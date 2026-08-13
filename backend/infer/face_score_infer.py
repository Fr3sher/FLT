"""Face similarity scorer — InsightFace antelopev2, lance dans un interprete DEDIE
(insightface y est installe, PAS dans le venv Flask). CPU force (provider CPU + ctx_id=-1)
-> pas de GPU, ne touche pas ComfyUI.
Protocole stdin: {"ref": path, "images": [paths], "models_root": path|null} -> stdout
UNE ligne JSON {"ref_ok": bool, "results": {path: {state, sim?, det, bbox_frac, yaw}}}.
Logs -> stderr.
Gating 3-etats + padding rescue (valide empiriquement sur test3)."""
from __future__ import annotations
import json, os, sys

DET_MIN, BBOX_MIN, YAW_MAX = 0.50, 0.06, 40.0


def _log(m): print(m, file=sys.stderr, flush=True)


def _repair_nested_antelopev2(models_root=None):
    """L'antelopev2.zip d'insightface 0.7.3 contient un DOSSIER RACINE (contrairement
    a buffalo_l) : l'auto-extract pose les .onnx dans .../models/antelopev2/antelopev2/,
    or FaceAnalysis globbe NON-recursivement -> 0 modele charge -> AssertionError
    (`'detection' in self.models`). CHAQUE install fraiche en auto-download est
    touchee, et ca ne s'auto-repare jamais (le dossier externe existe, insightface
    ne re-telecharge pas). On aplatit une fois pour toutes ici."""
    import glob, os, shutil
    root = models_root or os.path.join(os.path.expanduser('~'), '.insightface')
    outer = os.path.join(root, 'models', 'antelopev2')
    inner = os.path.join(outer, 'antelopev2')
    if not os.path.isdir(inner) or glob.glob(os.path.join(outer, '*.onnx')):
        return
    moved = 0
    for f in glob.glob(os.path.join(inner, '*.onnx')):
        shutil.move(f, outer)
        moved += 1
    try:
        os.rmdir(inner)
    except OSError:
        pass  # reliquats (zip...) — sans consequence
    if moved:
        _log(f"[face] repaired nested antelopev2 layout ({moved} model(s) moved up)")


def main() -> int:
    raw = sys.stdin.read()
    try:
        req = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        print(json.dumps({"ref_ok": False, "results": {}, "error": f"bad json: {e}"})); return 1
    ref = req.get("ref")
    refs = [str(p) for p in (req.get("refs") or [])]
    if ref and str(ref) not in refs:
        refs.insert(0, str(ref))
    images = [str(p) for p in (req.get("images") or [])]
    quality_only = bool(req.get("quality_only"))
    models_root = req.get("models_root") or None
    if not images or (not quality_only and not refs):
        print(json.dumps({"ref_ok": False, "results": {}, "error": "missing refs/images"})); return 1

    import numpy as np, cv2
    from insightface.app import FaceAnalysis
    _repair_nested_antelopev2(models_root)
    try:
        kwargs = {'name': 'antelopev2', 'providers': ['CPUExecutionProvider']}
        if models_root:
            kwargs['root'] = models_root
        app = FaceAnalysis(**kwargs)
        app.prepare(ctx_id=-1, det_size=(640, 640))
    except Exception as e:
        # Un crash de chargement (modeles absents/corrompus) doit sortir en JSON
        # propre — pas en traceback muet que le parent resume en « pas de JSON ».
        print(json.dumps({"ref_ok": False, "results": {},
                          "error": f"model load failed: {type(e).__name__}: {e}"}))
        return 1
    import onnxruntime as ort
    _log(f"[face] providers: {ort.get_available_providers()}")

    def biggest(faces):
        return max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1])) if faces else None

    def detect(img):
        f = biggest(app.get(img))
        if f is None:  # padding rescue : SCRFD rate les gros plans plein cadre
            h, w = img.shape[:2]; pad = int(0.25 * max(h, w))
            f2 = biggest(app.get(cv2.copyMakeBorder(img, pad, pad, pad, pad,
                                                    cv2.BORDER_CONSTANT, value=(0, 0, 0))))
            if f2 is not None:
                f2._padded = True
                return f2
        return f

    def analyze(path):
        img = cv2.imread(path)
        if img is None: return {"state": "unreadable"}
        h, w = img.shape[:2]
        f = detect(img)
        if f is None: return {"state": "no_face"}
        scale = 1.0
        if getattr(f, "_padded", False):
            pad = int(0.25 * max(h, w)); scale = (w + 2*pad) * (h + 2*pad) / (w * h)
        area = (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1])
        bbox_frac = float(area / (w * h) / scale)
        det = float(f.det_score)
        yaw = float(f.pose[1]) if getattr(f, "pose", None) is not None else 0.0
        state = "scorable"
        if det < DET_MIN: state = "low_det"
        elif bbox_frac < BBOX_MIN: state = "too_small"
        elif abs(yaw) > YAW_MAX: state = "extreme_pose"
        return {"state": state, "det": round(det, 3), "bbox_frac": round(bbox_frac, 4),
                "yaw": round(yaw, 1), "_emb": f.normed_embedding}

    # Multiple references are averaged into a centroid (normalised) so a single
    # odd reference can't skew the identity; quality_only skips the comparison.
    centroid = None
    if not quality_only:
        embs = []
        for rp in refs:
            rr = analyze(rp)
            e = rr.pop("_emb", None)
            if rr.get("state") == "scorable" and e is not None:
                embs.append(e)
            else:
                _log(f"[face] ref {os.path.basename(rp)} unusable: {rr.get('state')}")
        if not embs:
            print(json.dumps({"ref_ok": False, "results": {},
                              "error": "no usable face in the reference photos"})); return 1
        centroid = np.mean(np.array(embs), axis=0)
        norm = float(np.linalg.norm(centroid)) or 1.0
        centroid = centroid / norm

    results = {}
    for i, p in enumerate(images, 1):
        try:
            r = analyze(p); emb = r.pop("_emb", None)
            if not quality_only and r["state"] == "scorable" and emb is not None:
                r["sim"] = round(float(np.dot(centroid, emb)), 4)
            results[p] = r
            _log(f"[face] {i}/{len(images)} {r['state']} sim={r.get('sim')}")
        except Exception as e:
            results[p] = {"state": "error", "error": str(e)}
            _log(f"[face] {i}/{len(images)} ERROR {e}")
    print(json.dumps({"ref_ok": True, "results": results}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
