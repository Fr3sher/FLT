"""Shared H3 model download specifications (SDK 1.10).

Products register their own action IDs for these destinations. Existing files
are reused through the host downloader; no product or route is registered here.
"""

# MiniMax H3 - the Video Test Studio's engine. Four required files, 39.5 GB
# measured on disk, all from Comfy-Org's own conversion (verified against the
# hub's file list: not gated, and these exact paths). They land in ComfyUI's
# standard subfolders, which are also the paths the repository uses - so the
# training lane's WEIGHT_FOOTPRINTS and these entries name the same four files
# and cannot drift into two different opinions of what H3 needs.
#
# `min_free_gb` is the file's own size plus room to write it, not the lane's
# total: each action is downloaded on its own, and a machine that can take three
# of them should be told about the fourth rather than refused up front.
H3_DOWNLOADS = {
    'h3_base': {
        'url': 'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors',
        'dest': ('diffusion_models', 'minimax_h3_fl2va_pruned_int8_convrot.safetensors'),
        'min_free_gb': 24, 'gated': False, 'min_bytes': 8 * 1024 ** 3,
        'license_url': 'https://huggingface.co/Comfy-Org/MiniMax-H3',
    },
    'h3_text_encoder': {
        'url': 'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',
        'dest': ('text_encoders', 'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors'),
        'min_free_gb': 19, 'gated': False, 'min_bytes': 6 * 1024 ** 3,
        'license_url': 'https://huggingface.co/Comfy-Org/MiniMax-H3',
    },
    'h3_video_vae': {
        'url': 'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors',
        'dest': ('vae', 'minimax_h3_video_vae_fp16.safetensors'),
        'min_free_gb': 8, 'gated': False, 'min_bytes': 2 * 1024 ** 3,
        'license_url': 'https://huggingface.co/Comfy-Org/MiniMax-H3',
    },
    # Small, and not optional despite it: H3 emits video and audio in ONE latent,
    # so the graph decodes both. Without this the render stops at the decode.
    'h3_audio_vae': {
        'url': 'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors',
        'dest': ('vae', 'minimax_h3_audio_vae_fp32.safetensors'),
        'min_free_gb': 3, 'gated': False, 'min_bytes': 128 * 1024 ** 2,
        'license_url': 'https://huggingface.co/Comfy-Org/MiniMax-H3',
    },
    # 🪶 The lighter base of the Render panel: the official H3 weights quantized
    # to W4A8 ConvRot by Winnougan (apache-2.0 on the hub, not gated; the hub
    # blob is sha256 8b624de0ab7554bb507c4486093d4c93e0bf2eb2a40c2382f26eb0af7cd97407,
    # the file the studio was measured with). 12.5 GB against 21 for the
    # official base; MiniMax's community licence still applies to the weights
    # underneath, exactly as for h3_base. Optional: absent, the checkbox is
    # greyed and the official base renders. Reads only on ComfyUI >= 0.31.0, and
    # its fused kernel wants a GPU of compute capability 8.0 or newer (Ampere);
    # below that it still runs, on the unaccelerated eager path.
    'h3_base_light': {
        'url': 'https://huggingface.co/Winnougan/MiniMax-H3-INT4_Convrot_ComfyUI/resolve/main/minimax_h3_fl2va_pruned-w4a8_convrot_pruned.safetensors',
        'dest': ('diffusion_models', 'minimax_h3_fl2va_pruned-w4a8_convrot_pruned.safetensors'),
        'min_free_gb': 15, 'gated': False, 'min_bytes': 10 * 1024 ** 3,
        'license_url': 'https://huggingface.co/Winnougan/MiniMax-H3-INT4_Convrot_ComfyUI',
    },
    # The 6-step distillation LoRA (larryvrh, apache-2.0, not gated - checked on
    # the hub; row 1 of the multimodalart H3 acceleration arena). Optional in
    # the sense that the lane runs without it, at twenty steps instead of six:
    # the difference between a clip in minutes and a clip in tens of minutes,
    # which is why the choice defaults to it wherever it CAN run.
    'h3_turbo_lora': {
        'url': 'https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora/resolve/main/minimax_h3_turbo_v4_step600_ema.safetensors',
        'dest': ('loras', 'minimax_h3_turbo_v4_step600_ema.safetensors'),
        'min_free_gb': 3, 'gated': False, 'min_bytes': 128 * 1024 ** 2,
        'license_url': 'https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora',
    },
    # ⚡ The other two accelerations of the Render panel — rows 2 and 3 of the
    # same arena, statistical ties with larryvrh's. Ordinary LoRAs for the
    # stock loader: no node pack. Parasyte is MIT (checked on the hub). The
    # DARE-TIES merge combines LightX2V v0.1 and larryvrh v4 (both apache-2.0)
    # but its own repo states no license — the panel says so, in words.
    'h3_parasyte_lora': {
        'url': 'https://huggingface.co/Plaguekind/H3-Lora/resolve/main/H3-PK-Parasyte-Turbo.safetensors',
        'dest': ('loras', 'H3-PK-Parasyte-Turbo.safetensors'),
        'min_free_gb': 5, 'gated': False, 'min_bytes': 1024 ** 3,
        'license_url': 'https://huggingface.co/Plaguekind/H3-Lora',
    },
    'h3_dareties_lora': {
        'url': 'https://huggingface.co/silveroxides/MiniMax-H3_tests/resolve/main/minimax_h3_fl2v_lightx2v_v0.1_dareties_v4_step600_comfy_fro.safetensors',
        'dest': ('loras', 'minimax_h3_fl2v_lightx2v_v0.1_dareties_v4_step600_comfy_fro.safetensors'),
        'min_free_gb': 3, 'gated': False, 'min_bytes': 512 * 1024 ** 2,
        'license_url': 'https://huggingface.co/silveroxides/MiniMax-H3_tests',
    },
    # 🔴 The video VAE quantized to int8 (Kijai's experimental repack, 3.17 GB
    # against 5.21 for fp16). Not faster to decode by much (jacokon measured
    # 9.2 s → 6.5 s at 362 frames on a 5090) but 2.3 GB lighter in host RAM,
    # which is what a machine holding two ComfyUI instances is short of. The
    # repository declares no licence of its own; the weights underneath stay
    # under MiniMax's community licence, as every H3 file here. Reads only on
    # ComfyUI >= 0.31.0 (older builds decode a quantized VAE to black frames).
    'h3_video_vae_int8': {
        'url': 'https://huggingface.co/Kijai/MiniMax-H3-experimental/resolve/main/minimax_h3_video_vae_int8_convrot.safetensors',
        'dest': ('vae', 'minimax_h3_video_vae_int8_convrot.safetensors'),
        'min_free_gb': 5, 'gated': False, 'min_bytes': 2 * 1024 ** 3,
        'license_url': 'https://huggingface.co/Kijai/MiniMax-H3-experimental',
    },
}



