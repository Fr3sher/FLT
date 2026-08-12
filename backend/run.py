import atexit
import sys, os
import threading
import time
import urllib.request
import webbrowser


def _reexec_into_venv():
    """Run on the project's pinned interpreter, not whatever Python launched us.

    If a project .venv exists and we are not already its interpreter, re-exec
    into it before anything else imports. This makes every launch method — the
    start.bat/start.sh flow, a bare `python backend/run.py`, a double-click, an
    IDE, a shell with a newer Python first on PATH — converge on the SAME
    interpreter. That is what lets the optional ML extras (insightface / numpy<2
    / onnxruntime, which only publish wheels for CPython 3.10-3.12) install into
    a supported Python: the in-app installer and the capability probes both key
    off sys.executable, so if run.py runs on e.g. the machine's default 3.14 the
    extras can never install. Skipped for the frozen/portable build (it bundles
    its own Python) and once we are already the venv's python. Set
    LDS_NO_REEXEC=1 to opt out."""
    if getattr(sys, 'frozen', False) \
            or os.environ.get('LDS_REEXEC') == '1' \
            or os.environ.get('LDS_NO_REEXEC') == '1':
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in (('.venv', 'Scripts', 'python.exe'), ('.venv', 'bin', 'python')):
        venv_py = os.path.join(repo_root, *rel)
        if os.path.exists(venv_py):
            break
    else:
        return                                   # no venv -> nothing to switch to
    try:
        if os.path.samefile(venv_py, sys.executable):
            return                               # already the venv interpreter
    except OSError:
        if os.path.normcase(os.path.realpath(venv_py)) \
                == os.path.normcase(os.path.realpath(sys.executable)):
            return
    os.environ['LDS_REEXEC'] = '1'               # loop guard for the re-exec'd child
    print(f"[LDS] re-launching under the project venv: {venv_py}", flush=True)
    os.execv(venv_py, [venv_py, os.path.abspath(__file__), *sys.argv[1:]])


_reexec_into_venv()

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from bootstrap_dependencies import ensure_pillow_consistent

# Must run before importing ``app`` (which eventually imports PIL).  This fixes
# Windows installs left half-upgraded by versions of the in-app updater that ran
# pip while Pillow files were still loaded and locked by the Flask process.
ensure_pillow_consistent()

from app import create_app
from port_utils import find_available_port
from single_instance import live_instance, refusal_message, release_lock, write_lock

try:
    from app.config import get as cfg_get
except ImportError:
    cfg_get = lambda k, d=None: {'server.host': '127.0.0.1', 'server.port': 5000}.get(k, d)

app = create_app()


