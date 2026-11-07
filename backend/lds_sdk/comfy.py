"""Local workflow staging and admission to the host's existing image queue."""

__all__ = ['load_workflow', 'ensure_input_usable', 'stage_input_image', 'queue', 'clear_model_caches', 'render_progress',
           'add_plugin_job', 'plugin_job', 'cancel_plugin_job']


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


def clear_model_caches():
    from app.utils.comfyui import clear_model_caches as operation
    return operation()


def render_progress():
    """Cached progress of the host's current GPU job, identified by its prompt."""
    from app.services import comfyui_console, queue_view
    return comfyui_console.render_progress(*queue_view.gpu_job())


def add_plugin_job(plugin_id, kind, *, user_id, workflow_data, prompt, job_id, metadata=None):
    """API 1.13: enqueue a registered product's work through host admission.

    The product persists its own intent before this call. The fixed job ID lets
    it reconcile a crash without resubmitting a possibly running generation.
    """
    from flask import current_app
    from .lifecycle import is_available, state_change_lock
    from app.job_queue import queue_manager
    if not isinstance(plugin_id, str) or not isinstance(kind, str) or not kind.startswith('is_'):
        raise ValueError('Expected a registered product and completion kind.')
    if not isinstance(metadata or {}, dict):
        raise ValueError('Expected job metadata.')
    extra = dict(metadata or {})
    if any(not isinstance(key, str) or key.startswith('is_')
           or key in ('plugin_id', 'plugin_job_kind', 'lds_plugin_job') for key in extra):
        raise ValueError('Completion ownership is assigned by the host.')
    with state_change_lock:
        registry = current_app.extensions.get('lds_plugins')
        handler = registry.job_handlers.get(kind) if registry else None
        if (not isinstance(kind, str) or not kind.startswith('is_') or handler is None
                or handler[0] != plugin_id or not is_available(plugin_id)):
            raise ValueError('Enable the product before starting this operation.')
        extra.update({kind: True, 'plugin_id': plugin_id, 'plugin_job_kind': kind, 'lds_plugin_job': True})
        return queue_manager.add_job(job_type='image', user_id=str(user_id),
                                     workflow_data=workflow_data, prompt=prompt,
                                     job_id=job_id, metadata=extra)


def _plugin_row(plugin_id, job_id, user_id):
    import json
    from app.models import ImageGenerationQueue
    row = ImageGenerationQueue.query.filter_by(job_id=str(job_id), user_id=str(user_id)).populate_existing().first()
    if row is None:
        return None
    try:
        metadata = json.loads(row.job_metadata or '{}')
    except (ValueError, TypeError):
        return None
    if (not isinstance(metadata, dict) or metadata.get('lds_plugin_job') is not True
            or metadata.get('plugin_id') != plugin_id
            or not isinstance(metadata.get('plugin_job_kind'), str)
            or metadata.get(metadata['plugin_job_kind']) is not True):
        return None
    return row


def plugin_job(plugin_id, job_id, user_id):
    """Read only a product's owned durable queue row, including after disable."""
    row = _plugin_row(plugin_id, job_id, user_id)
    if row is None:
        return None
    return {'job_id': row.job_id, 'status': row.status,
            'result_filename': row.result_filename, 'error': row.error_message,
            'comfy_prompt_id': row.comfyui_prompt_id}


def cancel_plugin_job(plugin_id, job_id, user_id):
    """Return the host's precise outcome; uncertain GPU work remains retained."""
    if _plugin_row(plugin_id, job_id, user_id) is None:
        raise LookupError('Product job not found.')
    from app.job_queue import queue_manager
    return queue_manager.cancel_job_outcome(str(job_id), str(user_id))
