"""Video-owned downloads for the existing public V2 host."""
from lds_sdk.h3_downloads import H3_DOWNLOADS as HOST_DOWNLOADS

CHIMERA_DOWNLOADS = {'h3_taomate_lora': {'url': 'https://huggingface.co/CZMartin22/TaoMate-H3-3step-ComfyUI/resolve/3fc6fda82a6684543235b38bcd45f075530ed1c6/TaoMate-H3-3step-ComfyUI.safetensors',
                     'dest': ('loras', 'TaoMate-H3-3step-ComfyUI.safetensors'),
                     'min_free_gb': 2,
                     'min_bytes': 1073741824,
                     'gated': False,
                     'expected_bytes': 1240539224,
                     'sha256': '908d6c9a8d4cb7311b9b48aece606a1d29033f07e2ef23676f8404acc07d5173',
                     'license_url': 'https://huggingface.co/CZMartin22/TaoMate-H3-3step-ComfyUI'},
 'h3_fasth3_lora': {'url': 'https://huggingface.co/drozbay/MiniMax-H3-FastH3-Preview-LoRA/resolve/main/loras/minimax_h3_fl2va_fasth3_preview_v0.2_lora_pruned_rank128_fp16.safetensors',
                    'dest': ('loras',
                             'minimax_h3_fasth3_v0.2_rank128_drozbay.safetensors'),
                    'legacy_names': ('minimax_h3_fl2va_fasth3_preview_v0.2_lora_pruned_rank128_fp16.safetensors',),
                    'min_free_gb': 2,
                    'min_bytes': 1073741824,
                    'gated': False,
                    'expected_bytes': 1333483008,
                    'sha256': '260616f7f60f698eb601dec376de00e3a0ba4e8c6cdc85673a5808b8bda4594c',
                    'license_url': 'https://huggingface.co/drozbay/MiniMax-H3-FastH3-Preview-LoRA'}}
from .clipproj import DOWNLOADS as CLIPPROJ_DOWNLOADS

H3_DOWNLOADS = {**HOST_DOWNLOADS, **CHIMERA_DOWNLOADS, **CLIPPROJ_DOWNLOADS}
