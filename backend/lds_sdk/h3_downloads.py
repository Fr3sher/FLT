"""Public H3 assets shared by independently prepared local products."""
H3_DOWNLOADS = {
    'h3_base': {
        'url': 'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors',
        'dest': ('diffusion_models', 'minimax_h3_fl2va_pruned_int8_convrot.safetensors'),
        'min_free_gb': 24, 'gated': False, 'min_bytes': 8 * 1024 ** 3,
        'license_url': 'https://huggingface.co/Comfy-Org/MiniMax-H3',
    },
    'h3_text_encoder': {
        'url': 'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',
        'dest': ('text_encoders', 'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors'),
        'min_free_gb': 19, 'gated': False, 'min_bytes': 6 * 1024 ** 3,
        'license_url': 'https://huggingface.co/Comfy-Org/MiniMax-H3',
    },
    'h3_video_vae': {
        'url': 'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors',
        'dest': ('vae', 'minimax_h3_video_vae_fp16.safetensors'),
        'min_free_gb': 8, 'gated': False, 'min_bytes': 2 * 1024 ** 3,
        'license_url': 'https://huggingface.co/Comfy-Org/MiniMax-H3',
    },
    # Small, and not optional despite it: H3 emits video and audio in ONE latent,
    # so the graph decodes both. Without this the render stops at the decode.
    'h3_audio_vae': {
        'url': 'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors',
        'dest': ('vae', 'minimax_h3_audio_vae_fp32.safetensors'),
        'min_free_gb': 3, 'gated': False, 'min_bytes': 128 * 1024 ** 2,
        'license_url': 'https://huggingface.co/Comfy-Org/MiniMax-H3',
    },
    # The 6-step distillation LoRA (larryvrh, apache-2.0, not gated - checked on
    # the hub; row 1 of the multimodalart H3 acceleration arena). Optional in
    # the sense that the lane runs without it, at twenty steps instead of six:
    # the difference between a clip in minutes and a clip in tens of minutes,
    # which is why the choice defaults to it wherever it CAN run.
    'h3_turbo_lora': {
        'url': 'https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora/resolve/main/minimax_h3_turbo_v4_step600_ema.safetensors',
        'dest': ('loras', 'minimax_h3_turbo_v4_step600_ema.safetensors'),
        'min_free_gb': 3, 'gated': False, 'min_bytes': 128 * 1024 ** 2,
        'license_url': 'https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora',
    },
    # ⚡ The other two accelerations of the Render panel — rows 2 and 3 of the
    # same arena, statistical ties with larryvrh's. Ordinary LoRAs for the
    # stock loader: no node pack. Parasyte is MIT (checked on the hub). The
    # DARE-TIES merge combines LightX2V v0.1 and larryvrh v4 (both apache-2.0)
    # but its own repo states no license — the panel says so, in words.
    'h3_parasyte_lora': {
        'url': 'https://huggingface.co/Plaguekind/H3-Lora/resolve/main/H3-PK-Parasyte-Turbo.safetensors',
        'dest': ('loras', 'H3-PK-Parasyte-Turbo.safetensors'),
        'min_free_gb': 5, 'gated': False, 'min_bytes': 1024 ** 3,
        'license_url': 'https://huggingface.co/Plaguekind/H3-Lora',
    },
    'h3_dareties_lora': {
        'url': 'https://huggingface.co/silveroxides/MiniMax-H3_tests/resolve/main/minimax_h3_fl2v_lightx2v_v0.1_dareties_v4_step600_comfy_fro.safetensors',
        'dest': ('loras', 'minimax_h3_fl2v_lightx2v_v0.1_dareties_v4_step600_comfy_fro.safetensors'),
        'min_free_gb': 3, 'gated': False, 'min_bytes': 512 * 1024 ** 2,
        'license_url': 'https://huggingface.co/silveroxides/MiniMax-H3_tests',
    },
}
__all__ = ['H3_DOWNLOADS']
