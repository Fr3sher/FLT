"""Reference-only H3 choices, shared by Setup and the render studio.

These files are the native Ref2VA checkpoints and task-specific LightX2V
distillations. FL2VA accelerations remain a separate catalogue.
"""

BASE_REF_OFFICIAL = 'minimax_h3_ref2va_pruned_int8_convrot.safetensors'
BASE_REF_LIGHT = 'minimax_h3_ref2va_pruned-w4a8_convrot_pruned.safetensors'
BASE_REF_EROS = '10Eros_Max_h3_ref2va_beta2_pruned_int8_convrot_skip_edges.safetensors'
REF_LORA_4 = 'minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors'
REF_LORA_8 = 'minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors'
REF_LORA_CLASS = 'LDSMiniMaxH3ReferenceLoRA'
REF_NODE_ACTION = 'h3_reference_nodes'
REF_LIMITS = {'image': 9, 'video': 3, 'audio': 3}

REF_BASES = (
    {'id': 'official', 'label': 'MiniMax H3 Ref — INT8', 'file': BASE_REF_OFFICIAL,
     'action': 'h3_ref_base', 'size_bytes': 20970379616,
     'hint': 'The official reference model, used as the quality baseline.'},
    {'id': 'light', 'label': 'MiniMax H3 Ref — W4A8', 'file': BASE_REF_LIGHT,
     'action': 'h3_ref_base_light', 'size_bytes': 12540857840,
     'hint': 'Smaller quantized weights. Requires ComfyUI 0.31 or later.'},
    {'id': 'eros', 'label': '10Eros Ref — INT8 skip-edges', 'file': BASE_REF_EROS,
     'action': 'h3_ref_base_eros', 'size_bytes': 22508017360,
     'hint': 'An optional creative fine-tune; compare reference fidelity with the official base.'},
)

REF_ACCELERATIONS = (
    {'id': 'ref4', 'label': 'LightX2V Ref4', 'file': REF_LORA_4, 'steps': 4,
     'action': 'h3_ref_turbo_4_lora', 'pack': 'reference',
     'strength': 1.0, 'shift': (12.0, 3.0), 'class_type': REF_LORA_CLASS,
     'author': 'lightx2v', 'license': 'apache-2.0',
     'hint': 'Four-step reference preview, trained at 544p. Euler / simple, shift 12/3.'},
    {'id': 'ref8', 'label': 'LightX2V Ref8 · 768p', 'file': REF_LORA_8, 'steps': 8,
     'action': 'h3_ref_turbo_8_lora', 'pack': 'reference',
     'strength': 1.0, 'shift': (12.0, 3.0), 'class_type': REF_LORA_CLASS,
     'author': 'lightx2v', 'license': 'apache-2.0',
     'hint': 'Eight-step reference generation up to 768p. Euler, shift 12/3.'},
    {'id': 'vdn', 'label': 'VDN-H3 Reference · hybrid attention',
     'file': 'stage-dmd-step-250', 'steps': 8, 'action': 'h3_vdn_stage',
     'pack': 'vdn', 'strength': 1.0, 'shift': None, 'class_type': 'ApplyVDNH3',
     'author': 'OpenVDN / Saganaki22',
     'license': 'apache-2.0 (port) · MiniMax H3 community (weights)',
     'hint': 'Experimental Reference support, one GPU. Eight steps recommended; '
             'replaces LightX2V and requires Sparse attention Off. Use W4A8 below 28 GB.'},
)


def reference_downloads():
    """Pinned HF revisions and LFS hashes, checked against the published files."""
    specs = (
        ('h3_ref_base', 'Comfy-Org/MiniMax-H3',
         '4cc1d817b6184899b41293954329f576cb5ae86b',
         'diffusion_models/' + BASE_REF_OFFICIAL, 'diffusion_models', BASE_REF_OFFICIAL,
         20970379616, '9255f52b6677845ad238f20dfaafa94727053694127ab7f255c048f0f9365779', 24),
        ('h3_ref_base_light', 'Winnougan/MiniMax-H3-INT4_Convrot_ComfyUI',
         '2b6945259df70193ab7249af5a251a69b151f6ee',
         BASE_REF_LIGHT, 'diffusion_models', BASE_REF_LIGHT,
         12540857840, '16be87247dff1f49c7141d6bcde4c0465fc254128e2de60e34aebc744a8177df', 15),
        ('h3_ref_base_eros', 'cicalooo/10Eros-Max-h3-int8-convrot',
         'dbdd87944063bc01d8062bae1dba12212ca4061f',
         BASE_REF_EROS, 'diffusion_models', BASE_REF_EROS,
         22508017360, '02d3468301d3ccb1709999ca5f184ca457286fb2641e8624ad0c7872a51830b1', 26),
        ('h3_ref_turbo_4_lora', 'lightx2v/Minimax-h3-Turbo',
         '2f015e66b37c585cea9dc4ae6f1850ea8788e742',
         REF_LORA_4, 'loras', REF_LORA_4,
         1956193000, '5b9ab5ade15d0775676d01a907268a69a1468dc6033b3b0d3ded5502f3ebb84c', 3),
        ('h3_ref_turbo_8_lora', 'lightx2v/Minimax-h3-Turbo',
         '2f015e66b37c585cea9dc4ae6f1850ea8788e742',
         REF_LORA_8, 'loras', REF_LORA_8,
         1956193000, '6a56f41ab4229c9dd845b9501bbd475ee57e112d846cf2e819d534a1ae928c5a', 3),
    )
    return {action: {
        'url': f'https://huggingface.co/{repo}/resolve/{revision}/{source}',
        'dest': (folder, filename), 'min_free_gb': free_gb,
        'gated': False, 'min_bytes': size, 'expected_bytes': size,
        'sha256': sha256, 'license_url': f'https://huggingface.co/{repo}',
    } for action, repo, revision, source, folder, filename, size, sha256, free_gb in specs}

__all__ = [
    'BASE_REF_EROS',
    'BASE_REF_LIGHT',
    'BASE_REF_OFFICIAL',
    'REF_ACCELERATIONS',
    'REF_BASES',
    'REF_LIMITS',
    'REF_LORA_4',
    'REF_LORA_8',
    'REF_LORA_CLASS',
    'REF_NODE_ACTION',
    'reference_downloads',
]
