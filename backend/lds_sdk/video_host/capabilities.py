"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'CAPABILITY_IMPORTS': ('app.capabilities', 'CAPABILITY_IMPORTS'),
 '_cached_import': ('app.capabilities', '_cached_import'),
 'bank_scoring_gpu_available': ('app.capabilities', 'bank_scoring_gpu_available'),
 'probe_comfyui': ('app.capabilities', 'probe_comfyui'),
 'probe_lmstudio_model': ('app.capabilities', 'probe_lmstudio_model'),
 'probe_ollama_model': ('app.capabilities', 'probe_ollama_model'),
 'probe_video': ('app.capabilities', 'probe_video'),
 'probe_video_text': ('app.capabilities', 'probe_video_text'),
 'probe_watermark_detect': ('app.capabilities', 'probe_watermark_detect'),
 'watermark_detect_gpu_available': ('app.capabilities', 'watermark_detect_gpu_available')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