def _announce_when_ready(url, open_browser=False, timeout=180):
    """Print the address the app is actually serving on — and open the browser
    when asked — once that address answers.

    The URL has to be printed HERE because Werkzeug's own " * Running on ..."
    banner never reaches the terminal: ``create_app`` attaches a rotating file
    handler to the ROOT logger, so werkzeug's INFO-level banner lands in
    ``data/app.log`` instead of stdout. A plain ``python backend/run.py`` used to
    print no address at all, and any launcher that reads the terminal for one
    (the Pinokio launcher does, to light up its "Open Web UI" tab) would wait
    forever. Waiting for /api/health first means the line — and the browser tab —
    appear when the app can actually answer, not on a startup error page.

    On timeout the address is printed anyway: a slow first boot must not leave a
    launcher hanging on a line that never comes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + 'api/health', timeout=1) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    print(f"[LDS] Ready on {url}", flush=True)
    if open_browser:
        webbrowser.open(url)

if __name__ == '__main__':
    host = os.environ.get('LDS_HOST') or cfg_get('server.host')
    requested_port = int(os.environ.get('LDS_PORT') or cfg_get('server.port'))
    # One data folder, one server — checked BEFORE the port slide below, which
    # is exactly how a double-launch used to become a second server on :5051
    # sharing the first one's database (private in-memory job registries, a
    # pass running in one process while the other swore the bank was idle).
    # Instances on their OWN data folder (worktrees, proof instances with
    # LDS_DATA_DIR) are untouched; LDS_ALLOW_SECOND_INSTANCE=1 overrides.
    data_dir = app.config['LDS_DATA_DIR']
    running = live_instance(data_dir)
    if running:
        print(refusal_message(running), flush=True)
        if os.environ.get('LDS_OPEN_BROWSER') == '1':
            # The double-click case: the person wanted the app on screen, and
            # it exists already — open THAT one instead of printing at them.
            webbrowser.open(f"http://127.0.0.1:{running['port']}/")
        sys.exit(0)
    port = (requested_port if os.environ.get('LDS_AUTO_PORT') == '0'
            else find_available_port(host, requested_port))
    if port != requested_port:
        print(f"[LDS] port {requested_port} is already in use; using {port} instead.",
              flush=True)
    os.environ['LDS_PORT'] = str(port)
    is_lan = host not in ('127.0.0.1', 'localhost', '::1')
    if is_lan and cfg_get('server.require_token') \
            and not os.environ.get('LDS_ACCESS_TOKEN') \
            and os.environ.get('LDS_ALLOW_UNAUTHENTICATED') != '1':
        # Token gate is ON (opt-in in Settings): make sure netguard has a token to
        # check. Persisted in config.json (not just this process's env) so it
        # survives a restart instead of rotating every boot -- the Settings
        # "Server" card reads it back from there to show/copy it.
        token = cfg_get('server.access_token') or ''
        if not token:
            import secrets
            token = secrets.token_urlsafe(24)
            try:
                from app.config import save_config
                save_config({'server': {'access_token': token}})
            except ImportError:
                pass   # config module unavailable (see cfg_get fallback above) -> ephemeral this run
        os.environ['LDS_ACCESS_TOKEN'] = token
        print(f"\n[LDS] server.host={host} reachable from the network -> access token REQUIRED.")
        print(f"[LDS] Open from another device:  http://<this-machine>:{port}/?token={os.environ['LDS_ACCESS_TOKEN']}")
        print("[LDS] (turn the token off in Settings -> Server to open the LAN without one)\n")
    elif is_lan:
        print(f"\n[LDS] server.host={host} reachable from the network (no token — trusted-LAN mode).")
        print(f"[LDS] Open from another device:  http://<this-machine>:{port}/\n")
    # Snapshot of what's ACTUALLY bound, for the Settings "Server" card: config.json
    # may already hold newer values the user saved but hasn't restarted into yet, so
    # reading cfg_get again there would lie about what's currently serving requests.
    app.config['LDS_BOUND_HOST'] = host
    app.config['LDS_BOUND_PORT'] = port
    # Claim the data folder only once the port is settled, so the lock records
    # the address the next double-launch should be pointed at. Released on
    # clean exit; a crash leaves it behind, where the dead pid reads as stale.
    write_lock(data_dir, host, port)
    atexit.register(release_lock, data_dir)
    local_host = {'0.0.0.0': '127.0.0.1', '::': '::1'}.get(host, host)
    if ':' in local_host and not local_host.startswith('['):
        local_host = f'[{local_host}]'
    url = f"http://{local_host}:{port}/"
    threading.Thread(target=_announce_when_ready, args=(url,),
                     kwargs={'open_browser': os.environ.get('LDS_OPEN_BROWSER') == '1'},
                     daemon=True).start()

    # Warm the capability import caches in the background so the FIRST real
    # request doesn't eat the cold-start cost. probe() spawns several subprocess
    # `import torch` probes against the ai-toolkit venv; the first one has to
    # fault ~2 GB of torch DLLs from cold disk page-cache (~30 s). Running it
    # once here, off the request path, means a user who connects right after a
    # container restart gets a fast /api/capabilities instead of a 30 s wait.
    # It shares this process's `_import_cache`, and probe() is a no-op if the
    # cache is already warm (TTL 30 s) — so this never re-fires on later boots
    # of the same process.
    def _warm_capabilities():
        try:
            from app import capabilities
            capabilities.probe()
        except Exception:
            pass  # warm-up is best-effort; a failed probe is never fatal

    threading.Thread(target=_warm_capabilities, daemon=True).start()

    if os.environ.get('FLASK_DEBUG', '0') == '1':
        app.run(debug=True, host=host, port=port, threaded=True, use_reloader=False)
    else:
        try:
            from waitress import serve
        except Exception:
            app.run(debug=False, host=host, port=port, threaded=True, use_reloader=False)
        else:
            # Production path: waitress (threaded, pure-Python) instead of
            # Werkzeug's single-threaded dev server. The app keeps its in-memory
            # state in a single process; waitress runs many threads against that
            # same process, so nothing that relies on module-level state breaks.
            # (queue_manager reads/writes are DB-backed via SystemState, so even
            # multi-worker would be safe, but the threaded single-process model is
            # the conservative choice.)
            serve(app, host=host, port=port, threads=8, channel_timeout=120)
