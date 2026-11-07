"""Prompt batches must reach EVERY launch route. create_comparison_run accepted
prompts, but POST /api/studio/run did not forward them. Consequently history,
scenes and Civitai batches silently failed on multi-LoRA comparison. Two
complementary guards cover this: post a batch through the repaired route and
inspect the engine input; then discover every engine function accepting prompts
and require every app/routes caller to pass prompts=. New routes or engine entry
points enter the check automatically instead of relying on a fixed list."""
import ast
import inspect
import pathlib

ROUTES_DIR = pathlib.Path(__file__).resolve().parents[1] / 'app' / 'routes'


def _comfy(monkeypatch, reachable=True):
    monkeypatch.setattr('app.capabilities.probe',
                        lambda *a, **k: {'comfyui': {'reachable': reachable}})
    monkeypatch.setattr('app.capabilities.probe_comfyui', lambda: {'ok': reachable, 'status': 'ok' if reachable else 'unreachable', 'detail': '', 'hint': 'Check the URL'})


# 1) Execute the guard: the repaired route really forwards the batch.

def test_studio_run_forwards_the_prompt_batch_to_the_engine(client, monkeypatch):
    """Multi-LoRA comparison must forward the posted batch to the engine."""
    _comfy(monkeypatch)
    seen = {}

    def _spy(*a, **k):
        seen.update(k)
        return {'created': 2, 'seed': 42, 'count': 1, 'run_id': 'r1'}

    monkeypatch.setattr('app.services.lora_test_studio.create_comparison_run', _spy)
    resp = client.post('/api/studio/run', json={
        'selections': [{'dataset_id': 1, 'checkpoint': 'x'}],
        'prompts': ['a first prompt', 'a second one'],
    })
    assert resp.status_code == 200, resp.get_json()
    assert seen.get('prompts') == ['a first prompt', 'a second one']


def test_studio_run_without_a_batch_sends_none(client, monkeypatch):
    """No selection means prompts=None, preserving previous behavior."""
    _comfy(monkeypatch)
    seen = {}

    def _spy(*a, **k):
        seen.update(k)
        return {'created': 1, 'seed': 42, 'count': 1, 'run_id': 'r1'}

    monkeypatch.setattr('app.services.lora_test_studio.create_comparison_run', _spy)
    resp = client.post('/api/studio/run',
                       json={'selections': [{'dataset_id': 1, 'checkpoint': 'x'}]})
    assert resp.status_code == 200, resp.get_json()
    assert seen.get('prompts') is None


# 2) Structural guard discovers its own scope.

def _engine_functions_accepting_prompts():
    """Discover {name: module} for engine entry points accepting prompts through
    introspection, never a fixed list, so new entry points are covered
    automatically."""
    from app.services import cloud_training, lora_test_studio
    found = {}
    for mod in (lora_test_studio, cloud_training):
        for name, obj in vars(mod).items():
            if name.startswith('_') or not inspect.isfunction(obj):
                continue
            if getattr(obj, '__module__', None) != mod.__name__:
                continue            # Re-export: checked in its owning module.
            try:
                if 'prompts' in inspect.signature(obj).parameters:
                    found[name] = mod.__name__
            except (TypeError, ValueError):
                continue
    return found


def _call_sites(func_names):
    """Return (file, line, name, passes_prompts) for every matching call in
    app/routes, including module aliases and direct function imports."""
    out = []
    for path in sorted(ROUTES_DIR.rglob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', None)
            if name in func_names:
                passes = any(kw.arg == 'prompts' for kw in node.keywords)
                out.append((path.name, node.lineno, name, passes))
    return out


def test_every_route_that_launches_a_run_forwards_the_prompt_batch():
    engines = _engine_functions_accepting_prompts()
    assert engines, "no engine entry point accepts prompts; the guard covers nothing"

    sites = _call_sites(set(engines))
    assert sites, (
        "no callers found in app/routes/ for "
        f"{sorted(engines)}; the guard cannot verify forwarding"
    )

    missing = [(f, ln, n) for (f, ln, n, ok) in sites if not ok]
    assert not missing, (
        'These routes launch a run WITHOUT forwarding the prompt batch; '
        "the prompt axis is unreachable through them:\n"
        + '\n'.join(f'  {f}:{ln} -> {n}(…)  [prompts= missing]' for f, ln, n in missing)
    )
