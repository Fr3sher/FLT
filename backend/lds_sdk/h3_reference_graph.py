"""Pure H3 reference conditioning; products validate and stage their media."""
import re

LIMITS = {'image': 9, 'video': 3, 'audio': 3}

VIDEO_GRID = 32

NAME = re.compile(r'lds_vref_[0-9a-f]{32}\.(?:png|mp4|wav)\Z')

def _safe_name(name):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError('invalid reference name — pick the reference again')
    return name

def label_references(references):
    """Same fixed type order and soundtrack numbering as the native H3 node."""
    counts = {'image': 0, 'video': 0, 'audio': 0}
    out = []
    for kind in ('image', 'video', 'audio'):
        for original in references:
            if original['kind'] != kind:
                continue
            ref = dict(original)
            counts[kind] += 1
            label = {'image': 'Picture', 'video': 'Video', 'audio': 'Audio'}[kind]
            ref['tag'] = f'<{label} {counts[kind]}>'
            ref.pop('audio_tag', None)
            if kind == 'video' and ref.get('include_audio'):
                counts['audio'] += 1
                ref['audio_tag'] = f'<Audio {counts["audio"]}>'
            out.append(ref)
    return out

def reference_format_ratio(references):
    """Read one selected video's display ratio from server-validated metadata."""
    selected = None
    for ref in references:
        use_format = ref.get('use_format', False)
        if not isinstance(use_format, bool):
            raise ValueError('use_format must be true or false')
        if 'use_format' in ref and ref['kind'] != 'video':
            raise ValueError('Only a video reference can set the output format.')
        if use_format:
            if selected is not None:
                raise ValueError('Choose only one video reference for the output format.')
            selected = ref
    if selected is None:
        return None
    # Normalization can round 640x360 to 640x352. Keep the source's autorotated
    # display ratio; manifests predating source dimensions retain their canvas.
    keys = (('source_width', 'source_height')
            if 'source_width' in selected or 'source_height' in selected else ('width', 'height'))
    width, height = (selected.get(key) for key in keys)
    if (type(width) is not int or type(height) is not int or min(width, height) < VIDEO_GRID
            or max(width, height) > 8192 or width * height > 16_777_216):
        raise ValueError('The reference video format is unavailable; pick the video again.')
    return width / height

def graft(wf, *, references, image=None, end_image=None, ref_image_size='match'):
    """Turn the already-sized text graph into native reference conditioning."""
    from lds_sdk import h3_render as vts
    if ref_image_size not in ('match', 'max'):
        raise ValueError('Reference image size must be match or max.')
    inputs = wf[vts.N_COND]['inputs']
    inputs.pop('last_frame', None)
    inputs['audio_vae'] = [vts.N_VAE_AUDIO, 0]
    inputs['ref_image_size'] = ref_image_size
    wf[vts.N_COND]['class_type'] = 'MiniMaxH3ReferenceToVideo'
    counters = dict.fromkeys(LIMITS, 0)
    for index, ref in enumerate(label_references(references)):
        kind = ref['kind']
        counters[kind] += 1
        n = counters[kind] - 1
        load = str(900 + index * 2)
        if kind == 'image':
            wf[load] = {'class_type': 'LoadImage', 'inputs': {'image': ref['name']}}
            inputs[f'ref_images.ref_image_{n}'] = [load, 0]
        elif kind == 'video':
            components = str(901 + index * 2)
            sliced = str(1100 + index)
            wf[load] = {'class_type': 'LoadVideo', 'inputs': {'file': ref['name']}}
            wf[sliced] = {'class_type': 'Video Slice', 'inputs': {
                'video': [load, 0], 'start_time': 0.0,
                'duration': inputs['length'] / 24.0, 'strict_duration': False,
            }}
            wf[components] = {'class_type': 'GetVideoComponents', 'inputs': {'video': [sliced, 0]}}
            inputs[f'ref_videos.ref_video_{n}'] = [components, 0]
            if ref.get('include_audio'):
                # H3 crops reference video to output length but retains the
                # complete soundtrack. Read it independently of the video slice.
                audio = str(1200 + index)
                wf[audio] = {'class_type': 'LoadAudio', 'inputs': {'audio': ref['name']}}
                inputs[f'ref_video_audios.ref_video_audio_{n}'] = [audio, 0]
        else:
            wf[load] = {'class_type': 'LoadAudio', 'inputs': {'audio': ref['name']}}
            inputs[f'ref_audios.ref_audio_{n}'] = [load, 0]
    positive = [vts.N_COND, 0]
    for index, (name, frame_idx) in enumerate(((image, 0), (end_image, -1))):
        if name:
            load, guide = str(950 + index * 2), str(951 + index * 2)
            wf[load] = {'class_type': 'LoadImage', 'inputs': {'image': name}}
            wf[guide] = {'class_type': 'MiniMaxH3AddGuide', 'inputs': {
                'positive': positive, 'latent': [vts.N_COND, 1],
                'vae': [vts.N_VAE_VIDEO, 0], 'image': [load, 0], 'frame_idx': frame_idx,
            }}
            positive = [guide, 0]
    wf[vts.N_GUIDER]['inputs']['conditioning'] = positive

safe_name = _safe_name

__all__ = [
    'LIMITS',
    'NAME',
    'VIDEO_GRID',
    'graft',
    'label_references',
    'reference_format_ratio',
    'safe_name',
]