import os
from lds_sdk import setup
from lds_sdk import config as cfg

_VDN_HUB = 'https://huggingface.co/OpenVDN/vdn-minimax-h3/resolve/main/stage-dmd-step-250/'

_VDN_LICENSE_URL = 'https://huggingface.co/OpenVDN/vdn-minimax-h3'

_VDN_STAGE_COMPANIONS = (
    {'url': _VDN_HUB + 'model_spec.json',
     'dest': ('vdn', 'stage-dmd-step-250', 'model_spec.json'), 'kind': 'json'},
    {'url': _VDN_HUB + 'metadata.json',
     'dest': ('vdn', 'stage-dmd-step-250', 'metadata.json'), 'kind': 'json'},
    {'url': _VDN_HUB + 'linear_branch/config.json',
     'dest': ('vdn', 'stage-dmd-step-250', 'linear_branch', 'config.json'), 'kind': 'json'},
    {'url': _VDN_HUB + 'adapters/default/adapter_config.json',
     'dest': ('vdn', 'stage-dmd-step-250', 'adapters', 'default', 'adapter_config.json'),
     'kind': 'json'},
    {'url': _VDN_HUB + 'adapters/default/adapter_model.safetensors',
     'dest': ('vdn', 'stage-dmd-step-250', 'adapters', 'default', 'adapter_model.safetensors'),
     'min_bytes': 256 * 1024 ** 2, 'expected_bytes': 334026912,
     'sha256': '58558fef506f88bb41649242de9b9b3a365da806b51b2e96afbbe1625222058a'},
    {'url': _VDN_HUB + 'adapters/turbo/adapter_config.json',
     'dest': ('vdn', 'stage-dmd-step-250', 'adapters', 'turbo', 'adapter_config.json'),
     'kind': 'json'},
    {'url': _VDN_HUB + 'adapters/turbo/adapter_model.safetensors',
     'dest': ('vdn', 'stage-dmd-step-250', 'adapters', 'turbo', 'adapter_model.safetensors'),
     'min_bytes': 512 * 1024 ** 2, 'expected_bytes': 851452696,
     'sha256': '24fc93c82fe84dc45d0627f4e72c637bc387d282ba18f60ed3b7f8c81089392c'},
)

