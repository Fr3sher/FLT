"""Read the public host's bounded safetensors header without loading weights."""


def read_safetensors_header(path):
    from app.services.fp8_export import Fp8ExportError, read_header
    try:
        return read_header(path)
    except Fp8ExportError as exc:
        raise ValueError(str(exc)) from exc


__all__ = ['read_safetensors_header']
