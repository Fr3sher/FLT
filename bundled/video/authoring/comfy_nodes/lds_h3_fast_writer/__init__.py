# SPDX-License-Identifier: Apache-2.0
"""Chunked synchronous H.264 writer adapted from jacokon/fasth3-live.

The Video plugin requires completion and errors to belong to this exact prompt. The
upstream async worker and VAE mutation node are deliberately not registered.
See NOTICE and LICENSE for provenance. The input image tensor is never mutated.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import threading

import folder_paths
import torch

ENCODE_TIMEOUT_SECONDS = 300


def _stop_encoder(proc):
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass  # The process may have exited between poll and kill.


def _ffmpeg() -> str:
    """Prefer an explicitly configured ffmpeg, else the one VHS already uses."""
    env = os.environ.get("H3_FFMPEG")
    if env and os.path.exists(env):
        return env
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        pass
    return shutil.which("ffmpeg") or "ffmpeg"


def _frame_bytes(chunk: torch.Tensor) -> bytes:
    """[N,H,W,C] float in 0..1 -> packed rgb24 bytes, in as few passes as possible.

    ``mul`` and not ``mul_``: ``.to(device, dtype)`` returns the SAME tensor when
    both already match, so an in-place scale here would rewrite the caller's
    IMAGE to 0..255 and every later read of it -- a re-execution, a second
    consumer -- would come back white. ``mul`` is the one copy this needs;
    everything after it acts on that copy and is in place.
    """
    out = chunk.detach().to("cpu", torch.float32).mul(255.0).add_(0.5)
    return out.clamp_(0.0, 255.0).to(torch.uint8).contiguous().numpy().tobytes()


def _encode(job: dict) -> None:
    """Run one clip through ffmpeg and move it to its final name when done."""
    images, audio, tmp, final = job["images"], job["audio"], job["tmp"], job["final"]
    ff = _ffmpeg()
    args = [ff, "-v", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{job['width']}x{job['height']}", "-r", f"{job['fps']:.6f}",
            "-i", "pipe:0"]

    # Audio goes in as a second input in the SAME pass. VHS instead encodes the
    # video, then re-opens it to mux -- correct, but it pays for a second
    # process and a second read of the file it just wrote.
    audio_path = None
    if audio is not None:
        rate, wave = audio["rate"], audio["wave"]
        fd, audio_path = tempfile.mkstemp(suffix=".f32", prefix="h3aud_")
        with os.fdopen(fd, "wb") as fh:
            fh.write(wave.numpy().tobytes())
        args += ["-f", "f32le", "-ar", str(rate), "-ac", str(wave.shape[1]),
                 "-i", audio_path]

    args += ["-c:v", "libx264", "-preset", job["preset"], "-crf", str(job["crf"]),
             "-pix_fmt", "yuv420p"]
    if audio_path:
        args += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    # the .part name hides the container from ffmpeg's extension sniffing
    args += ["-movflags", "+faststart", "-f", "mp4", tmp]

    try:
        # stderr to a real file, never a pipe: nothing drains a pipe while the
        # writes below are blocking, so a chatty ffmpeg would deadlock.
        with tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=err,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            deadline = threading.Timer(ENCODE_TIMEOUT_SECONDS, _stop_encoder, args=(proc,))
            deadline.daemon = True
            deadline.start()
            try:
                try:
                    n = images.shape[0]
                    step = job["chunk_frames"]
                    for start in range(0, n, step):
                        proc.stdin.write(_frame_bytes(images[start:start + step]))
                except BrokenPipeError:
                    pass
                except BaseException:
                    _stop_encoder(proc)
                    raise
                finally:
                    try:
                        proc.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass
                rc = proc.wait()
            finally:
                deadline.cancel()
                _stop_encoder(proc)
                proc.wait()
            if rc != 0:
                err.seek(0)
                raise RuntimeError(f"ffmpeg exited {rc}:\n"
                                   f"{err.read().decode('utf-8', 'replace')[-2000:]}")
        os.replace(tmp, final)          # atomic within a volume
    finally:
        if audio_path:
            try:
                os.remove(audio_path)
            except OSError:
                pass
        if os.path.exists(tmp):
            try:
                os.remove(tmp)          # a failed encode leaves no .part behind
            except OSError:
                pass


class H3FastWriteVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.01}),
                "filename_prefix": ("STRING", {"default": "video/ComfyUI"}),
                "crf": ("INT", {"default": 16, "min": 0, "max": 51,
                                "tooltip": "libx264 quality; lower is better. 16 is "
                                           "near-transparent and cheap enough that the "
                                           "encoder is not the bottleneck."}),
                "preset": (["veryfast", "faster", "fast", "medium", "ultrafast", "superfast"],
                           {"default": "veryfast"}),
            },
            "optional": {
                "audio": ("AUDIO",),
                "async_write": ("BOOLEAN", {"default": False,
                                            "tooltip": "Must remain false: the MP4 is complete when this node returns."}),
                "chunk_frames": ("INT", {"default": 32, "min": 1, "max": 4096,
                                         "tooltip": "Frames converted per pass. Larger is "
                                                    "marginally slower here; 32 measured best."}),
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "write"
    OUTPUT_NODE = True
    CATEGORY = "video"
    DESCRIPTION = "Chunked H.264 writer. Returns only when the MP4 is finalized; no metadata or background worker."

    def write(self, images, fps, filename_prefix, crf, preset,
              audio=None, async_write=False, chunk_frames=32):
        if async_write:
            raise ValueError("Fast writer requires synchronous completion.")

        if images.ndim == 5:  # a batched decode arrives as [B,N,H,W,C]
            images = images.reshape(-1, *images.shape[-3:])
        if images.ndim != 4 or not images.shape[0] or not math.isfinite(fps) or fps <= 0:
            raise ValueError("Invalid video dimensions or frame rate.")
        if type(chunk_frames) is not int or not 1 <= chunk_frames <= 4096:
            raise ValueError("Invalid video chunk size.")
        n_frames, height, width = images.shape[0], images.shape[1], images.shape[2]
        if images.shape[-1] != 3:
            raise ValueError(f"expected 3 colour channels, got {images.shape[-1]}")

        out_dir, name, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), width, height)
        file = f"{name}_{counter:05}_.mp4"
        final = os.path.join(out_dir, file)

        snd = None
        if audio is not None and audio.get("waveform") is not None:
            rate = int(audio["sample_rate"])
            wave = audio["waveform"]
            if wave.ndim == 3:
                wave = wave[0]
            # trim to the video's own duration, as SaveVideo does; a longer tail
            # would otherwise extend the clip past its last frame
            if rate <= 0 or wave.ndim != 2 or wave.shape[0] < 1:
                raise ValueError("Invalid audio shape or sample rate.")
            samples = math.ceil(rate / fps * n_frames)
            wave = wave[:, :samples]
            # -shortest must stop on the video, never discard its final frames
            # because H3 produced a short (or empty) audio tail.
            if wave.shape[1] < samples:
                wave = torch.nn.functional.pad(wave, (0, samples - wave.shape[1]))
            # interleave now: it is small, and it releases the caller's tensor
            snd = {"rate": rate,
                   "wave": wave.detach().to("cpu", torch.float32)
                           .transpose(0, 1).contiguous()}

        job = {"images": images, "audio": snd, "fps": fps, "crf": crf,
               "preset": preset, "chunk_frames": chunk_frames,
               "width": width, "height": height,
               "tmp": final + ".part", "final": final}

        _encode(job)

        return {"ui": {"gifs": [{"filename": file, "subfolder": subfolder,
                                 "type": "output", "format": "video/h264-mp4",
                                 "frame_rate": fps}]}}


NODE_CLASS_MAPPINGS = {"LDSH3FastWriteVideo": H3FastWriteVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"LDSH3FastWriteVideo": "Fast Write Video (synchronous H.264)"}
