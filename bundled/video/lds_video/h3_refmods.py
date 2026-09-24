"""Encoded identity RefMods with optional FL2VA first and last frames.

Recipe qualified with ComfyUI-MiniMaxH3Mod 0.2.5. No saved embeddings,
training, temporal scrambling or replacement of the continuity frame.
"""
import re

from lds_sdk.h3_reference_graph import safe_name as _safe_name

CLASSES = ('MiniMaxH3RefModExtract', 'MiniMaxH3RefModApply')


def first_frame_prompt(text, *, battle=False, has_first_frame=True):
    """Keep the writer's identity descriptions without mislabelling the seam.

    Reference writers emit five fields; native FL2VA consumes three. Literal
    dialogue and on-screen text stay untouched, including reference-like text.
    """
    from lds_sdk.h3_prompt import inject_alignment_header, HEADER_LINE as _HEADER_LINE
    text = _HEADER_LINE.sub('', text).strip()
    fields = list(re.finditer(r'(?im)^\s*(summary|subject_definitions|detailed_description|overall_soundscape|non_diegetic_music):', text))
    if any(match[1].lower() == 'detailed_description' for match in fields):
        parts = {match[1].lower(): text[match.end():fields[i + 1].start() if i + 1 < len(fields) else len(text)].strip()
                 for i, match in enumerate(fields)}
        text = ('integrated_multimodal_description: ' + parts.get('subject_definitions', '') + ' '
                + parts['detailed_description'] + '\noverall_soundscape: '
                + parts.get('overall_soundscape', 'N/A') + '\nnon_diegetic_music: '
                + parts.get('non_diegetic_music', 'N/A'))
    def prose(value):
        return re.sub(r'<Picture\s+(\d+)>', lambda m:
            ('the opening frame' if m[1] == '3' else 'the requested final composition')
            if battle and int(m[1]) > 2 else f'identity reference {m[1]}', value)
    chunks, end = [], 0
    for literal in re.finditer(r'<d>[\s\S]*?</d>|"[^"\n]*"', text):
        chunks.extend((prose(text[end:literal.start()]), literal[0]))
        end = literal.end()
    chunks.append(prose(text[end:]))
    compiled = ''.join(chunks)
    return inject_alignment_header(compiled) if has_first_frame else compiled


def validate(mode, image, references, enabled):
    if type(enabled) is not bool:
        raise ValueError('RefMods must be true or false.')
    if not enabled:
        if references and mode != 'ref2va':
            raise ValueError('Enable RefMods to use identity references with a first frame.')
        return
    if mode not in ('i2v', 't2v'):
        raise ValueError('RefMods need the FL2VA image or text mode.')
    if mode == 'i2v' and not image:
        raise ValueError('Pick a start image, or use text mode with RefMods.')
    if mode == 't2v' and image:
        raise ValueError('Text mode must not include a start image.')
    if not isinstance(references, list) or not references:
        raise ValueError('RefMods need at least one identity image.')
    for ref in references:
        if not isinstance(ref, dict) or ref.get('kind') != 'image':
            raise ValueError('RefMods accept identity images only.')
        _safe_name(ref.get('name'))


def graft(graph, references):
    original = graph['16']['inputs']['conditioning']
    readers = [node for node in graph.values() if node['inputs'].get('conditioning') == original]
    positive = original
    for index, ref in enumerate(references):
        # A numeric range would eventually overlap optional render nodes.
        image, extract, apply = (f'lds_refmod_{index}_{part}' for part in ('image', 'extract', 'apply'))
        graph[image] = {'class_type': 'LoadImage', 'inputs': {'image': ref['name']}}
        graph[extract] = {'class_type': CLASSES[0], 'inputs': {
            'name': f'lds_identity_{index + 1}', 'mode': 'encode', 'concept_type': 'identity',
            'vae': ['11', 0], 'ref_resolution': 512, 'identity': 0, 'multiplier': 1,
            'pool_h': 16, 'pool_w': 16, 'background_retention': 0.0, 'description': '',
            'latent_frames': 1, 'merge': False, 'motion_only': False, 'save': False,
            'max_tokens': 2048, 'budget_policy': 'error', 'extraction_preset': 'manual',
            'refs_image.ref_image_0': [image, 0]}}
        graph[apply] = {'class_type': CLASSES[1], 'inputs': {
            'conditioning': positive, 'mods': [extract, 0], 'override': False,
            'retention': 1.0, 'curve_direction': 'constant', 'curve_shape': 'linear',
            'curve_value': 1.0, 'scramble_seed': -1, 'max_total_tokens': 0}}
        positive = [apply, 0]
    for node in readers:
        node['inputs']['conditioning'] = positive


__all__ = ['CLASSES', 'first_frame_prompt', 'validate', 'graft']
