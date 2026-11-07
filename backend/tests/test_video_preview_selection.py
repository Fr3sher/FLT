"""A comparison queues all selected saves, preserving validation before work."""
from types import SimpleNamespace

import pytest

import app.models  # noqa: F401
from lds_video import video_checkpoint_previews as previews

pytestmark = pytest.mark.plugins('video')


def test_preview_batch_queues_all_twelve_checkpoints(app, monkeypatch):
    selected = [{'run_id': None, 'step': n * 100, 'final': False} for n in range(1, 13)]
    monkeypatch.setattr(previews.vck, '_dataset', lambda *a: SimpleNamespace(id=1))
    monkeypatch.setattr(previews, '_options', lambda data: {'seed': 123})
    monkeypatch.setattr(previews, '_resolve_choice', lambda ds, sel: {
        'selector': sel, 'run': None, 'lora': f'save-{sel["step"]}'})
    monkeypatch.setattr(previews, '_freeze', lambda choice: dict(choice))
    monkeypatch.setattr(previews, '_cleanup_unused', lambda copies: None)
    monkeypatch.setattr(previews, 'list_previews', lambda *a: {'previews': []})
    monkeypatch.setattr(previews.vts, 'registered_classes', lambda: set())
    monkeypatch.setattr(previews.vts, 'sage_available', lambda classes: False)
    monkeypatch.setattr(previews.vts, 'new_prefix', lambda uid: 'test')
    monkeypatch.setattr(previews.vts, 'build_workflow', lambda **kw: {'workflow': kw['lora']})
    checked, queued = [], []
    monkeypatch.setattr(previews.vts, 'preflight', checked.append)

    def enqueue(uid, **kw):
        assert len(checked) == 12, 'every selected save must pass preflight before queueing'
        queued.append(kw['lora'])
        return {'clip_id': len(queued)}

    monkeypatch.setattr(previews.vts, 'enqueue_clip', enqueue)
    with app.app_context():
        result = previews.start_previews('local', 1, {'checkpoints': selected})
    assert result['ok']
    assert [row['selector'] for row in result['queued']] == selected
    assert queued == [f'save-{n * 100}' for n in range(1, 13)]


def test_preview_selection_still_rejects_empty_duplicate_and_invalid_saves():
    valid = {'run_id': None, 'step': 100, 'final': False}
    for selection in [[], [valid, valid], [{'run_id': None, 'step': -1, 'final': False}]]:
        with pytest.raises(ValueError):
            previews.selectors({'checkpoints': selection})
