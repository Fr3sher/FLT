"""Local workflow staging and admission to the host's existing image queue."""


def load_workflow(path):
    from app.utils.comfyui import load_workflow_local
    return load_workflow_local(path)


def ensure_input_usable(path):
    from app.utils import comfy_fs
    return comfy_fs.ensure_input_usable(path)


def stage_input_image(source_path, destination_name, input_dir):
    from app.utils import comfy_fs
    return comfy_fs.stage_input_image(source_path, destination_name, input_dir)


class _Queue:
    def add_job(self, *, job_type, user_id, workflow_data, prompt, job_id, metadata):
        """Preserve the host's GPU admission, persistence and completion routing."""
        from app.job_queue import queue_manager
        return queue_manager.add_job(
            job_type=job_type, user_id=user_id, workflow_data=workflow_data,
            prompt=prompt, job_id=job_id, metadata=metadata)


queue = _Queue()


__all__ = ['ensure_input_usable', 'load_workflow', 'queue', 'stage_input_image']
