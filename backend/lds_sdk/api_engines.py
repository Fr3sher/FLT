"""Optional API Engines integration v1; OFF never imports the provider package."""


def _provider():
    import importlib
    from flask import current_app, has_app_context
    from app.plugins.optional import ServiceUnavailable
    from app.plugins.registry import active
    registry = current_app.extensions.get('lds_plugins') if has_app_context() else active()
    record = registry.records.get('api_engines') if registry else None
    from lds_sdk.config import get
    disabled = (get('plugins.enabled') or {}).get('api_engines') is False
    if disabled or record is None or not record.enabled or record.state != 'loaded':
        raise ServiceUnavailable('api_engines', 'API Engines is not enabled')
    try:
        module = importlib.import_module('lds_api_engines.public_api_v1')
    except ImportError as exc:
        raise ServiceUnavailable('api_engines', 'API Engines could not be loaded') from exc
    if module.API_VERSION != 1:
        raise ServiceUnavailable('api_engines', 'The API Engines integration API is incompatible')
    return module


def available():
    from app.plugins.optional import ServiceUnavailable
    try:
        _provider()
    except ServiceUnavailable:
        return False
    return True


class ChatGPT:
    def __bool__(self):
        return available()

    def status(self):
        return _provider().chatgpt_status()

    def model_name(self):
        return _provider().chatgpt_model_name()

    def generate_text(self, prompt, *, instructions='Answer with the requested text only.',
                      image=None, images=None, model=None):
        return _provider().chatgpt_generate_text(prompt, instructions=instructions,
                                                image=image, images=images, model=model)


chatgpt = ChatGPT()


__all__ = ['available', 'ChatGPT', 'chatgpt']
