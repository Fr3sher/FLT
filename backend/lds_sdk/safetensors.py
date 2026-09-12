"""Read the public host's bounded safetensors header without loading weights."""


def read_safetensors_header(path):
    from app.services.lora_training import _read_safetensors_header
    return _read_safetensors_header(path)


__all__ = ['read_safetensors_header']
