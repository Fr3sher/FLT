# API image engines

Nano Banana (Gemini), ChatGPT image generation and OpenRouter, with their image
model settings and provider keys. ChatGPT also retains its experimental OAuth
subscription lane and Codex CLI session import. Configure them from
**Plugins → API image engines → Settings**, then choose an engine in the dataset
generation controls.

Engine ids, generated-file tags, configuration keys and OAuth route URLs retain
their existing values. OAuth state remains in `data/chatgpt_oauth.json`. No other
product is required. Registration adds the engines, readiness probes and OAuth
routes; it starts no provider request, worker or installation.

The provider tests use temporary configuration/token files and an isolated SDK
adapter. HTTP responses are simulated and external runtime calls are refused.
They cover request construction, response/error interpretation and OAuth state;
the host must separately qualify engine dispatch, access control and activation.

Run the Python tests with `python -m pytest bundled/api_engines/tests -q` from the
repository root. JavaScript tests cover the descriptor and public image controls;
they require the host's `@lds/plugin-sdk/help` module resolver.
