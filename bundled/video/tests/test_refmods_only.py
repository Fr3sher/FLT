"""RefMods-only clips preserve identity conditioning without inventing a start frame."""
import pytest
from lds_video import h3_refmods
from lds_video.h3_chimera import build_workflow
from lds_sdk.h3_prompt import inject_alignment_header, HEADER_LINE

REFS = [{'kind': 'image', 'name': 'lds_vref_' + c * 32 + '.png'} for c in ('1', '2')]

@pytest.mark.parametrize('last', [None, 'ending.png'])
@pytest.mark.parametrize('light', [False, True])
def test_refs_without_first_frame_keep_shape_and_optional_last(last, light):
    result = build_workflow(prompt='The two toy robots wave.', mode='t2v',
        refmods=True, references=REFS, end_image=last, aspect='portrait',
        seed=54321, frames=24, megapixels=.15, accel='taomate_3step',
        light=light, light_on_disk=light, sage=False)
    graph = result['workflow']
    inputs = graph['104']['inputs']
    assert 'first_frame' not in inputs and '114' not in graph
    assert inputs['height'] > inputs['width']
    assert inputs.get('last_frame') == (['620', 0] if last else None)
    assert graph['16']['inputs']['conditioning'] == ['lds_refmod_1_apply', 0]
    assert graph['lds_refmod_1_apply']['inputs']['conditioning'] == ['lds_refmod_0_apply', 0]
    assert graph['lds_refmod_0_apply']['inputs']['conditioning'] == ['104', 0]
    assert result['generation_settings']['refmods'] is True
    assert result['generation_settings']['references'] == REFS
    for node in graph.values():
        for value in node['inputs'].values():
            if isinstance(value, list): assert value[0] in graph

def test_existing_first_frame_still_has_its_own_input():
    graph = build_workflow(prompt='The robot waves.', mode='i2v', image='opening.png',
        references=REFS, refmods=True, sage=False)['workflow']
    assert graph['114']['inputs']['image'] == 'opening.png'
    assert 'first_frame' in graph['104']['inputs']
    assert graph['16']['inputs']['conditioning'] == ['lds_refmod_1_apply', 0]

@pytest.mark.parametrize('change', [
    {'references': []}, {'references': None}, {'refmods': 'true'},
    {'references': [{'kind': 'video', 'name': REFS[0]['name']}]},
    {'mode': 't2v', 'image': 'ignored.png'}, {'mode': 'i2v'},
])
def test_invalid_inputs_are_not_silently_dropped(change):
    with pytest.raises(ValueError):
        build_workflow(**(dict(prompt='Motion.', mode='t2v', references=REFS, refmods=True) | change))


@pytest.mark.parametrize('count', [3, 16, 160])
@pytest.mark.parametrize('image', [None, 'opening.png'])
def test_every_identity_reaches_the_sampler_without_overwriting_render_nodes(count, image):
    refs = [{'kind': 'image', 'name': f'lds_vref_{i:032x}.png'} for i in range(count)]
    options = dict(prompt='The toy robots wave.', mode='i2v' if image else 't2v',
                   image=image, sage=False, h3_spectrum=True,
                   performance_classes={'SpectrumApplyMiniMaxH3'})
    baseline = build_workflow(**options)['workflow']
    result = build_workflow(**options, references=refs, refmods=True)
    graph = result['workflow']
    assert baseline.keys() <= graph.keys()
    assert result['generation_settings']['references'] == refs
    current = graph['16']['inputs']['conditioning']
    for ref in reversed(refs):
        apply = graph[current[0]]
        assert apply['class_type'] == 'MiniMaxH3RefModApply'
        extract = graph[apply['inputs']['mods'][0]]
        image_node = graph[extract['inputs']['refs_image.ref_image_0'][0]]
        assert image_node['inputs']['image'] == ref['name']
        current = apply['inputs']['conditioning']
    assert current == ['104', 0]
    assert graph['1302'] == baseline['1302']


def test_refmod_validation_and_writer_keep_all_staged_images(monkeypatch):
    from lds_video import video_references as refs, video_reference_prompt as writer
    selected = [{'kind': 'image', 'name': f'lds_vref_{i:032x}.png'} for i in range(16)]
    monkeypatch.setattr(refs, '_manifest', lambda name, user_id=None: {'kind': 'image', 'name': name})
    staged = []
    monkeypatch.setattr(refs, 'path_for', lambda name, **kwargs: staged.append(name))
    checked = refs.validate_references(selected, enforce_limits=False)
    assert len(checked) == len(selected)
    assert checked[-1]['tag'] == '<Picture 16>'
    assert staged == [r['name'] for r in selected]
    assert writer._validated(selected) == checked
    with pytest.raises(ValueError, match='Too many'):
        refs.validate_references(selected)
    monkeypatch.setattr(refs, '_manifest', lambda *args: {'kind': 'video'})
    with pytest.raises(ValueError, match='kind does not match'):
        refs.validate_references(selected, enforce_limits=False)

def test_prompt_without_first_frame_has_no_alignment_header_and_preserves_literals():
    text = ('summary: A greeting.\nsubject_definitions: A red robot from <Picture 1>.\n'
        'detailed_description: [Shot 1] It waves. A sign reads "<Picture 2>".\n'
        'overall_soundscape: Quiet hum.\nnon_diegetic_music: N/A')
    compiled = h3_refmods.first_frame_prompt(inject_alignment_header(text), has_first_frame=False)
    assert not HEADER_LINE.search(compiled)
    assert 'red robot from identity reference 1' in compiled
    assert '"<Picture 2>"' in compiled
    assert compiled.startswith('integrated_multimodal_description:')
    assert h3_refmods.first_frame_prompt(compiled, has_first_frame=False) == compiled
    assert HEADER_LINE.search(h3_refmods.first_frame_prompt(text))
