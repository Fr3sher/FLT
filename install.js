/* Pinokio install script — see pinokio.js for why this runs in place.

   Deliberately small. The core app is a Flask server plus a frontend that is
   committed already built (frontend/dist), so a working install is exactly one
   pip run: no torch, no node build, nothing GPU-specific. Everything heavy is
   OPTIONAL and installed later from the app's own Setup screen, which knows
   what this machine actually has — pinning that guesswork here would download
   gigabytes for users who only import images.

   The venv is created by Pinokio at `env/` from its bundled Python (3.10),
   which is inside the 3.10-3.12 window the optional ML extras publish wheels
   for, so the in-app Setup installs land in a supported interpreter. */
module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        venv: "env",
        message: [
          "uv pip install -r backend/requirements.txt"
        ]
      }
    },
    {
      method: "notify",
      params: {
        html: "Installed. Click <b>Start</b> — then use the app's <b>Setup</b> screen to connect ComfyUI, Ollama or the optional ML helpers."
      }
    }
  ]
}
