"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'MIN_FREE_GB_TRAIN': ('app.services.lora_training', 'MIN_FREE_GB_TRAIN'),
 '_PROG_LOG_MAX_BYTES': ('app.services.lora_training', '_PROG_LOG_MAX_BYTES'),
 '_TRAIN_STATE_TTL': ('app.services.lora_training', '_TRAIN_STATE_TTL'),
 '_aitoolkit_dir': ('app.services.lora_training', '_aitoolkit_dir'),
 '_assert_no_vision_pass_on_gpu': ('app.services.lora_training', '_assert_no_vision_pass_on_gpu'),
 '_clear_training_identity': ('app.services.lora_training', '_clear_training_identity'),
 '_comfyui_free_before_training': ('app.services.lora_training', '_comfyui_free_before_training'),
 '_comfyui_free_report': ('app.services.lora_training', '_comfyui_free_report'),
 '_jobs_dir': ('app.services.lora_training', '_jobs_dir'),
 '_output_dir': ('app.services.lora_training', '_output_dir'),
 '_parse_training_log': ('app.services.lora_training', '_parse_training_log'),
 '_queue_lock': ('app.services.lora_training', '_queue_lock'),
 '_record_training_process_identity': ('app.services.lora_training', '_record_training_process_identity'),
 '_serial_local_launch': ('app.services.lora_training', '_serial_local_launch'),
 '_training_process_is_definitely_dead': ('app.services.lora_training',
                                          '_training_process_is_definitely_dead'),
 '_venv_python': ('app.services.lora_training', '_venv_python'),
 '_watch_training': ('app.services.lora_training', '_watch_training'),
 'assert_free_disk': ('app.services.lora_training', 'assert_free_disk'),
 'assert_interpreter_ready': ('app.services.lora_training', 'assert_interpreter_ready'),
 'export_dataset_to_aitoolkit': ('app.services.lora_training', 'export_dataset_to_aitoolkit'),
 'free_disk_gb': ('app.services.lora_training', 'free_disk_gb'),
 'is_installed': ('app.services.lora_training', 'is_installed'),
 'parse_download_progress': ('app.services.lora_training', 'parse_download_progress'),
 'secrets': ('app.services.lora_training', 'secrets'),
 'stop_training': ('app.services.lora_training', 'stop_training'),
 'training_subprocess_env': ('app.services.lora_training', 'training_subprocess_env')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
