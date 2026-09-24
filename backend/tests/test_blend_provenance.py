"""Generation provenance for a LoRA stack: which board chips produced this image.
Three relationships must stay distinct: training lineage (tree.edges, which run
continued another); image-to-checkpoint links; and generation provenance, where a
blend of N LoRAs has N parent chips. Only the last is multi-parent and requires
separate data. Head provenance already used record_id/step columns; stack members
previously had only filenames. These tests require member origins and None for
older runs, never fabricated origins."""
from tests.test_blend_sweep import _two_lora_stack


def test_each_stacked_member_records_the_pill_it_came_from(app, monkeypatch, tmp_path):
    """Each stack member carries (record_id, step), identifying the selected board
    chip rather than only a filename."""
    import json
    from app.models import LoraTestImage
    with app.app_context():
        launch, cp_a, cp_b, _, _, _ = _two_lora_stack(tmp_path, monkeypatch)
        out = launch({'weight': 0.9, 'record_id': 11, 'step': 2000},
                     {'weight': 0.55, 'record_id': 22, 'step': 1000})
        row = LoraTestImage.query.filter_by(run_id=out['run_id']).one()
        # The head retains its original provenance columns.
        assert (row.record_id, row.step) == (11, 2000)
        member = [m for m in json.loads(row.extra_loras) if m.get('combined')][0]
        assert member['filename'] == cp_b
        assert (member['record_id'], member['step']) == (22, 1000)


def test_the_stack_reads_back_as_one_parent_per_member(app, monkeypatch, tmp_path):
    """stack_of_row returns the COMPLETE stack, including the head, with member
    origins used to derive multi-parent edges."""
    from app.services import lora_test_studio as lts
    from app.models import LoraTestImage
    with app.app_context():
        launch, cp_a, cp_b, _, _, _ = _two_lora_stack(tmp_path, monkeypatch)
        out = launch({'weight': 0.9, 'record_id': 11, 'step': 2000},
                     {'weight': 0.55, 'record_id': 22, 'step': 1000})
        row = LoraTestImage.query.filter_by(run_id=out['run_id']).one()
        members = lts.stack_of_row(row)
        assert [(m['filename'], m['record_id'], m['step'], m['head']) for m in members] == [
            (cp_a, 11, 2000, True),
            (cp_b, 22, 1000, False),
        ]


def test_a_sweep_stamps_the_same_origins_on_every_combination(app, monkeypatch, tmp_path):
    """Sweeps change WEIGHTS, never provenance: all four images descend from the same
    two chips."""
    from app.services import lora_test_studio as lts
    from app.models import LoraTestImage
    with app.app_context():
        launch, cp_a, cp_b, _, _, _ = _two_lora_stack(tmp_path, monkeypatch)
        out = launch({'weights': [0.6, 0.8], 'record_id': 11, 'step': 2000},
                     {'weights': [0.4, 1.0], 'record_id': 22, 'step': 1000})
        assert out['created'] == 4
        rows = LoraTestImage.query.filter_by(run_id=out['run_id']).all()
        origins = {tuple((m['record_id'], m['step']) for m in lts.stack_of_row(r))
                   for r in rows}
        assert origins == {((11, 2000), (22, 1000))}


def test_a_stack_launched_before_this_says_UNKNOWN_rather_than_inventing_one(app):
    """Cell JSON is fixed at creation, so older stacks lack member origins. Return
    None instead of guessing a neighboring chip. An unknown parent means no edge,
    which the view must disclose."""
    import json
    from types import SimpleNamespace
    from app.services import lora_test_studio as lts
    with app.app_context():
        legacy = SimpleNamespace(
            dataset_id=None, checkpoint='z image' + chr(92) + 'lora_aaa.safetensors',
            strength=0.9, record_id=None, step=None,
            # Exactly what older runs stored: neither record_id nor step.
            extra_loras=json.dumps([{'filename': 'z image' + chr(92) + 'lora_bbb.safetensors',
                                     'strength': 0.55, 'combined': True,
                                     'dataset_id': 7, 'trigger': 'bbb'}]))
        members = lts.stack_of_row(legacy)
        assert len(members) == 2
        assert members[1]['record_id'] is None and members[1]['step'] is None
        # The rest of the composition stays readable: only the edge is lost, not the
        # stack.
        assert members[1]['trigger'] == 'bbb'
        assert members[1]['weight'] == 0.55
