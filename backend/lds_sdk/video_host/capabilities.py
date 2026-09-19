"""Named capabilities operations shared with the host; no module handle escapes."""

def probe_comfyui(*args, **kwargs):
    from app.capabilities import probe_comfyui
    return probe_comfyui(*args, **kwargs)


def probe_lmstudio_model(*args, **kwargs):
    from app.capabilities import probe_lmstudio_model
    return probe_lmstudio_model(*args, **kwargs)


def probe_ollama_model(*args, **kwargs):
    from app.capabilities import probe_ollama_model
    return probe_ollama_model(*args, **kwargs)


def probe_video(*args, **kwargs):
    from app.capabilities import probe_video
    return probe_video(*args, **kwargs)


def probe_video_text(*args, **kwargs):
    from app.capabilities import probe_video_text
    return probe_video_text(*args, **kwargs)


def bank_scoring_gpu_available(*args, **kwargs):
    from app.capabilities import bank_scoring_gpu_available
    return bank_scoring_gpu_available(*args, **kwargs)


def probe_watermark_detect(*args, **kwargs):
    from app.capabilities import probe_watermark_detect
    return probe_watermark_detect(*args, **kwargs)


def watermark_detect_gpu_available(*args, **kwargs):
    from app.capabilities import watermark_detect_gpu_available
    return watermark_detect_gpu_available(*args, **kwargs)



__all__ = ['probe_comfyui', 'probe_lmstudio_model', 'probe_ollama_model', 'probe_video', 'probe_video_text', 'bank_scoring_gpu_available', 'probe_watermark_detect', 'watermark_detect_gpu_available', 'video_decoder_ready']


def video_decoder_ready(python):
    from app import capabilities
    return capabilities._cached_import('video_decode', python, capabilities.CAPABILITY_IMPORTS['video'])


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'CAPABILITY_IMPORTS': ('app.capabilities', 'CAPABILITY_IMPORTS'),
 '_cached_import': ('app.capabilities', '_cached_import'),
 'bank_scoring_gpu_available': ('app.capabilities',
                                'bank_scoring_gpu_available'),
 'probe_comfyui': ('app.capabilities', 'probe_comfyui'),
 'probe_lmstudio_model': ('app.capabilities', 'probe_lmstudio_model'),
 'probe_ollama_model': ('app.capabilities', 'probe_ollama_model'),
 'probe_video': ('app.capabilities', 'probe_video'),
 'probe_video_text': ('app.capabilities', 'probe_video_text'),
 'probe_watermark_detect': ('app.capabilities', 'probe_watermark_detect'),
 'watermark_detect_gpu_available': ('app.capabilities',
                                    'watermark_detect_gpu_available')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
