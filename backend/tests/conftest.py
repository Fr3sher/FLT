import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _basetemp_guard


def pytest_configure(config):
    """Refuse a --basetemp another live pytest run already owns.

    pytest rm_rf's the basetemp it is given (see _basetemp_guard), so two runs
    sharing one wipe each other's tmp_path trees mid-flight and fail on things
    that have nothing to do with the code. Several agents running this suite in
    parallel is now the norm, so the collision is refused here — with a message
    naming the other run — instead of surfacing as a phantom failure plus a
    handful of "ERROR at setup" half a suite later."""
    basetemp = getattr(config.option, 'basetemp', None)
    if not basetemp:
        return                        # no --basetemp: pytest numbers per run, safe
    conflict = _basetemp_guard.claim(basetemp)
    if conflict:
        pytest.exit(conflict, returncode=pytest.ExitCode.USAGE_ERROR)


def pytest_unconfigure(config):
    basetemp = getattr(config.option, 'basetemp', None)
    if basetemp:
        _basetemp_guard.release(basetemp)

@pytest.fixture(autouse=True)
def _restore_secret_env():
    """set_secrets() writes os.environ directly; snapshot & restore the secret keys.

    Also CLEAR them at setup: config.py runs load_dotenv(ENV_PATH) at import, and at
    collection time (before LDS_ENV is pointed at a tmp file) ENV_PATH is the real
    repo .env — so a developer who saved a real Gemini/OpenAI key via the app would
    leak it into os.environ and make "unconfigured" probes see a key. Starting each
    test with the keys unset makes the suite independent of the local .env; tests
    that need a key set it themselves via monkeypatch.setenv."""
    import os
    from app.config import SECRET_KEYS as keys   # stays in sync as keys are added
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

@pytest.fixture(autouse=True)
def _no_live_comfyui_vram_release(monkeypatch):
    """Every GPU-exclusive vision window POSTs /free to ComfyUI — for real.

    `gpu_exclusive_vision_window` calls `free_comfyui_vram()`, which is a live
    `requests.post('<comfyui>/free', {"unload_models": true, "free_memory": true})`
    with a 10 s timeout. Nothing mocks it, so on a developer machine where
    ComfyUI is running the unit suite REALLY unloads that ComfyUI's models —
    measured 2026-07-28: eleven test files reach 127.0.0.1:8188, among them the
    whole bank-vision-concurrency file.

    Two costs, and the second is the one that gets misfiled. It has a side
    effect on a program nobody asked it to touch; and its duration is whatever
    that program happens to be doing — instant when ComfyUI is idle, seconds
    when it is mid-generation, the full 10 s timeout when the port answers but
    the server is wedged. A test asserting "Stop returns in under 5 s" then
    passes or fails on the state of an unrelated process. That is not a flake,
    it is an undeclared dependency.

    Tests that are ABOUT this call (test_vision_features) monkeypatch it
    themselves; a later setattr wins over this one, so they are unaffected."""
    monkeypatch.setattr('app.utils.comfyui.free_comfyui_vram', lambda *a, **k: True)


@pytest.fixture(autouse=True)
def _reset_inmemory_registries():
    """dataset_activity is a process-global in-memory store (a batch dies with the
    process, not the request). With :memory: DBs each test restarts dataset ids at
    1, so a batch a PRIOR test began on 'dataset 1' would look live to the next
    test's fresh 'dataset 1' — enough to make the kind-switch guard 409 spuriously.
    Clear it around every test so in-memory activity never leaks across cases.

    The bank folder-sync cooldowns are process-global for the same reason: bank
    id 1 of a prior test would make the next test's first walk a no-op.

    The vision keep-warm LEASE is the same kind of global, and the nastiest: any
    test that crops/uploads through detect_head_bbox grants a 120 s lease, and
    every later test whose code path is "about to take the GPU" then calls
    revoke() -> a REAL HTTP POST to whatever answers on the Ollama URL. That is
    how test_training_queue_atomic failed once in a full suite and never alone:
    the launch under test paid for a live unload of a machine's actual Ollama,
    which can take tens of seconds. The suite must never depend on a lease left
    behind by an earlier test, nor talk to a live Ollama by accident.

    The 🔤 text-search query cache is a third one, and it bites the same way in
    reverse: it is keyed by PHRASE only (a CLIP vector depends on the checkpoint,
    not on the bank), so a query encoded by one test would be served from memory
    to the next — whose LDS_DATA_DIR is a different empty tmp dir. A test proving
    "the encoder is invoked exactly once" would then see zero calls and fail, and
    one proving "no ML python ⇒ 503" would silently get a cache hit and a 200.
    Both did, before this line existed."""
    from app.services import bank_jobs, bank_undo, clip_text_encoder
    from app.services import dataset_activity
    from app.services import image_bank_service, vision_keepalive
    dataset_activity.reset()
    bank_jobs.reset()
    bank_undo.reset()
    image_bank_service.reset_folder_sync()
    image_bank_service.reset_score_memo()
    vision_keepalive.forget_lease()
    clip_text_encoder.forget_memory_cache()
    yield
    dataset_activity.reset()
    bank_jobs.reset()
    bank_undo.reset()
    image_bank_service.reset_folder_sync()
    image_bank_service.reset_score_memo()
    vision_keepalive.forget_lease()
    clip_text_encoder.forget_memory_cache()
    clip_text_encoder.release()

@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('LDS_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('LDS_CONFIG', str(tmp_path / 'config.json'))
    monkeypatch.setenv('LDS_ENV', str(tmp_path / '.env'))
    import app.config as _cfg
    monkeypatch.setattr(_cfg, 'ENV_PATH', tmp_path / '.env')   # never touch the real .env in tests
    # config.py caches load_config() in a module-level global keyed on nothing but
    # "has it been loaded before" -- it isn't tied to LDS_CONFIG. Without resetting it
    # here, a test that calls save_config() with a real comfyui.base_dir leaks that
    # value into every later test's "fresh" app (same process, stale cache), even
    # though each test gets its own tmp_path/env vars. Task 14 (Klein path) hit this:
    # a test asserting "ComfyUI unconfigured -> RuntimeError" silently inherited a
    # previous test's real base_dir and passed for the wrong reason.
    monkeypatch.setattr(_cfg, '_cache', None)
    from app import create_app
    application = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False,
                              'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    yield application

@pytest.fixture()
def client(app):
    return app.test_client()
