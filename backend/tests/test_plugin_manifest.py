"""Plugin manifest input validation, using neutral in-memory packages."""
import json
from pathlib import Path

import pytest

from app.plugins.manifest import ManifestError, load_manifest, parse_manifest


def _good(**over):
    data = {
        'id': 'acme.tagger', 'name': 'Tagger', 'version': '1.0.0', 'api': 1,
        'requires': [], 'python_package': 'lds_acme_tagger', 'frontend': 'frontend/index.js',
        'owns': {'probes': ['acme_tagger_ready'], 'install_actions': ['acme_tagger_deps']},
        'permissions': ['network', 'secrets:ACME_KEY'],
    }
    data.update(over)
    return data


def test_a_valid_external_manifest_parses():
    m = parse_manifest(_good(), Path('/x'))
    assert m.id == 'acme.tagger' and m.external and m.python_package == 'lds_acme_tagger'
    assert m.owned('probes') == ('acme_tagger_ready',)
    assert m.frontend == 'frontend/index.js'


def test_a_valid_bundled_manifest_parses():
    m = parse_manifest(_good(id='scrape', bundled=True, in_process_requirements=True,
                             requirements='requirements.txt'), Path('/x'))
    assert m.bundled and m.in_process_requirements


def test_external_ids_are_namespaced_and_bundled_ids_are_bare():
    with pytest.raises(ManifestError, match='publisher.name'):
        parse_manifest(_good(id='tagger'), Path('/x'))
    with pytest.raises(ManifestError, match='letters, digits'):
        parse_manifest(_good(id='acme.tagger', bundled=True), Path('/x'))


def test_the_reserved_id_enabled_is_refused():
    with pytest.raises(ManifestError, match='reserved'):
        parse_manifest(_good(id='enabled', bundled=True), Path('/x'))


def test_in_process_requirements_is_a_bundled_only_exception():
    with pytest.raises(ManifestError, match='bundled'):
        parse_manifest(_good(in_process_requirements=True), Path('/x'))


def test_a_package_that_would_shadow_the_app_is_refused():
    for name in ('app', 'backend', 'tests'):
        with pytest.raises(ManifestError, match='shadow'):
            parse_manifest(_good(python_package=name), Path('/x'))


def test_frontend_must_stay_inside_the_plugin():
    for bad in ('../x.js', '/abs/x.js', 'C:/x.js', 'a//b.js'):
        with pytest.raises(ManifestError):
            parse_manifest(_good(frontend=bad), Path('/x'))


def test_owns_only_knows_the_declared_kinds_and_shapes():
    with pytest.raises(ManifestError, match='ownership kind'):
        parse_manifest(_good(owns={'routes': ['x']}), Path('/x'))
    with pytest.raises(ManifestError, match='list of non-empty strings'):
        parse_manifest(_good(owns={'probes': 'x'}), Path('/x'))
    m = parse_manifest(_good(owns={'config_keys_in_shared_sections': {'engines': ['acme_model']}}), Path('/x'))
    assert m.owns['config_keys_in_shared_sections'] == {'engines': ['acme_model']}


def test_a_model_without_a_verifiable_hash_is_not_listed():
    with pytest.raises(ManifestError, match='sha256'):
        parse_manifest(_good(models=[{'key': 'w', 'url': 'https://x', 'sha256': 'nope', 'dest': 'models/x'}]), Path('/x'))


def test_permissions_come_from_the_vocabulary():
    with pytest.raises(ManifestError, match='vocabulary'):
        parse_manifest(_good(permissions=['root']), Path('/x'))


def test_api_must_be_a_positive_integer_and_version_a_number():
    with pytest.raises(ManifestError, match='"api"'):
        parse_manifest(_good(api='1'), Path('/x'))
    with pytest.raises(ManifestError, match='version'):
        parse_manifest(_good(version='latest'), Path('/x'))


def test_a_plugin_cannot_require_itself():
    with pytest.raises(ManifestError, match='itself'):
        parse_manifest(_good(requires=['acme.tagger']), Path('/x'))


def test_load_manifest_reads_the_file_and_names_bad_json(tmp_path):
    d = tmp_path / 'acme.tagger'
    d.mkdir()
    (d / 'plugin.json').write_text(json.dumps(_good()), encoding='utf-8')
    assert load_manifest(d).dir == d
    (d / 'plugin.json').write_text('{not json', encoding='utf-8')
    with pytest.raises(ManifestError, match='not valid JSON'):
        load_manifest(d)
    with pytest.raises(ManifestError, match='cannot read'):
        load_manifest(tmp_path / 'missing')
