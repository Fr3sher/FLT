DOWNLOADS = {
    'seedvr2_model': {
        'url': 'https://huggingface.co/numz/SeedVR2_comfyUI/resolve/main/seedvr2_ema_3b_fp8_e4m3fn.safetensors',
        'dest': ('SEEDVR2', 'seedvr2_ema_3b_fp8_e4m3fn.safetensors'),
        'min_free_gb': 5, 'gated': False, 'min_bytes': 512 * 1024 ** 2,
        'license_url': 'https://huggingface.co/numz/SeedVR2_comfyUI',
    },
    'seedvr2_vae': {
        'url': 'https://huggingface.co/numz/SeedVR2_comfyUI/resolve/main/ema_vae_fp16.safetensors',
        'dest': ('SEEDVR2', 'ema_vae_fp16.safetensors'),
        'min_free_gb': 1, 'gated': False, 'min_bytes': 32 * 1024 ** 2,
        'license_url': 'https://huggingface.co/numz/SeedVR2_comfyUI',
    },
}
