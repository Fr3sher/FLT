"""The Video plugin's default H3 prompt encoder and its complete installation."""
from lds_sdk import h3_render as host

ENCODER = 'qwen3vl_4b_fp8_scaled.safetensors'
PROJECTION = 'mmh3-4b-ClipProj-v3.1.safetensors'
NODE = 'ClipProjApply'
NODE_ID = '1310'
DOWNLOADS = {
    'h3_text_encoder': {
        'url': 'https://huggingface.co/Comfy-Org/Krea-2/resolve/eb1eddd3983a54678545a9b2c178c5853b30f7be/text_encoders/' + ENCODER,
        'dest': ('text_encoders', ENCODER), 'min_free_gb': 7, 'gated': False,
        'min_bytes': 5_000_000_000, 'expected_bytes': 5242467968,
        'sha256': '54bd5144df0bbc25dd6ccadfcb826b521445a1b06ae5a42570bdd2974ca87094',
        'license_url': 'https://huggingface.co/Comfy-Org/Krea-2',
    },
    'h3_clip_projection': {
        'url': 'https://huggingface.co/jhong520/ClipProj-MiniMax-H3/resolve/5246fbaea31927645e032ece5ecba1966468f70b/' + PROJECTION,
        'dest': ('clip_projections', PROJECTION), 'min_free_gb': 1, 'gated': False,
        'min_bytes': 26_000_000, 'expected_bytes': 26256128,
        'sha256': '0184e5c8d666a131962506d21949c2d8a8c6f33445b7b5e347e9a7e0a5baa819',
        'license_url': 'https://huggingface.co/jhong520/ClipProj-MiniMax-H3',
    },
}


def apply(built):
    graph = built['workflow']
    graph['13']['inputs'].update(clip_name=ENCODER, type='krea2', device='default')
    for node in graph.values():
        if node['inputs'].get('clip') == ['13', 0]:
            node['inputs']['clip'] = [NODE_ID, 0]
    graph[NODE_ID] = {'class_type': NODE, 'inputs': {'clip': ['13', 0], 'projection': PROJECTION}}
    built['generation_settings'].update(text_encoder=ENCODER, clip_projection=PROJECTION)
    built['notes'].append('prompt encoder: Qwen3-VL 4B FP8 + ClipProj v3.1')
    return built


def missing_weights(rows, classes=None):
    actions = {'h3_text_encoder', 'h3_clip_projection', 'h3_clipproj_nodes'}
    rows = [row for row in rows if row.get('action') not in actions]
    for action, folders, filename, label in (
        ('h3_text_encoder', ('text_encoders', 'clip'), ENCODER, 'the 4B prompt encoder'),
        ('h3_clip_projection', ('clip_projections',), PROJECTION, 'the ClipProj v3.1 projection'),
    ):
        if not host.weight_present(folders, filename):
            rows.append({'action': action, 'filename': filename, 'what': label,
                         'required': True, 'place_in': f'models/{folders[0]}/'})
    if classes is None:
        classes = host.registered_classes()
    if classes is None or NODE not in classes:
        rows.append({'action': 'h3_clipproj_nodes', 'filename': NODE,
                     'what': 'ClipProj nodes (start or restart ComfyUI after installation)',
                     'required': True, 'place_in': 'custom_nodes/ComfyUI-ClipProj/'})
    return rows


def reference_status(result, classes):
    result['missing_weights'] = missing_weights(result.get('missing_weights', []), classes)
    if classes is not None and NODE not in classes and NODE not in result.get('missing_nodes', []):
        result['missing_nodes'] = [*result.get('missing_nodes', []), NODE]
    for base in result.get('bases', []):
        base['missing_weights'] = missing_weights(base.get('missing_weights', []), classes)
        base['nodes_ready'] = base.get('nodes_ready', True) and classes is not None and NODE in classes
        base['ready'] = (base['available'] and base['nodes_ready']
                         and not any(row.get('required') for row in base['missing_weights']))
    result['ready'] = any(base['ready'] for base in result.get('bases', []))
    return result


def preflight(workflow):
    # Generic host preflight checks the CLIP file and node availability. Custom
    # projection folders are not model-loader fields in older supported hosts.
    if any(node['class_type'] == NODE for node in workflow.values()):
        if not host.weight_present(('clip_projections',), PROJECTION):
            from lds_sdk.video_host import studio as lts
            raise lts.StudioAssetsMissing('h3video', [{
                'path': f'models/clip_projections/{PROJECTION}', 'kind': 'clip projection',
                'hint': 'Install the ClipProj v3.1 projection from Setup.',
            }], [])
    return host.preflight(workflow)
