"""The engine list exists in TWO languages — this file is the seam that holds
them together.

WHY THIS TEST EXISTS
--------------------
Python owns `svc.API_ENGINES` (what /ref/edit and the fan-out accept) and
JavaScript owns `API_ENGINES` in engineSelection.js (what the workspace offers).
Neither can import the other, so the only thing that can stop them drifting is a
test that reads both. Drift is not theoretical: OpenRouter shipped as a
generation engine while the ✦ Edit modal and the /ref/edit route each kept their
own two-engine copy, so the app offered an engine set that no longer matched what
the server accepted.

The rule the codebase now follows is DERIVE, don't copy: the edit engines are the
API engines on both sides (`EDIT_ENGINES = [...API_ENGINES]` in JS,
`svc.API_ENGINES` in the route). That kills the third and fourth copies. This
test kills the drift between the two that remain — ids AND human labels, because
the labels word user-facing refusals on both sides.

Parsing JS with a regex is crude, and deliberately so: it must fail loudly if the
declaration moves or changes shape, rather than quietly matching nothing.
"""
import re
from pathlib import Path

import pytest

from app.services import face_dataset_service as svc

_JS = (Path(__file__).resolve().parents[2]
       / 'frontend' / 'src' / 'components' / 'dataset' / 'engineSelection.js')


def _js_source():
    if not _JS.exists():                       # source-only checkout of the backend
        pytest.skip(f'frontend source not present ({_JS.name})')
    return _JS.read_text(encoding='utf-8')


def _js_api_engines():
    m = re.search(r'export const API_ENGINES\s*=\s*\[(.*?)\];', _js_source(), re.S)
    assert m, 'API_ENGINES declaration not found in engineSelection.js'
    return tuple(re.findall(r"'([^']+)'", m.group(1)))


def _js_engine_labels():
    m = re.search(r'export const ENGINE_LABELS\s*=\s*\{(.*?)\};', _js_source(), re.S)
    assert m, 'ENGINE_LABELS declaration not found in engineSelection.js'
    return dict(re.findall(r"(\w+):\s*'([^']*)'", m.group(1)))


def test_the_api_engine_ids_are_identical_on_both_sides():
    """Same ids, same ORDER: the order drives the toggle order in the ✦ Edit modal
    and the batch build order on the server."""
    assert _js_api_engines() == svc.API_ENGINES


def test_the_engine_labels_are_worded_identically_on_both_sides():
    """Both sides word a refusal from these labels ('pick Nano Banana Pro, ChatGPT
    or OpenRouter'), so the same engine must not be called two different things
    depending on whether the client or the server said no."""
    js = _js_engine_labels()
    for engine in svc.API_ENGINES:
        assert js.get(engine) == svc.API_ENGINE_LABELS.get(engine), engine


def test_the_refusal_message_is_derived_from_the_list_not_hardcoded():
    """The point of deriving: adding an engine to API_ENGINES rewrites the message
    with no edit anywhere else. Pinned by mutating the tuple, not by pinning the
    sentence — a pinned sentence is just the old hardcoded list again."""
    msg = svc.edit_engine_choice_message()
    for engine in svc.API_ENGINES:
        assert svc.API_ENGINE_LABELS[engine] in msg

    real_engines, real_labels = svc.API_ENGINES, svc.API_ENGINE_LABELS
    try:
        svc.API_ENGINES = ('nanobanana', 'newcomer')
        svc.API_ENGINE_LABELS = dict(real_labels, newcomer='Newcomer')
        assert svc.edit_engine_choice_message() == 'pick Nano Banana Pro or Newcomer'
    finally:
        svc.API_ENGINES, svc.API_ENGINE_LABELS = real_engines, real_labels
