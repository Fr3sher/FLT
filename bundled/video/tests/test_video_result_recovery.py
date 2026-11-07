import pytest
from lds_video.video_result_recovery import saved_video


def history(filename='render.mp4', status='success', **extra):
    return {'status': {'status_str': status, 'completed': True}, 'outputs': {
        '902': {'images': [{'filename': 'reference.mp4', 'type': 'input'}]},
        '92': {'gifs': [{'filename': filename, 'type': 'output', **extra}]}}}


WORKFLOW = {'902': {'class_type': 'LoadVideo'}, '92': {'class_type': 'SaveVideo'}}


def test_recovers_only_the_exact_successful_saver():
    assert saved_video(history(), WORKFLOW) == 'render.mp4'
    assert saved_video(history(), {}) is None
    assert saved_video(history(status='error'), WORKFLOW) is None


@pytest.mark.parametrize('filename', ['../render.mp4', 'a\\render.mp4', 'C:render.mp4', 'image.png'])
def test_rejects_unsafe_or_non_video_outputs(filename):
    assert saved_video(history(filename), WORKFLOW) is None


def test_rejects_inputs_subfolders_and_ambiguous_savers():
    assert saved_video(history(type='input'), WORKFLOW) is None
    assert saved_video(history(subfolder='other'), WORKFLOW) is None
    entry = history()
    entry['outputs']['93'] = {'images': [{'filename': 'other.mp4', 'type': 'output'}]}
    assert saved_video(entry, {**WORKFLOW, '93': {'class_type': 'SaveVideo'}}) is None
