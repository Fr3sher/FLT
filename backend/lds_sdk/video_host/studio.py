"""Named adapters to the existing public host; no plugin implementation is imported."""

_EXPORTS = {'comfy_output_dir': ('app.services.lora_test_studio', '_comfy_output_dir'), 'is_unsafe_external_lora_name': ('app.services.lora_test_studio', '_is_unsafe_external_lora_name'), 'unsafe_lora_name': ('app.services.lora_test_studio', '_is_unsafe_external_lora_name')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
