"""Optional, versioned read-only interface exported by the Video product.

The SDK contains no video resolver or model policy. An OFF/absent product is
rejected before importing its package, even if it exists on Python's path.
"""

__all__ = ['VideoPublication']


def _provider():
    import importlib
    from flask import current_app, has_app_context
    from app.plugins.optional import ServiceUnavailable
    from app.plugins.registry import active
    registry = current_app.extensions.get('lds_plugins') if has_app_context() else active()
    record = registry.records.get('video') if registry is not None else None
    if record is None or not record.enabled or record.state != 'loaded':
        raise ServiceUnavailable('video_publication', 'Video is not enabled')
    module = importlib.import_module('lds_video.publication')
    if module.API_VERSION != 1:
        raise ServiceUnavailable('video_publication', 'The Video publication API is incompatible')
    return module


class VideoPublication:
    def dataset(self, user_id, dataset_id):
        return _provider().dataset(user_id, dataset_id)

    def cloud_run(self, user_id, dataset_id, run_id):
        return _provider().cloud_run(user_id, dataset_id, run_id)

    def provenance(self, user_id, dataset_id, run_id):
        return _provider().provenance(user_id, dataset_id, run_id)

    def step_files(self, user_id, dataset_id, run_id, step, final):
        return _provider().step_files(user_id, dataset_id, run_id, step, final)

    def training_progress(self, user_id, dataset_id):
        return _provider().training_progress(user_id, dataset_id)

    def verified_base(self, arch):
        return _provider().verified_base(arch)

    def split_checkpoint_name(self, name):
        return _provider().split_checkpoint_name(name)

    def is_multistage_arch(self, arch):
        return _provider().is_multistage_arch(arch)
