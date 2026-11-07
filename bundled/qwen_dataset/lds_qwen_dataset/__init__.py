"""Dataset Forge: an autonomous local dataset engine using Qwen-Image 2.1."""


def register(ctx):
    from . import assets, engine, graph

    ctx.register_config_defaults(graph.DEFAULTS)
    assets.register(ctx)
    ctx.register_probe('qwen_dataset', engine.probe)
    ctx.register_probe('comfyui.qwen_dataset_missing', lambda: assets.inspect_assets()['missing'])
    ctx.register_probe('comfyui.qwen_dataset_invalid', lambda: assets.inspect_assets()['invalid'])
    ctx.register_probe('comfyui.qwen_dataset_ready', lambda: engine.probe()['ok'])
    ctx.register_engine(
        id='qwen_dataset', label='Qwen-Image 2.1', kind='local', order=1,
        file_tag='qwen_dataset', tracked_capability='Dataset Forge (Qwen-Image 2.1)',
        counts_as_recommended=True, probe=engine.probe,
        local_preflight=engine.preflight, local_enqueue=engine.enqueue,
        extra={'supports_reference_edit': False},
    )
