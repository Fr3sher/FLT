"""Closed hardware profiles shared by provider admission and the owned runtime."""

__all__ = ['GPU_COUNTS', 'gpu_count', 'DEFAULT', 'RTX5090', 'validate', 'select',
           'minimum_vram_gb', 'minimum_host_ram_gb', 'gpu_names', 'parallelism']

GPU_COUNTS = (1, 2, 4)


def gpu_count(value):
    if type(value) is not int or value not in GPU_COUNTS:
        raise ValueError("Select exactly one, two or four cooperating GPUs")
    return value


DEFAULT = "h200-resident"
RTX5090 = "rtx5090-tp2-offload"


def validate(profile_id, gpus):
    if type(gpus) is not int or gpus not in (1, 2, 4):
        raise ValueError("Select exactly one, two or four cooperating GPUs")
    if type(profile_id) is not str or profile_id not in (DEFAULT, RTX5090):
        raise ValueError("Unknown native hardware profile")
    if profile_id == RTX5090 and gpus != 2:
        raise ValueError("The RTX 5090 native profile requires exactly two GPUs")
    return profile_id


def select(gpu_name, gpus):
    if type(gpu_name) is not str:
        raise ValueError("Select a supported native GPU model")
    if gpu_name in ("H200", "H200 NVL"):
        return validate(DEFAULT, gpus)
    if gpu_name == "RTX 5090":
        return validate(RTX5090, gpus)
    raise ValueError("Select a supported native GPU model")


def minimum_vram_gb(profile_id):
    validate(profile_id, 2)
    return 31 if profile_id == RTX5090 else 135


def minimum_host_ram_gb(profile_id, gpus):
    validate(profile_id, gpus)
    # Provider catalogue GB; no extra physical-RAM veto on the nominal class.
    return 412 if profile_id == RTX5090 else 128 * gpus


def gpu_names(gpus):
    validate(DEFAULT, gpus)
    return ("H200", "H200 NVL", "RTX 5090") if gpus == 2 else ("H200", "H200 NVL")


def parallelism(profile_id, gpus):
    validate(profile_id, gpus)
    return {"tp": 2, "sp": 1, "ulysses": 1} if profile_id == RTX5090 else {
        "tp": 1, "sp": gpus, "ulysses": gpus}
