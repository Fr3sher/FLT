"""Package preparation checks never start inference or import optional sources."""
import ast
from pathlib import Path
import sys

import pytest

from lds_sdk.setup import missing_modules


def test_module_presence_does_not_import_optional_module(tmp_path, monkeypatch):
    (tmp_path / 'fixture_optional.py').write_text('raise AssertionError("must not import")\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    assert missing_modules(['fixture_optional', 'fixture_absent']) == ['fixture_absent']
    assert 'fixture_optional' not in sys.modules


@pytest.mark.parametrize('names', ['requests', ['a.b'], ['../a'], ['a/b'], [None], ['é'], ['a'] * 65])
def test_invalid_presence_query_is_rejected_before_inspection(names, monkeypatch):
    monkeypatch.setattr('importlib.util.find_spec', lambda _: pytest.fail('must reject before inspection'))
    with pytest.raises(ValueError):
        missing_modules(names)


def test_packaged_video_caption_helper_loads_without_app_or_gpu(monkeypatch):
    folder = Path(__file__).resolve().parents[2] / 'bundled/video/infer'
    tree = ast.parse((folder / 'video_caption_infer.py').read_text(encoding='utf-8'))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == '_load_caption_fields')
    monkeypatch.syspath_prepend(str(folder))
    namespace = {'_log': lambda text: pytest.fail(text)}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'worker-helper', 'exec'), namespace)
    previous = sys.modules.pop('_caption_fields', None)
    try:
        helper = namespace['_load_caption_fields']()
        assert Path(helper.__file__).resolve() == folder / '_caption_fields.py'
        assert helper.split_caption_fields('A person walks.\n---\nMotion: walking')[0] == 'A person walks.'
    finally:
        sys.modules.pop('_caption_fields', None)
        if previous is not None:
            sys.modules['_caption_fields'] = previous
