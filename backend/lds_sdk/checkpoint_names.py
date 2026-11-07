"""Named shared operations for checkpoint_names."""

__all__ = ['restage_checkpoint_name', 'split_checkpoint_name', 'group_saves_by_step']



def restage_checkpoint_name(base: str, step, stage):
    from app.services.checkpoint_names import restage_checkpoint_name as operation
    return operation(base, step, stage)



def split_checkpoint_name(filename):
    from app.services.checkpoint_names import split_checkpoint_name as operation
    return operation(filename)



def group_saves_by_step(saves, target=None):
    from app.services.checkpoint_names import group_saves_by_step as operation
    return operation(saves, target)
