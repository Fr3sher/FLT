"""The public engine catalogs agree across Python and JavaScript.

The host keeps local engines while API engines belong to their optional plugin.
Compare the current spec owners' ids, order and labels with the real backend
registry after booting with that plugin on and off. The frontend specs retain a
stable first-line shape for this cross-language source contract; reference-pool
contracts below independently keep the local edit inputs aligned.
"""
import re
from pathlib import Path

import pytest

from app.services import face_dataset_service as svc

_JS = (Path(__file__).resolve().parents[2]
       / 'frontend' / 'src' / 'components' / 'dataset' / 'engineSelection.js')


def _js_catalog(api_enabled):
    """Read the explicit spec rows owned by core and the optional API plugin."""
    paths = [_JS.parents[2] / 'engines' / 'catalog.js']
    if api_enabled:
        paths.append(_JS.parents[4] / 'bundled' / 'api_engines' / 'frontend' / 'lib' / 'engineSpecs.js')
    rows = []
    for path in paths:
        text = path.read_text(encoding='utf-8')
        entries = re.findall(r"\{ id: '([^']+)', label: '([^']+)', kind: '(api|local)', order: (\d+),", text)
        assert entries, f'engine spec rows not found in {path.name}'
        rows.extend(entries)
    return sorted(rows, key=lambda row: int(row[3]))


def _js_edit_ref_support():
    """EDIT_REF_SUPPORT in referenceEdit.js: which references each LOCAL engine
    consumes. Lives in the OTHER file, so it gets its own reader."""
    path = _JS.parent / 'referenceEdit.js'
    if not path.exists():
        pytest.skip(f'frontend source not present ({path.name})')
    src = path.read_text(encoding='utf-8')
    m = re.search(r'export const EDIT_REF_SUPPORT\s*=\s*\{(.*?)\};', src, re.S)
    assert m, 'EDIT_REF_SUPPORT declaration not found in referenceEdit.js'
    return dict(re.findall(r"(\w+):\s*'([^']*)'", m.group(1)))


@pytest.mark.parametrize('api_enabled', [
    pytest.param(False, marks=pytest.mark.plugins()),
    pytest.param(True, marks=pytest.mark.plugins('api_engines')),
])
def test_the_api_engine_ids_are_identical_on_both_sides(app, api_enabled):
    """The installed owner supplies the same ids and order to both catalogs."""
    from app.engines.registry import available_specs
    js = tuple(row[0] for row in _js_catalog(api_enabled) if row[2] == 'api')
    py = tuple(spec.id for spec in available_specs() if spec.is_api)
    assert js == py
    assert py == (svc.API_ENGINES if api_enabled else ())


@pytest.mark.parametrize('api_enabled', [
    pytest.param(False, marks=pytest.mark.plugins()),
    pytest.param(True, marks=pytest.mark.plugins('api_engines')),
])
def test_the_editable_engine_ids_are_identical_on_both_sides(app, api_enabled):
    """Local engines remain first; an unavailable plugin offers no edit engine."""
    assert tuple(row[0] for row in _js_catalog(api_enabled)) == svc.editable_engines()


def test_the_local_engines_reference_support_matches_on_both_sides():
    """The UI says at PICK time which reference photos an engine will use; the
    service is what actually forwards (or doesn't) forward them. Those two
    claiming different things is the silent drop the whole feature avoids — the
    user would be told Klein takes the extra angles and get an edit that ignored
    them, or the reverse."""
    assert _js_edit_ref_support() == svc.LOCAL_EDIT_REF_SUPPORT
    # And every local engine has an answer: a new one must not default to "all".
    for engine in svc.LOCAL_ENGINES:
        assert engine in svc.LOCAL_EDIT_REF_SUPPORT, engine


def test_each_local_engine_reads_only_its_own_pool():
    """The two local engines want opposite photos, so the pools must not cross.

    Klein chains the dataset's ANGLES (same face, identity locked across every
    generation). Krea reads ONE image from the edit dialog, because its `_b` slot
    was trained for a DIFFERENT subject — feeding it the dataset pool would hand
    it another view of the same person every single time, which is the one photo
    that slot mishandles. Two functions, one per pool, so a crossed wire is a
    failing test rather than a quietly wrong render."""
    dataset, modal = ['a.png', 'b.png', 'c.png'], ['upload1.png', 'upload2.png']

    assert svc.local_edit_extra_refs('klein', dataset) == dataset
    assert svc.local_edit_modal_refs('klein', modal) == []

    assert svc.local_edit_extra_refs('krea', dataset) == []
    assert svc.local_edit_modal_refs('krea', modal) == ['upload1.png']

    assert svc.local_edit_extra_refs('krea', None) == []
    assert svc.local_edit_modal_refs('krea', None) == []
    # An engine nobody has decided about reads NEITHER pool rather than both —
    # the safe default for a graph that may have no slot at all.
    assert svc.local_edit_extra_refs('nanobanana', dataset) == []
    assert svc.local_edit_modal_refs('nanobanana', modal) == []

    # And the refusal path turns on this list, not on "is it local".
    assert svc.local_engines_taking_modal_refs(['klein', 'krea']) == ['krea']
    assert svc.local_engines_taking_modal_refs(['klein']) == []
    # Its mirror gates DISK WRITES: a Krea-only edit must not copy the dataset's
    # extras to temporary files for a consumer that no longer exists.
    assert svc.local_engines_taking_dataset_refs(['klein', 'krea']) == ['klein']
    assert svc.local_engines_taking_dataset_refs(['krea']) == []
    assert svc.local_engines_taking_dataset_refs(['chatgpt']) == []


@pytest.mark.parametrize('api_enabled', [
    pytest.param(False, marks=pytest.mark.plugins()),
    pytest.param(True, marks=pytest.mark.plugins('api_engines')),
])
def test_the_engine_labels_are_worded_identically_on_both_sides(app, api_enabled):
    """Labels used in both refusal messages come from the same owner catalog."""
    assert {row[0]: row[1] for row in _js_catalog(api_enabled)} == svc.engine_labels()


def test_the_refusal_message_is_derived_from_the_list_not_hardcoded(monkeypatch):
    """Adding an engine at the registry seam rewrites the refusal at read time."""
    from app.engines import registry
    monkeypatch.setattr(registry, '_specs', {})
    registry.register(registry.EngineSpec('nanobanana', 'Nano Banana Pro', 'api', 0))
    assert svc.edit_engine_choice_message() == 'pick Nano Banana Pro'
    registry.register(registry.EngineSpec('newcomer', 'Newcomer', 'api', 1))
    assert svc.edit_engine_choice_message() == 'pick Nano Banana Pro or Newcomer'
