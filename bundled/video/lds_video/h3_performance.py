"""Optional H3 render controls, owned and recorded by Video."""
from lds_sdk import h3_render as host

FUSED_MODEL = 'minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors'
SPECTRUM = 'SpectrumApplyMiniMaxH3'
FAST_WRITER = 'LDSH3FastWriteVideo'


def reference_status(classes=None, comfy_version=None):
    from lds_sdk.h3_reference_catalog import REF_LORA_CLASS
    result = host.reference_status(classes, comfy_version)
    present = host.weight_present(('diffusion_models', 'unet'), FUSED_MODEL)
    shared_missing = [item for item in result.get('missing_weights', []) if item.get('required')]
    core_missing = [name for name in result.get('missing_nodes', []) if name != REF_LORA_CLASS]
    nodes_ready = classes is not None and not core_missing
    for base in result.get('bases', []):
        base['nodes_ready'] = nodes_ready
    result['bases'] = [*result.get('bases', []), {
        'id': 'fused', 'label': 'H3 Fused Turbo · INT8', 'file': FUSED_MODEL,
        'available': present, 'ready': present and nodes_ready and not shared_missing,
        'weight_present': present, 'nodes_ready': nodes_ready, 'action': None,
        'missing_weights': shared_missing + ([] if present else [{'action': None, 'filename': FUSED_MODEL,
            'what': 'H3 Fused Turbo', 'required': True, 'place_in': 'models/diffusion_models/'}]),
        'hint': 'Turbo is already merged. Start at 8 steps; no acceleration LoRA. '
                'Uses the existing Fused weight in models/diffusion_models.',
    }]
    from . import clipproj
    return clipproj.reference_status(result, classes)


def status(classes):
    from lds_sdk.video_host.comfyui import fetch_node_info
    known = classes is not None
    classes = set(classes or ())
    sage_class = next((c for c in (host.BLOCK_ATTN_CLASS, 'MiniMaxH3BlockAttentionSplit')
                       if c in classes), None)
    backends = host.block_attention_backends(fetch_node_info(sage_class)) if sage_class else []
    return {
        'fused': {'available': host.weight_present(('diffusion_models', 'unet'), FUSED_MODEL),
                  'filename': FUSED_MODEL},
        'sage': {'available': host.ATTN_SAGE in backends if known else None,
                 'action': host.BLOCK_ATTN_INSTALL_ACTION,
                 'hint': 'Needs the H3 attention switch and a SageAttention backend in ComfyUI.'},
        'spectrum': {'available': SPECTRUM in classes if known else None,
                     'action': 'h3_spectrum_nodes'},
        'int8': {'available': host.weight_present(('vae',), host.VIDEO_VAE_INT8),
                 'action': 'h3_video_vae_int8'},
        'fast': {'available': bool({FAST_WRITER, 'H3FastWriteVideo'} & classes) if known else None,
                 'action': 'h3_fast_writer'},
    }


def validate(*, fused=False, h3_attention='auto', h3_spectrum=False,
             h3_video_vae='fp16', h3_video_writer='native', **options):
    if type(fused) is not bool or type(h3_spectrum) is not bool:
        raise ValueError('Fused Turbo and Spectrum must be true or false.')
    if h3_attention not in ('auto', 'native', 'sage'):
        raise ValueError('Choose automatic, native or H3 Sage attention.')
    if h3_video_vae not in ('fp16', 'int8') or h3_video_writer not in ('native', 'fast'):
        raise ValueError('Choose FP16/INT8 decoding and native/fast MP4 recording.')
    if fused and (options.get('accel') or options.get('turbo') or options.get('eros') or options.get('light')):
        raise ValueError('H3 Fused Turbo already includes acceleration. Turn off the other base and acceleration choices.')
    if (h3_attention == 'sage' or h3_spectrum) and (options.get('sparse') or options.get('accel') == 'vdn'):
        raise ValueError('H3 Sage / Spectrum require Sparse off and no VDN-H3 acceleration.')


def insert(wf, node_id, node, previous):
    # All consumers, including scheduler and latent-upscale guider, must see
    # the same model. Do not rewire the newly inserted node into itself.
    for entry in wf.values():
        for key, value in entry.get('inputs', {}).items():
            if value == previous:
                entry['inputs'][key] = [node_id, 0]
    wf[node_id] = node


def apply(built, *, fused, h3_attention, h3_spectrum, h3_video_vae, h3_video_writer,
          classes=None, mode=None):
    wf = built['workflow']
    classes = set(classes or ())
    if fused:
        wf[host.N_UNET]['inputs']['unet_name'] = FUSED_MODEL
        previous = wf[host.N_GUIDER]['inputs']['model']
        insert(wf, '1300', {'class_type': 'MiniMaxH3SigmaShift', 'inputs': {
            'model': previous, 'shift_video': 12.0, 'shift_audio': 3.0}}, previous)
        wf[host.N_SAMPLER_SELECT]['inputs']['sampler_name'] = 'euler'
        wf[host.N_SCHEDULER]['inputs']['scheduler'] = 'simple'
        built['base'] = FUSED_MODEL
        built['generation_settings']['base_model'] = FUSED_MODEL
        if mode == 'ref2va':
            built['generation_settings']['ref_base'] = 'fused'
        built['notes'].append('H3 Fused Turbo: integrated acceleration, shift 12/3')
    if h3_attention == 'sage':
        node_class = next((c for c in (host.BLOCK_ATTN_CLASS, 'MiniMaxH3BlockAttentionSplit')
                           if c in classes), host.BLOCK_ATTN_CLASS)
        previous = wf[host.N_GUIDER]['inputs']['model']
        insert(wf, '1301', {'class_type': node_class, 'inputs': {
            'model': previous, 'edge_backend': host.ATTN_PYTORCH,
            'middle_backend': host.ATTN_SAGE, 'head_pct': 0.0, 'tail_pct': 0.0}}, previous)
    if h3_spectrum:
        previous = wf[host.N_GUIDER]['inputs']['model']
        insert(wf, '1302', {'class_type': SPECTRUM, 'inputs': {
            'model': previous, 'enabled': True, 'blend_weight': 0.5,
            'degree': 1, 'ridge_lambda': 0.1, 'window_size': 2.0,
            'flex_window': 0.75, 'warmup_steps': 1, 'tail_actual_steps': 1,
            'max_history': 8, 'debug': False, 'history_storage': 'system_ram',
            'bootstrap_first_forecast': True}}, previous)
    if h3_video_writer == 'fast':
        create = wf[host.N_CREATE_VIDEO]['inputs']
        inputs = {'images': create['images'], 'fps': create['fps'],
                  'filename_prefix': wf[host.N_SAVE]['inputs']['filename_prefix'],
                  'crf': 16, 'preset': 'veryfast', 'async_write': False, 'chunk_frames': 32}
        if 'audio' in create:
            inputs['audio'] = create['audio']
        wf[host.N_SAVE] = {'class_type': (FAST_WRITER if FAST_WRITER in classes or 'H3FastWriteVideo' not in classes
                                        else 'H3FastWriteVideo'), 'inputs': inputs}
    settings = dict(fused=fused, h3_attention=h3_attention, h3_spectrum=h3_spectrum,
                    h3_video_vae=h3_video_vae, h3_video_writer=h3_video_writer)
    built['generation_settings'].update(settings)
    return built
