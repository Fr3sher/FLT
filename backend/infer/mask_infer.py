"""Person-mask generator using rembg/u2net through ComfyUI's embedded
Python because rembg is absent from Flask's venv. Uses the same
subprocess pattern as face_score_infer.py.

stdin: {images: [paths], out_dir: path}. The final stdout line is JSON
{ok: bool, written: N, results: {path: state}}; logs go to stderr.
Save the raw grayscale u2net matte (white=person, black=background,
soft hair edges) as PNG with the image's basename, matching ai-toolkit's
mask_path convention. Training applies mask_min_value to the background;
this worker does not."""
import json
import os
import sys


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        images = payload.get('images') or []
        out_dir = payload['out_dir']
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"payload: {e}"}))
        return 1
    os.makedirs(out_dir, exist_ok=True)
    try:
        from PIL import Image
        from rembg import new_session, remove
        session = new_session('u2net', providers=['CPUExecutionProvider'])
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"rembg init: {e}"}))
        return 1
    results, written = {}, 0
    for i, p in enumerate(images, 1):
        try:
            with Image.open(p) as im:
                mask = remove(im.convert('RGB'), session=session, only_mask=True)
            name = os.path.splitext(os.path.basename(p))[0] + '.png'
            mask.convert('L').save(os.path.join(out_dir, name), 'PNG')
            results[p] = 'ok'
            written += 1
        except Exception as e:
            results[p] = f'error: {e}'
        _log(f'[mask] {i}/{len(images)} {results[p]}')
    print(json.dumps({"ok": True, "written": written, "results": results}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
