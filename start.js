/* Pinokio start script — runs the Flask server as a Pinokio daemon.

   The URL is READ BACK from the terminal instead of being hardcoded: port 5050
   is a default, not a promise (backend/run.py advances to the next free port
   when something else already holds it), so `local.set url` uses whatever
   Werkzeug reports it bound. That is what fills the "Open Web UI" tab.

   Environment:
   - LDS_PORT=5050    same default as start.bat (5000 collides constantly).
   - LDS_NO_REEXEC=1  backend/run.py re-execs itself into a `.venv/` sitting
                      next to it when it finds one. Under Pinokio the pinned
                      interpreter is the `env/` venv Pinokio just activated, so
                      a `.venv/` left behind by an earlier start.bat run in the
                      same folder must not hijack the launch.
   - LDS_OPEN_BROWSER is intentionally NOT set: Pinokio opens the app itself. */
module.exports = {
  daemon: true,
  run: [
    {
      method: "shell.run",
      params: {
        venv: "env",
        env: {
          PYTHONUTF8: "1",
          LDS_PORT: "5050",
          LDS_NO_REEXEC: "1"
        },
        message: [
          "python backend/run.py"
        ],
        on: [{
          // backend/run.py prints "[LDS] Ready on http://127.0.0.1:5050/" once
          // /api/health answers. NOT Werkzeug's " * Running on ..." banner:
          // create_app routes the root logger into data/app.log, so that banner
          // never reaches the terminal and a launcher waiting on it hangs.
          event: "/\\[LDS\\] Ready on (http:\\/\\/\\S+)/",
          done: true
        }]
      }
    },
    {
      method: "local.set",
      params: {
        url: "{{input.event[1]}}"
      }
    }
  ]
}
