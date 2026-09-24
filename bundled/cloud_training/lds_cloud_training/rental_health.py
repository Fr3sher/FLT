"""Recognize confirmed startup faults without treating slow progress as failure."""
import re


def image_cuda_floor(image):
    match = re.search(r'cuda[-_](\d+\.\d+)', str(image or ''), re.I)
    return float(match[1]) if match else 0


def boot_failure(instance):
    if not instance or instance.get('actual_status') in ('running', 'loading'):
        return None
    text = str(instance.get('status_msg') or '').lower()
    if 'unresolvable cdi devices' in text or 'failed to inject cdi devices' in text:
        return 'the host cannot attach its GPU to the container'
    if 'driver failed programming external connectivity' in text:
        return 'the host cannot publish the container ports'
    if 'nvidia-container-cli' in text and 'initialization error' in text:
        return 'the host NVIDIA runtime could not initialize'
    return None


def gpu_startup_failure(log):
    # Only the last meaningful line: an old traceback followed by resumed
    # loading/training is not a current failure. Duplicated worker stderr is OK.
    lines = str(log or '').strip().splitlines()
    tail = lines[-1].lower() if lines else ''
    if 'cuda unknown error' in tail:
        return 'CUDA cannot access the GPU on this host'
    if any(marker in tail for marker in (
            'no cuda gpus are available', 'found no nvidia driver',
            'cuda driver version is insufficient', 'cuda error: initialization error')):
        return 'the host GPU driver cannot initialize CUDA'
    return None
