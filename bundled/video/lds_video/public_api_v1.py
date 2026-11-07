"""Public Video integration API v1 for training, deployment and live recovery.

The complete product remains here. The host exposes an enabled-product adapter,
not copies of Video training or rendering policy.
"""
API_VERSION = 1

def build_job_config(*args, **kwargs):
    from .video_training import build_job_config
    return build_job_config(*args, **kwargs)


def image_supports_training_adapter(*args, **kwargs):
    from .video_training import image_supports_training_adapter
    return image_supports_training_adapter(*args, **kwargs)


def image_supports_ref2va(*args, **kwargs):
    from .video_training import image_supports_ref2va
    return image_supports_ref2va(*args, **kwargs)


def job_name_for(*args, **kwargs):
    from .video_training import job_name_for
    return job_name_for(*args, **kwargs)


def training_controls(*args, **kwargs):
    from .video_training import training_controls
    return training_controls(*args, **kwargs)


def get_target(*args, **kwargs):
    from .video_targets import get
    return get(*args, **kwargs)


def record(*args, **kwargs):
    from .video_run_lineage import record
    return record(*args, **kwargs)


def harvested_steps(*args, **kwargs):
    from .video_run_lineage import harvested_steps
    return harvested_steps(*args, **kwargs)


def reference_dirs(*args, **kwargs):
    from .video_bank_service import reference_dirs
    return reference_dirs(*args, **kwargs)


def deployment_spec():
    from . import video_test_studio as studio
    return {'base_workflow': studio.load_base_workflow(),
            'sage_class': studio.SAGE_CLASS,
            'block_attention_class': studio.BLOCK_ATTN_CLASS,
            'option_node_packs': dict(studio.OPTION_NODE_PACKS)}


def session():
    from lds_sdk import live_services
    return live_services.session()


def block_attention_backends(node_info):
    from . import video_test_studio
    return video_test_studio.block_attention_backends(node_info)