_VDN_STAGE_COMPANIONS = tuple({**c, 'license_url': _VDN_LICENSE_URL} for c in _VDN_STAGE_COMPANIONS)

def _vdn_extra_roots():
    """The VDN node derives a stage root beside each configured LoRA root."""
    from lds_sdk import h3_render as vts
    resolved = setup.resolve_install_folder(cfg.get('comfyui.base_dir') or '')
    base = os.path.normcase(os.path.normpath(os.path.join(resolved['resolved'], 'models', 'vdn')))
    return [root for root in vts.vdn_roots() if os.path.normcase(os.path.normpath(root)) != base]


def _vdn_stage_complete() -> bool:
    """Skip companions only for a complete stage outside the install's own tree."""
    from lds_sdk import h3_render as vts
    try:
        return any(not vts.vdn_stage_missing_under(root) for root in _vdn_extra_roots())
    except (OSError, ValueError):
        return False

H3_DOWNLOADS.update({'h3_vdn_stage': {'url': 'https://huggingface.co/OpenVDN/vdn-minimax-h3/resolve/main/stage-dmd-step-250/linear_branch/model.safetensors', 'dest': ('vdn', 'stage-dmd-step-250', 'linear_branch', 'model.safetensors'), 'min_free_gb': 8, 'gated': False, 'min_bytes': 3 * 1024 ** 3, 'sha256': 'dec6981c7874f5b3bc92d1a02e256b673a3b3499dc1a124714bb3b19da602855', 'expected_bytes': 4279428112, 'license_url': 'https://huggingface.co/OpenVDN/vdn-minimax-h3', 'companions': _VDN_STAGE_COMPANIONS, 'complete': _vdn_stage_complete, 'extra_roots': _vdn_extra_roots}, 'h3_vdn_stage_int8': {'url': 'https://huggingface.co/drbaph/vdn-minimax-h3-int8-convrot-comfyui/resolve/main/linear_branch/model_int8_convrot_comfyui.safetensors', 'dest': ('vdn', 'stage-dmd-step-250', 'linear_branch', 'model_int8_convrot_comfyui.safetensors'), 'min_free_gb': 6, 'gated': False, 'min_bytes': 2 * 1024 ** 3, 'sha256': '1fa18c3ebd94caa804ae3dc3a93df7ae069d8f5c363a00b6eb5288112c0f5abc', 'expected_bytes': 2304371056, 'license_url': 'https://huggingface.co/drbaph/vdn-minimax-h3-int8-convrot-comfyui', 'companions': _VDN_STAGE_COMPANIONS, 'complete': _vdn_stage_complete, 'extra_roots': _vdn_extra_roots}})

__all__ = [
    'H3_DOWNLOADS',
]
