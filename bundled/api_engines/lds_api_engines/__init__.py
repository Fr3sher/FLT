"""API image engines — the bundled plugin.

Three cloud engines the dataset workspace generates with, pay-per-image:
Nano Banana (Gemini), ChatGPT (gpt-image — by API key, or through a ChatGPT
subscription's Codex OAuth lane) and OpenRouter (one account in front of the
same upstream models). Each registers itself in the core's engine registry
(``app/engines``), which is how the workspace cards, the batch builder, the
Setup rows, the tracked capability keys and the key-test button all learn
about it without a line of their own.

What the plugin registers through ``lds.api``:

* the three ``EngineSpec``s — order, label, rate, secret, key-test target,
  file tag, model setting key, Setup row, ``generate``, ChatGPT's pinned auth
  lane, and a readiness probe each;
* the ``chatgpt_subscription`` capabilities section (connected, for whom,
  Codex CLI detected);
* the four Codex OAuth routes under ``/api/settings/chatgpt-oauth/``.

Engine ids never change: they are on disk (the filename tag), in the database
and in localStorage. The engines' settings keys live in the core's shared
``engines`` section (a stored key never moves) and are declared in the
manifest's ``owns.config_keys_in_shared_sections``.
"""
from . import probes

__version__ = '1.0.5'


def _nanobanana_generate():
    from .nanobanana import generate_variation
    return generate_variation


def _chatgpt_generate():
    from .chatgpt_image import generate_variation
    return generate_variation


def _chatgpt_kwargs():
    # Pinned ONCE for a run: a mid-batch token refresh failure would otherwise
    # make every later row's own check see "not connected" and silently reroute
    # onto the paid API key — the feature's headline invariant.
    from .chatgpt_image import _use_subscription
    return {'force_lane': 'subscription' if _use_subscription() else 'api'}


def _openrouter_generate():
    from .openrouter import generate_variation
    return generate_variation


# Rates: the ChatGPT subscription lane spends plan quota, not dollars (the
# frontend's estimate handles it). OpenRouter is an ESTIMATE for its default
# model — the same Gemini weights Nano Banana calls, hence the same rate — and
# the only rate the user can move, since the model slug is free text.
ENGINES = (
    dict(id='nanobanana', label='Nano Banana Pro', kind='api', order=2,
         rate_usd_per_image=0.15, remote=True, billable=True,
         secret='GEMINI_API_KEY', key_test_target='gemini',
         counts_as_recommended=True, tracked_capability='Nano Banana (Gemini)',
         file_tag='NBFace', model_setting_key='nanobanana_model',
         settings_label='Nano Banana (Gemini)',
         setup_row={'label': 'Nano Banana (Gemini)',
                    'what': "Generates test images from a prompt — Google's cloud engine (API key)",
                    'topic': 'GEMINI_API_KEY'},
         generate=_nanobanana_generate, probe=probes.probe_gemini),
    dict(id='chatgpt', label='ChatGPT', kind='api', order=3,
         rate_usd_per_image=0.17, remote=True, billable=True,
         secret='OPENAI_API_KEY', key_test_target='openai',
         counts_as_recommended=True, tracked_capability='ChatGPT (gpt-image-2)',
         file_tag='GPTFace', model_setting_key='chatgpt_image_model',
         settings_label='ChatGPT (OpenAI)',
         setup_row={'label': 'ChatGPT (gpt-image-2)',
                    'what': "Generates test images — OpenAI's cloud engine (API key)",
                    'topic': 'engines.chatgpt_auth'},
         generate=_chatgpt_generate, generate_kwargs=_chatgpt_kwargs,
         probe=probes.probe_openai),
    dict(id='openrouter', label='OpenRouter', kind='api', order=4,
         rate_usd_per_image=0.15, remote=True, billable=True,
         secret='OPENROUTER_API_KEY', key_test_target='openrouter',
         counts_as_recommended=True, tracked_capability='OpenRouter',
         file_tag='ORFace', model_setting_key='openrouter_model',
         settings_label='OpenRouter',
         setup_row={'label': 'OpenRouter',
                    'what': 'Generates test images through OpenRouter-hosted models (API key)',
                    'topic': 'OPENROUTER_API_KEY'},
         generate=_openrouter_generate, probe=probes.probe_openrouter),
)


def register(ctx):
    from .routes import bp
    for spec in ENGINES:
        ctx.register_engine(**spec)
    ctx.register_probe('chatgpt_subscription', probes.chatgpt_subscription)
    ctx.register_blueprint(bp, url_prefix='/api')     # the URLs the screens already call
