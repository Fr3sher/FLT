"""Named shared operations for gpu_speed."""

__all__ = ['speed_factor', 'estimate_minutes', 'video_estimate_minutes']



def speed_factor(gpu_name: str):
    from app.services.gpu_speed import speed_factor as operation
    return operation(gpu_name)



def estimate_minutes(gpu_name: str, family: str, steps: int):
    from app.services.gpu_speed import estimate_minutes as operation
    return operation(gpu_name, family, steps)



def video_estimate_minutes(gpu_name, frames, steps):
    from app.services.gpu_speed import video_estimate_minutes as operation
    return operation(gpu_name, frames, steps)
