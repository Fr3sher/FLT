"""Public H3 assets shared by independently prepared local products."""
from copy import deepcopy
from app.setup_installer import _H3_DOWNLOADS
H3_DOWNLOADS = {key: deepcopy(_H3_DOWNLOADS[key]) for key in (
    'h3_base', 'h3_text_encoder', 'h3_video_vae', 'h3_audio_vae', 'h3_turbo_lora',
    'h3_parasyte_lora', 'h3_dareties_lora')}
__all__ = ['H3_DOWNLOADS']
