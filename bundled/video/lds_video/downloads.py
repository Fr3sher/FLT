"""Only the seven public H3 downloads are offered by Video."""
from lds_sdk.h3_downloads import H3_DOWNLOADS as _SHARED

PUBLIC_ACTIONS = ('h3_base', 'h3_text_encoder', 'h3_video_vae', 'h3_audio_vae', 'h3_turbo_lora', 'h3_parasyte_lora', 'h3_dareties_lora')
H3_DOWNLOADS = {key: _SHARED[key] for key in PUBLIC_ACTIONS}
