"""Video recipes on the public H3 API."""
from lds_sdk import h3_render as host
from . import h3_refmods, clipproj


def normalise_accel(accel, turbo=False):
    return accel if isinstance(accel, str) and accel in IDS else host.normalise_accel(accel, turbo)


def accel_spec(accel):
    return next((spec for spec in CHIMERA if spec['id'] == accel), None) or host.accel_spec(accel)


def accelerations_status(classes=None, vram_gb=None):
    rows = []
    for spec in CHIMERA:
        present = host.weight_present(('loras',), spec['file'])
        rows.append({**spec, 'pack': None, 'weight_present': present, 'available': present,
                     'needs_light': False, 'setup_path': f"Video Test Studio › {spec['label']}"})
    return rows + [row for row in host.accelerations_status(classes, vram_gb=vram_gb) if row['id'] not in IDS]


def missing_weights():
    actions = {spec['action'] for spec in CHIMERA}
    rows = [row for row in host.missing_weights() if row.get('action') not in actions]
    for spec in CHIMERA:
        if not host.weight_present(('loras',), spec['file']):
            rows.append({'action': spec['action'], 'filename': spec['file'], 'what': spec['label'],
                         'required': False, 'place_in': 'models/loras/'})
    return clipproj.missing_weights(rows)


def build_workflow(*, refmods=False, references=None, fused=False, h3_attention='auto',
                   h3_spectrum=False, h3_video_vae='fp16', h3_video_writer='native',
                   performance_classes=None, **options):
    from . import h3_performance as performance
    mode = host.normalise_mode(options.get('mode'))
    fused = fused or options.get('ref_base') == 'fused'
    controls = dict(fused=fused, h3_attention=h3_attention, h3_spectrum=h3_spectrum,
                    h3_video_vae=h3_video_vae, h3_video_writer=h3_video_writer)
    performance.validate(**controls, **options)
    if fused:
        options['steps'] = options.get('steps') if options.get('steps') is not None else 8
        options['ref_base'] = 'official'
    if h3_attention != 'auto':
        options['sage'] = False
    if h3_video_vae == 'int8':
        options['video_vae'] = host.VIDEO_VAE_INT8
    h3_refmods.validate(mode, options.get('image'), references, refmods)
    spec = next((row for row in CHIMERA if row['id'] == options.get('accel')), None)
    if spec and mode == 'ref2va':
        raise ValueError('Choose the acceleration from the reference mode controls.')
    steps = options.get('steps')
    if spec:
        if spec['id'] == 'taomate_3step':
            if steps is not None and (isinstance(steps, bool) or float(steps) != 3):
                raise ValueError('TaoMate H3 requires exactly 3 sampling steps.')
            options['sage'] = False
        options.update(accel='', turbo=False, steps=steps if steps is not None else spec['steps'])
    built = host.build_workflow(references=None if refmods else references, **options)
    graph = built['workflow']
    if spec:
        # The public graft reconnects all readers, including style and upscale.
        host.graft_stock_accel(graph, spec)
        count = 3 if spec['id'] == 'taomate_3step' else max(4, min(40, int(steps if steps is not None else spec['steps'])))
        graph[host.N_SCHEDULER]['inputs']['steps'] = count
        built.update(accel=spec['id'], steps=count)
        built['generation_settings'].update(accel=spec['id'], steps=count)
        built['notes'].append(f"acceleration: {spec['label']}, {count} steps")
    if refmods:
        h3_refmods.graft(graph, references)
        built['generation_settings'].update(refmods=True, references=references)
        built['notes'].append(f'identity RefMods: {len(references)} (experimental)')
    return clipproj.apply(performance.apply(built, **controls, classes=performance_classes, mode=mode))

CHIMERA = ({'id': 'taomate_3step',
  'label': 'TaoMate H3 · 3 steps',
  'file': 'TaoMate-H3-3step-ComfyUI.safetensors',
  'steps': 3,
  'arena': '',
  'author': 'TaoLive AIGC / CZMartin22',
  'license': 'See model card',
  'action': 'h3_taomate_lora',
  'pack': None,
  'strength': 1.0,
  'shift': (12.0, 3.0),
  'hint': 'Chimera TaoMate FL2VA recipe: exactly 3 steps, Euler, shift 12/3. '
          'Supports identity RefMods.'},
 {'id': 'fasth3_v02',
  'label': 'FastH3 v0.2 (Chimera)',
  'file': 'minimax_h3_fasth3_v0.2_rank128_drozbay.safetensors',
  'steps': 4,
  'arena': '',
  'author': 'drozbay',
  'license': 'See model card',
  'action': 'h3_fasth3_lora',
  'pack': None,
  'strength': 1.0,
  'shift': (12.0, 3.0),
  'hint': 'Experimental FL2VA acceleration with identity RefMods support. 4 '
          'steps recommended; editable.'})

IDS = {spec["id"] for spec in CHIMERA}
ACCELERATIONS = CHIMERA + tuple(spec for spec in host.ACCELERATIONS if spec["id"] not in IDS)
ACCEL_IDS = tuple(spec["id"] for spec in ACCELERATIONS)
