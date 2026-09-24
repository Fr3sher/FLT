"""Named shared operations for zimage_convert."""

__all__ = ['converted_dir', 'is_converted']



def converted_dir(z_model: str):
    from app.services.zimage_convert import converted_dir as operation
    return operation(z_model)



def is_converted(z_model: str):
    from app.services.zimage_convert import is_converted as operation
    return operation(z_model)
