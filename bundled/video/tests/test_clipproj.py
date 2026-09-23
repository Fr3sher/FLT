"""Replacement keeps every H3 mode connected and preparation complete."""
import pytest
from lds_video import clipproj, h3_chimera


@pytest.mark.parametrize('mode', ['t2v', 'i2v', 'ref2va'])
def test_all_modes_send_projected_4b_conditioning(mode):
    options = {'prompt': 'A toy robot waves.', 'mode': mode, 'seed': 72, 'sage': False}
    if mode == 'i2v':
        options['image'] = 'opening.png'
    if mode == 'ref2va':
        options['references'] = [{'kind': 'image', 'name': 'lds_vref_' + '1' * 32 + '.png'}]
        options['accel'] = 'ref4'
    built = h3_chimera.build_workflow(**options)
    graph = built['workflow']
    assert graph['104']['inputs']['clip'] == [clipproj.NODE_ID, 0]
    assert graph[clipproj.NODE_ID]['inputs']['clip'] == ['13', 0]
    assert graph['13']['inputs']['type'] == 'krea2'
    assert graph['13']['inputs']['clip_name'] == clipproj.ENCODER
    assert built['generation_settings']['clip_projection'] == clipproj.PROJECTION
    assert graph['15']['inputs']['noise_seed'] == 72


def test_no_32b_dependency_and_every_new_component_is_actionable(monkeypatch):
    monkeypatch.setattr(clipproj.host, 'weight_present', lambda *args: False)
    old = [{'action': 'h3_text_encoder', 'filename': 'old32b', 'required': True}]
    missing = clipproj.missing_weights(old, classes=set())
    assert {r['action'] for r in missing} == {'h3_text_encoder', 'h3_clip_projection', 'h3_clipproj_nodes'}
    assert all(r['required'] and r['filename'] != 'old32b' for r in missing)
    monkeypatch.setattr(clipproj.host, 'weight_present', lambda *args: True)
    assert clipproj.missing_weights(old, classes={'ClipProjApply'}) == []


def test_reference_readiness_uses_4b_projection_and_loaded_node(monkeypatch):
    monkeypatch.setattr(clipproj.host, 'weight_present', lambda folders, name: name != 'old32b')
    old = {'missing_weights': [{'action': 'h3_text_encoder', 'filename': 'old32b', 'required': True}],
           'missing_nodes': [], 'bases': [{'available': True, 'ready': False,
                                         'missing_weights': [{'action': 'h3_text_encoder', 'required': True}]}]}
    result = clipproj.reference_status(old, {'ClipProjApply'})
    assert result['ready'] and result['bases'][0]['ready']
    assert not clipproj.reference_status(result, set())['ready']


def test_missing_projection_fails_before_enqueue(monkeypatch):
    from lds_sdk.video_host import studio
    monkeypatch.setattr(clipproj.host, 'weight_present', lambda *args: False)
    graph = {clipproj.NODE_ID: {'class_type': clipproj.NODE}}
    with pytest.raises(studio.StudioAssetsMissing) as err:
        clipproj.preflight(graph)
    assert clipproj.PROJECTION in str(err.value.missing_files)
