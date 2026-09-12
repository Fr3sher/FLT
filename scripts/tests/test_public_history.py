"""Real Git DAGs: checking only the final tree would expose deleted products."""

from __future__ import annotations

import importlib.util
import copy
import hashlib
import io
import json
import os
import subprocess
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('public_history', SCRIPTS / 'check_public_history.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
import install_public_push_guard as installer
import private_plugin_pre_push as hook_runner
import public_port_manifest as port_policy


WHEEL_PATH = 'bundled/seedvr2/resources/wheels/fixture-1.0-py3-none-any.whl'
UPSTREAM_SOURCE = {
    'type': 'pypi_sdist',
    'url': ('https://files.pythonhosted.org/packages/3e/38/'
            '7859ff46355f76f8d19459005ca000b6e7012f2f1ca597746cbcd1fbfe5e/'
            'antlr4-python3-runtime-4.9.3.tar.gz'),
    'sha256': 'f224469b4168294902bb1efa80a8bf7855f24c99aef99cbefc1bcd3cce77881b',
}


def synthetic_wheel(entries=None, configure=None, metadata=True):
    """Tiny inert ZIP fixtures; no packaging toolchain or wheel installation."""
    output = io.BytesIO()
    entries = list(entries or [('fixture/__init__.py', b'VALUE = 1\n')])
    if metadata:
        information = {
            'fixture-1.0.dist-info/WHEEL': b'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
            'fixture-1.0.dist-info/METADATA': b'Metadata-Version: 2.1\nName: fixture\nVersion: 1.0\n',
            'fixture-1.0.dist-info/RECORD': b'',
        }
        present = {name for name, _ in entries}
        entries += [(name, data) for name, data in information.items() if name not in present]
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as wheel:
        for name, data in entries:
            info = zipfile.ZipInfo(name)
            # ZipInfo normalizes Windows backslashes; retain hostile raw names
            # in adversarial fixtures so the validator, not the builder, rejects them.
            info.filename = name
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            if configure:
                configure(info)
            wheel.writestr(info, data)
    return output.getvalue()


def resource_for(content):
    with zipfile.ZipFile(io.BytesIO(content)) as wheel:
        members = [{'path': info.filename, 'size': info.file_size,
                    'sha256': hashlib.sha256(wheel.read(info)).hexdigest()}
                   for info in wheel.infolist()]
    return {'type': 'wheel', 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
            'members': members, 'external_source': copy.deepcopy(UPSTREAM_SOURCE)}


class PublicHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repo'
        self.repo.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'LDS Fixture')
        self.git('config', 'user.email', 'noreply@lora-dataset-studio.dev')
        self.git('config', 'commit.gpgSign', 'false')
        self.write('core.py', 'print("public core")\n')
        self.baseline = self.commit('public baseline')

    def git(self, *args):
        # Fixtures must not inherit the real worktree's Git index or hooks.
        env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        env.update(GIT_ALLOW_PROTOCOL='', GIT_TERMINAL_PROMPT='0')
        result = subprocess.run(['git', '-C', str(self.repo), '-c', 'core.hooksPath=', *args],
                                capture_output=True, check=True, env=env)
        return result.stdout.decode().strip()

    def write(self, name, value):
        destination = self.repo / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(value, encoding='utf-8')

    def commit(self, message):
        self.git('add', '--all')
        self.git('commit', '-q', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def inspect(self, tip=None, private_source=None):
        return policy.check_history(self.repo, tip or self.git('rev-parse', 'HEAD'), self.baseline, private_source)

    def test_clean_core_changes_and_public_sdk_are_allowed(self):
        self.write('backend/lds_sdk/public.py', 'API_VERSION = "1.10"\n')
        self.write('docs/plugins/README.md', 'Public integration contract\n')
        self.commit('public SDK')
        self.assertTrue(self.inspect()['allowed'])

    def test_product_paths_and_archives_are_refused(self):
        for filename in ['bundled/example/p.py', 'nested/BUNDLED/example/p.py',
                         'public/example.ldsplugin', 'public/transition-pack.zip']:
            with self.subTest(filename=filename):
                self.git('checkout', '-q', '--detach', self.baseline)
                self.write(filename, 'PRIVATE_PRODUCT_FIXTURE\n')
                self.commit('private material')
                self.assertFalse(self.inspect()['allowed'])

    def test_deleted_product_in_history_is_still_refused(self):
        self.write('bundled/example/p.py', 'PRIVATE_PRODUCT_FIXTURE\n')
        private = self.commit('private product')
        self.git('rm', '-qr', 'bundled')
        self.commit('remove product from final tree')
        self.assertNotIn('bundled', self.git('ls-tree', '--name-only', 'HEAD'))
        result = self.inspect()
        self.assertFalse(result['allowed'])
        self.assertEqual(result['private_commit'], private)

    def test_merge_does_not_hide_private_side_branch(self):
        self.git('checkout', '-qb', 'private-product')
        self.write('bundled/example/p.py', 'PRIVATE_PRODUCT_FIXTURE\n')
        private = self.commit('private product')
        self.git('rm', '-qr', 'bundled')
        self.commit('remove private product')
        self.git('checkout', '-q', 'main')
        self.write('public.py', 'PUBLIC_FIXTURE = 1\n')
        self.commit('public change')
        self.git('merge', '-q', '--no-ff', 'private-product', '-m', 'merge with clean final tree')
        result = self.inspect()
        self.assertFalse(result['allowed'])
        self.assertEqual(result['private_commit'], private)

    def test_annotated_tag_is_checked_and_non_commit_target_is_refused(self):
        self.write('bundled/example/p.py', 'PRIVATE_PRODUCT_FIXTURE\n')
        self.commit('private product')
        self.git('tag', '-a', 'candidate', '-m', 'candidate')
        self.assertFalse(self.inspect(self.git('rev-parse', 'candidate'))['allowed'])
        blob = self.git('rev-parse', 'HEAD:bundled/example/p.py')
        with self.assertRaises(policy.HistoryError):
            self.inspect(blob)

    def test_known_private_blob_copied_to_public_path_is_refused(self):
        self.write('bundled/example/p.py', 'PRIVATE_PRODUCT_FIXTURE\n')
        source = self.commit('private product')
        self.git('checkout', '-q', '--detach', self.baseline)
        self.write('backend/renamed.py', 'PRIVATE_PRODUCT_FIXTURE\n')
        self.commit('accidental copy without private ancestry')
        self.assertFalse(self.inspect(private_source=source)['allowed'])

    def test_existing_public_content_is_not_made_private_by_a_duplicate(self):
        self.write('bundled/example/p.py', 'print("public core")\n')
        source = self.commit('private product has a public duplicate')
        self.git('checkout', '-q', '--detach', self.baseline)
        self.write('copy.py', 'print("public core")\n')
        self.commit('public duplicate')
        self.assertTrue(self.inspect(private_source=source)['allowed'])

    def test_private_baseline_and_moving_references_are_refused(self):
        self.write('bundled/example/p.py', 'PRIVATE_PRODUCT_FIXTURE\n')
        private = self.commit('private product')
        with self.assertRaises(policy.HistoryError):
            policy.check_history(self.repo, private, private)
        with self.assertRaises(policy.HistoryError):
            policy.check_history(self.repo, 'HEAD', self.baseline)

    def test_replace_refs_cannot_hide_a_private_commit(self):
        self.write('bundled/example/p.py', 'PRIVATE_PRODUCT_FIXTURE\n')
        private = self.commit('private product')
        self.git('replace', private, self.baseline)
        self.assertFalse(self.inspect(private)['allowed'])

    def test_inspection_failure_refuses_instead_of_allowing(self):
        with patch.object(policy.subprocess, 'run', side_effect=OSError('unavailable')):
            self.assertEqual(policy.main(['--repo', str(self.repo), '--tip', self.baseline,
                                          '--public-base', self.baseline]), 1)

    def test_inherited_git_context_cannot_redirect_the_explicit_repository(self):
        other = Path(self.temp.name) / 'other'
        self.git('init', '-q', str(other))
        with patch.dict(os.environ, {'GIT_DIR': str(other / '.git'), 'GIT_WORK_TREE': str(other)}):
            actual = Path(policy.git(self.repo, 'rev-parse', '--show-toplevel').decode().strip())
            self.assertEqual(actual.resolve(), self.repo.resolve())

    def test_inherited_git_context_cannot_disguise_a_manifest_inside_the_checkout(self):
        self.port_fixture()
        other = Path(self.temp.name) / 'other'
        self.git('init', '-q', str(other))
        # Share only synthetic immutable objects; a different worktree inventory
        # must not make a candidate-controlled policy look externally installed.
        (other / '.git/objects/info/alternates').write_bytes(
            ((self.repo / '.git/objects').as_posix() + '\n').encode())
        options = self.pin(path=self.repo / 'candidate-policy.json')
        with patch.dict(os.environ, {'GIT_DIR': str(other / '.git'), 'GIT_WORK_TREE': str(other)}):
            self.refused(**options)

    def test_shallow_history_is_refused(self):
        (self.repo / '.git/shallow').write_text(self.baseline + '\n', encoding='ascii')
        with self.assertRaises(policy.HistoryError):
            self.inspect(self.baseline)

    def test_local_grafts_are_refused(self):
        (self.repo / '.git/info/grafts').write_text(self.baseline + '\n', encoding='ascii')
        with self.assertRaises(policy.HistoryError):
            self.inspect(self.baseline)

    def test_installed_hook_decides_real_history_without_opening_a_transport(self):
        self.write('bundled/example/p.py', 'PRIVATE_PRODUCT_FIXTURE\n')
        private = self.commit('private product')
        self.git('rm', '-qr', 'bundled')
        clean_tip = self.commit('private source removed at tip')
        self.git('remote', 'add', 'private', 'https://example.invalid/owner/private.git')
        installer.install(self.repo, self.baseline, private, 'private')
        allowed = self.installed_hook(self.baseline)
        self.assertEqual(allowed.returncode, 0, allowed.stderr.decode())
        refused = self.installed_hook(clean_tip)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn(b'private plugin material', refused.stderr)

    def installed_hook(self, tip, extra=b'', remote='https://example.invalid/owner/public.git'):
        env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        env.update(GIT_ALLOW_PROTOCOL='', GIT_TERMINAL_PROMPT='0')
        directory = self.repo / '.git/hooks/lds-private-boundary'
        update = f'refs/heads/main {tip} refs/heads/main {"0" * 40}\n'.encode() + extra
        return subprocess.run([sys.executable, '-B', str(directory / 'private_plugin_pre_push.py'),
                               '--config', str(directory / 'guard.json'), 'private', remote],
                              input=update, cwd=self.repo, env=env, capture_output=True, timeout=60)

    def test_install_preserves_legacy_hook_and_survives_checkout_and_reinstall(self):
        original = self.repo / '.git/hooks/pre-push'
        original.write_text('#!/bin/sh\nexit 7\n', encoding='utf-8')
        original.chmod(original.stat().st_mode | 0o111)
        self.git('remote', 'add', 'private', 'https://example.invalid/owner/private.git')
        installed = installer.install(self.repo, self.baseline, self.baseline, 'private')
        self.assertTrue(installed['existing_hook_preserved'])
        config_path = self.repo / '.git/hooks/lds-private-boundary/guard.json'
        import json
        before = json.loads(config_path.read_text())
        installer.install(self.repo, self.baseline, self.baseline, 'private')
        self.assertEqual(json.loads(config_path.read_text())['previous_hook'], before['previous_hook'])
        self.git('checkout', '-q', '--detach', self.baseline)
        self.assertTrue(original.exists())
        update = f'refs/heads/main {self.baseline} refs/heads/main {"0" * 40}\n'.encode()
        self.assertEqual(hook_runner.run(config_path, 'private', 'https://example.invalid/owner/private.git', update), 1)

    def test_install_refuses_worktree_hooks_without_modifying_them(self):
        self.git('remote', 'add', 'private', 'https://example.invalid/owner/private.git')
        self.git('config', 'core.hooksPath', '.githooks')
        self.write('.githooks/pre-push', '#!/bin/sh\nexit 7\n')
        before = {str(p.relative_to(self.repo)): p.read_bytes()
                  for p in (self.repo / '.githooks').rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, 'shared Git hooks'):
            installer.install(self.repo, self.baseline, self.baseline, 'private')
        after = {str(p.relative_to(self.repo)): p.read_bytes()
                 for p in (self.repo / '.githooks').rglob('*') if p.is_file()}
        self.assertEqual(after, before)
        self.assertFalse((self.repo / '.git/hooks/lds-private-boundary').exists())

    def test_linked_worktree_install_uses_common_hooks_outside_checkout(self):
        self.git('remote', 'add', 'private', 'https://example.invalid/owner/private.git')
        linked = Path(self.temp.name) / 'linked'
        self.git('worktree', 'add', '-q', '--detach', str(linked), self.baseline)
        result = installer.install(linked, self.baseline, self.baseline, 'private')
        self.assertTrue(result['installed'])
        shared = self.repo / '.git/hooks'
        self.assertTrue((shared / 'pre-push').is_file())
        self.assertTrue((shared / 'lds-private-boundary/guard.json').is_file())
        self.assertFalse((linked / '.githooks').exists())
        hook = Path(policy.git(linked, 'rev-parse', '--path-format=absolute',
                               '--git-path', 'hooks/pre-push').decode().strip())
        self.assertEqual(hook.resolve(), (shared / 'pre-push').resolve())

    def test_remote_alias_is_not_a_private_destination_proof(self):
        self.git('remote', 'add', 'private', 'https://example.invalid/owner/private.git')
        installer.install(self.repo, self.baseline, self.baseline, 'private')
        config = self.repo / '.git/hooks/lds-private-boundary/guard.json'
        update = f'refs/heads/main {self.baseline} refs/heads/main {"0" * 40}\n'.encode()
        with patch.object(hook_runner, 'check_history', side_effect=policy.HistoryError('refused')):
            self.assertEqual(hook_runner.run(config, 'private', 'https://example.invalid/owner/public.git', update), 1)
            self.assertEqual(hook_runner.run(config, 'renamed', 'git@example.invalid:owner/private.git', update), 0)
            self.assertEqual(hook_runner.run(config, 'private', 'https://example.invalid/owner/private.git/other', update), 1)

    def port_fixture(self, unchanged=False):
        """Approval data is synthetic; never inventory or approve the real LDS export."""
        self.port_content = 'print("public core")\n' if unchanged else 'print("ported public core")\n'
        self.write('bundled/video/core.py', self.port_content)
        self.write('bundled/manga/secret.py', 'UNRELEASED_FIXTURE\n')
        self.private_source = self.commit('synthetic private snapshot')
        self.git('checkout', '-q', '--detach', self.baseline)
        self.write('public.md', 'Previously published origin\n')
        self.origin = self.commit('public origin after installed baseline')
        self.write('bundled/video/core.py', self.port_content)
        self.tip = self.commit('reviewed public port fixture')
        self.review = hashlib.sha256(b'Synthetic review fixture, not an LDS approval').hexdigest()
        self.manifest = self.manifest_for(self.tip, unchanged=unchanged)
        self.git('remote', 'add', 'private', 'https://example.invalid/owner/private.git')

    def manifest_for(self, tip, unchanged=False):
        source_blob = self.git('rev-parse', self.origin + ':core.py')
        records = []
        products = set()
        for commit in self.git('rev-list', tip, '--not', self.origin, '--').splitlines():
            entries = []
            for mode, kind, blob, name in policy.tree_entries(self.repo, commit):
                if name.startswith('bundled/'):
                    products.add(name.split('/')[1])
                    entries.append({'path': name, 'mode': mode, 'type': kind, 'blob': blob,
                                    'provenance': {
                                        'kind': 'unchanged' if unchanged else 'reviewed_port',
                                        'sources': [{'path': 'core.py', 'mode': '100644', 'blob': source_blob}],
                                        'evidence_sha256': self.review}})
            records.append({'commit': commit, 'tree': self.git('rev-parse', commit + '^{tree}'),
                            'parents': self.git('show', '-s', '--format=%P', commit).split(),
                            'exceptions': entries})
        return {'schema_version': 1, 'public_base': self.baseline, 'private_source': self.private_source,
                'public_origin': self.origin, 'tip': tip, 'tip_tree': self.git('rev-parse', tip + '^{tree}'),
                'review_sha256': self.review, 'products': sorted(products), 'commits': records}

    def pin(self, manifest=None, path=None, raw=None):
        manifest = self.manifest if manifest is None else manifest
        content = json.dumps(manifest, ensure_ascii=True).encode() if raw is None else raw
        path = path or Path(self.temp.name) / 'reviewed-fixture.json'
        path.write_bytes(content)
        return {'public_port_manifest': path, 'public_port_manifest_sha256': hashlib.sha256(content).hexdigest(),
                'public_port_review_sha256': self.review}

    def approved(self, manifest=None, tip=None, **options):
        options = options or self.pin(manifest)
        return policy.check_history(self.repo, tip or self.tip, self.baseline, self.private_source, **options)

    def refused(self, manifest=None, tip=None, **options):
        try:
            result = self.approved(manifest, tip, **options)
        except policy.HistoryError:
            return
        self.assertFalse(result['allowed'])

    def wheel_fixture(self, content=None, path=WHEEL_PATH):
        self.port_fixture()
        content = synthetic_wheel() if content is None else content
        destination = self.repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        self.tip = self.commit('synthetic generated wheel approval')
        self.manifest = self.manifest_for(self.tip)
        self.wheel_entry = next(entry for entry in self.manifest['commits'][0]['exceptions']
                                if entry['path'] == path)
        self.wheel_entry['provenance'].update(kind='generated', sources=[], resource=resource_for(content))

    def test_generated_wheel_exact_git_blob_is_approved_without_fabricated_main_source(self):
        self.wheel_fixture()
        self.assertTrue(self.approved()['allowed'])
        self.assertFalse(self.inspect(private_source=self.private_source)['allowed'])
        # The guard must inspect the pinned object, never mutable checkout bytes.
        (self.repo / WHEEL_PATH).write_bytes(b'uncommitted replacement, not approved')
        self.assertTrue(self.approved()['allowed'])
        self.wheel_entry['provenance']['resource']['sha256'] = hashlib.sha256(
            (self.repo / WHEEL_PATH).read_bytes()).hexdigest()
        self.refused()

    def test_generated_wheel_real_antlr_blob_passes_only_with_synthetic_explicit_approval(self):
        path = ('bundled/seedvr2/resources/wheels/'
                'antlr4_python3_runtime-4.9.3+lds.1-py3-none-any.whl')
        # Read the actual tracked blob, without executing or modifying the asset.
        content = policy.git(SCRIPTS.parent, 'cat-file', 'blob', 'HEAD:' + path)
        self.assertEqual(hashlib.sha256(content).hexdigest(),
                         '4e909ac01d54970b10622e90c2645dad8b186d4d79b5864fa60bb155379173ef')
        self.wheel_fixture(content, path)
        resource = self.wheel_entry['provenance']['resource']
        self.assertEqual((resource['size'], len(resource['members'])), (144376, 61))
        self.assertTrue(self.approved()['allowed'])
        self.wheel_entry['provenance'].pop('resource')
        self.refused()

    def test_generated_wheel_scope_schema_and_exhaustive_inventory_fail_closed(self):
        self.wheel_fixture()
        wheel_index = self.manifest['commits'][0]['exceptions'].index(self.wheel_entry)
        mutations = [
            lambda e: e['provenance'].pop('resource'),
            lambda e: e['provenance'].update(kind='reviewed_port'),
            lambda e: e['provenance'].update(kind='unchanged'),
            lambda e: e['provenance'].update(kind='reviewed_infrastructure'),
            lambda e: e['provenance'].update(sources=[{'path': 'core.py', 'mode': '100644',
                                                      'blob': self.git('rev-parse', self.origin + ':core.py')}]),
            lambda e: e.update(mode='100755'),
            lambda e: e['provenance'].update(evidence_sha256='unreviewed'),
            lambda e: e['provenance']['resource'].update(type='zip'),
            lambda e: e['provenance']['resource'].update(unknown=True),
            lambda e: e['provenance']['resource'].update(sha256='0' * 64),
            lambda e: e['provenance']['resource'].update(size=True),
            lambda e: e['provenance']['resource'].update(size=22),
            lambda e: e['provenance']['resource'].update(members=[]),
            lambda e: e['provenance']['resource']['members'][0].update(sha256='0' * 64),
            lambda e: e['provenance']['resource']['members'][0].update(size=0),
            lambda e: e['provenance']['resource']['members'].append(
                copy.deepcopy(e['provenance']['resource']['members'][0])),
            lambda e: e['provenance']['resource']['members'].append(
                {'path': 'unlisted.py', 'size': 0, 'sha256': hashlib.sha256(b'').hexdigest()}),
            lambda e: e['provenance']['resource'].pop('external_source'),
            lambda e: e['provenance']['resource']['external_source'].update(sha256='unverified'),
        ]
        paths = ['bundled/manga/resources/wheels/fixture-1.0-py3-none-any.whl',
                 'bundled/seedvr2/resources/fixture-1.0-py3-none-any.whl',
                 'bundled/seedvr2/resources/wheels/nested/fixture-1.0-py3-none-any.whl',
                 'bundled/seedvr2/resources/wheels/fixture-1.0-cp312-win_amd64.whl',
                 'bundled/seedvr2/resources/wheels/fixture.ldsplugin',
                 'bundled/seedvr2/resources/wheels/transition-pack.zip',
                 'bundled/seedvr2/resources/wheels/fixture.tar.gz']
        mutations += [lambda e, path=path: e.update(path=path) for path in paths]
        urls = ['https://pypi.org/project/antlr4-python3-runtime/4.9.3/',
                'https://files.pythonhosted.org/packages/latest/source.tar.gz',
                UPSTREAM_SOURCE['url'] + '?replacement=1',
                UPSTREAM_SOURCE['url'].replace('https://', 'http://'),
                UPSTREAM_SOURCE['url'].replace('https://', 'https://user@')]
        mutations += [lambda e, url=url: e['provenance']['resource']['external_source'].update(url=url)
                      for url in urls]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                candidate = copy.deepcopy(self.manifest)
                mutate(candidate['commits'][0]['exceptions'][wheel_index])
                self.refused(candidate)

    def verify_resource(self, content, resource):
        entry = {'path': WHEEL_PATH, 'mode': '100644',
                 'provenance': {'kind': 'generated', 'resource': resource}}
        port_policy.wheel_descriptor(entry)
        port_policy.verify_wheel(content, resource, WHEEL_PATH.rsplit('/', 1)[-1])

    def test_generated_resource_rejects_an_arbitrary_zip_and_private_product_contents(self):
        self.wheel_fixture(synthetic_wheel([('payload.py', b'INERT_FIXTURE = True\n')], metadata=False))
        self.refused()
        for name in ('bundled/manga/plugin.json', 'payload.exe', 'library.PYD', 'library.so.1',
                     'startup.pth', 'fixture-1.0.data/scripts/start.py'):
            content = synthetic_wheel([(name, b'INERT_PRIVATE_PRODUCT_FIXTURE\n')])
            with self.subTest(member=name), self.assertRaises(port_policy.ManifestError):
                self.verify_resource(content, resource_for(content))

    def test_generated_wheel_metadata_must_match_its_pure_python_identity(self):
        wheel = b'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
        metadata = b'Metadata-Version: 2.1\nName: fixture\nVersion: 1.0\n'
        for path, content in (
                ('WHEEL', wheel.replace(b'true', b'false')),
                ('WHEEL', wheel.replace(b'py3-none-any', b'cp314-cp314-win_amd64')),
                ('WHEEL', wheel + b'Tag: py3-none-any\n'),
                ('WHEEL', wheel + b'\nUNREVIEWED_EXECUTABLE_PAYLOAD'),
                ('METADATA', metadata.replace(b'Name: fixture', b'Name: another')),
                ('METADATA', metadata.replace(b'Version: 1.0', b'Version: 9.0')),
                ('METADATA', metadata + b'Name: fixture\n')):
            archive = synthetic_wheel([('fixture-1.0.dist-info/' + path, content)])
            with self.subTest(field=path, content=content), self.assertRaises(port_policy.ManifestError):
                self.verify_resource(archive, resource_for(archive))

    def test_generated_wheel_rejects_unsafe_paths_duplicates_and_non_regular_members(self):
        names = ['../private.py', '/private.py', 'a\\private.py', 'a//private.py',
                 'a/CON.py', 'a/trailing.', 'a/stream:ads', 'a/private.zip', 'a/private.ldsplugin',
                 'a/other.whl', 'a/transition-pack.zip', 'a/\u00e9.py', 'a/' + 'x' * 81]
        for name in names:
            with self.subTest(path=name):
                content = synthetic_wheel([(name, b'inert')])
                with self.assertRaises(port_policy.ManifestError):
                    self.verify_resource(content, resource_for(content))
        for entries in [[('a/file.py', b'one'), ('a/FILE.py', b'two')],
                        [('a/child.py', b'one'), ('A', b'file replacing directory')]]:
            content = synthetic_wheel(entries)
            with self.assertRaises(port_policy.ManifestError):
                self.verify_resource(content, resource_for(content))
        for attribute in [(0o120777 << 16), (0o040755 << 16), (0o104644 << 16),
                          (0o100644 << 16) | 0x400, (0o100644 << 16) | 0x10]:
            with self.subTest(attribute=attribute):
                content = synthetic_wheel(configure=lambda info: setattr(info, 'external_attr', attribute))
                with self.assertRaises(port_policy.ManifestError):
                    self.verify_resource(content, resource_for(content))

    def test_generated_wheel_rejects_hidden_zip_metadata_and_payload(self):
        original = synthetic_wheel()
        expected = resource_for(original)
        variants = [b'prefix' + original, original + b'trailing payload', b'invalid zip']
        for field, value in [('extra', b'\xfe\xca\x00\x00'), ('comment', b'unreviewed'),
                             ('compress_type', zipfile.ZIP_BZIP2)]:
            variants.append(synthetic_wheel(configure=lambda info, f=field, v=value: setattr(info, f, v)))
        # EOCD archive comment, encryption/data-descriptor flags, local name mismatch.
        commented = bytearray(original)
        struct.pack_into('<H', commented, len(commented) - 2, 3)
        variants.append(bytes(commented) + b'abc')
        with zipfile.ZipFile(io.BytesIO(original)) as wheel:
            central = wheel.start_dir
        for flag in (1, 8, 0x4000):
            altered = bytearray(original)
            struct.pack_into('<H', altered, 6, flag)
            struct.pack_into('<H', altered, central + 8, flag)
            variants.append(bytes(altered))
        altered = bytearray(original)
        altered[30] = ord('x')
        variants.append(bytes(altered))
        # A second, unlisted stream inside a member's compressed byte range.
        altered = bytearray(original[:central] + b'hidden' + original[central:])
        packed_size = struct.unpack_from('<I', altered, 18)[0] + 6
        struct.pack_into('<I', altered, 18, packed_size)
        struct.pack_into('<I', altered, central + 6 + 20, packed_size)
        struct.pack_into('<I', altered, len(altered) - 6, central + 6)
        variants.append(bytes(altered))
        for index, content in enumerate(variants):
            with self.subTest(variant=index):
                descriptor = copy.deepcopy(expected)
                descriptor.update(size=len(content), sha256=hashlib.sha256(content).hexdigest())
                with self.assertRaises(port_policy.ManifestError):
                    self.verify_resource(content, descriptor)

    def test_generated_wheel_enforces_object_and_decompression_budgets(self):
        content = synthetic_wheel()
        resource = resource_for(content)
        for limit, value in [('WHEEL_MAX_BYTES', len(content) - 1), ('WHEEL_MAX_MEMBERS', 0),
                             ('WHEEL_MAX_MEMBER', 1), ('WHEEL_MAX_EXPANDED', 1)]:
            with self.subTest(limit=limit), patch.object(port_policy, limit, value):
                with self.assertRaises(port_policy.ManifestError):
                    self.verify_resource(content, resource)
        # The actual stream expands beyond its lying ZIP headers and inventory.
        content = bytearray(synthetic_wheel([('fixture/__init__.py', b'x' * 100000)]))
        with zipfile.ZipFile(io.BytesIO(content)) as wheel:
            central = wheel.start_dir
        struct.pack_into('<I', content, 22, 1)
        struct.pack_into('<I', content, central + 24, 1)
        resource.update(size=len(content), sha256=hashlib.sha256(content).hexdigest())
        resource['members'][0].update(size=1, sha256=hashlib.sha256(b'x').hexdigest())
        with self.assertRaises(port_policy.ManifestError):
            self.verify_resource(bytes(content), resource)
        self.wheel_fixture()
        actual_git = policy.git
        oversized_blob = self.wheel_entry['blob']

        def guarded_git(repo, *args):
            if args == ('cat-file', '-s', oversized_blob):
                return str(port_policy.WHEEL_MAX_BYTES + 1).encode()
            if args == ('cat-file', 'blob', oversized_blob):
                self.fail('The guard materialized a blob before its size was approved')
            return actual_git(repo, *args)

        with patch.object(policy, 'git', side_effect=guarded_git):
            self.refused()

    def test_reviewed_infrastructure_requires_explicit_proof_without_fabricated_sources(self):
        self.port_fixture()
        self.manifest['commits'][0]['exceptions'][0]['provenance'].update(
            kind='reviewed_infrastructure', sources=[])
        self.assertTrue(self.approved()['allowed'])
        self.assertFalse(self.inspect(private_source=self.private_source)['allowed'])
        original = copy.deepcopy(self.manifest)
        for mutate in [lambda p: p.pop('evidence_sha256'), lambda p: p.update(evidence_sha256='unreviewed'),
                       lambda p: p.update(sources=[{'path': 'core.py', 'mode': '100644',
                                                   'blob': self.git('rev-parse', self.origin + ':core.py')}]),
                       lambda p: p.update(kind='reviewed_port'), lambda p: p.update(kind='generated')]:
            candidate = copy.deepcopy(original)
            mutate(candidate['commits'][0]['exceptions'][0]['provenance'])
            self.refused(candidate)
        # Even that category cannot approve an archive or a later tree implicitly.
        candidate = copy.deepcopy(original)
        candidate['commits'][0]['exceptions'][0]['path'] = 'bundled/video/hidden.zip'
        self.refused(candidate)
        self.write('bundled/video/extra.py', 'UNREVIEWED_NEW_INFRASTRUCTURE = True\n')
        self.refused(tip=self.commit('unapproved later infrastructure'))

    def test_exact_reviewed_port_and_unchanged_public_move_are_allowed(self):
        self.port_fixture(unchanged=True)
        self.assertFalse(self.inspect(private_source=self.private_source)['allowed'])
        self.assertTrue(self.approved()['allowed'])
        self.assertEqual(self.approved()['commits_checked'], 2, 'The installed baseline must not advance')
        self.assertIsNotNone(policy.private_plugin_path_reason('bundled/video/core.py'))
        self.manifest['commits'][0]['exceptions'][0]['provenance']['kind'] = 'generated'
        self.assertTrue(self.approved()['allowed'])

    def test_manifest_cannot_be_its_own_approval_or_come_from_any_checkout(self):
        self.port_fixture()
        self.assertTrue(self.approved()['allowed'])
        options = self.pin()
        for key in options:
            incomplete = dict(options)
            incomplete.pop(key)
            with self.subTest(missing=key):
                self.refused(**incomplete)
        for key in ('public_port_manifest_sha256', 'public_port_review_sha256'):
            with self.subTest(wrong=key):
                self.refused(**(options | {key: '0' * 64}))
        options['public_port_manifest'].write_bytes(b'{}')
        self.refused(**options)
        options['public_port_manifest'].unlink()
        self.refused(**options)
        self.refused(**self.pin(path=self.repo / 'candidate-policy.json'))
        linked = Path(self.temp.name) / 'linked'
        self.git('worktree', 'add', '-q', '--detach', str(linked), self.origin)
        self.refused(**self.pin(path=linked / 'candidate-policy.json'))

    def test_duplicate_keys_entries_and_schema_ambiguity_fail_closed(self):
        self.port_fixture()
        raw = json.dumps(self.manifest).encode()
        duplicates = [b'{"schema_version":1,' + raw[1:],
                      raw.replace(b'"kind": "reviewed_port"', b'"kind":"unchanged","kind":"reviewed_port"')]
        for value in duplicates + [b'[]', b'null', b'{broken', b'{"value":NaN}']:
            with self.subTest(raw=value[:50]):
                self.refused(**self.pin(raw=value))
        for mutate in (
                lambda m: m.update(schema_version=True),
                lambda m: m.update(unknown='candidate-controlled policy'),
                lambda m: m['commits'].append(copy.deepcopy(m['commits'][0])),
                lambda m: m['commits'][0]['exceptions'].append(copy.deepcopy(m['commits'][0]['exceptions'][0])),
                lambda m: m['products'].append('video'),
                lambda m: m.update(products=['video', 'canvas']),
                lambda m: m['commits'][0]['exceptions'][0]['provenance'].update(sources=[])):
            candidate = copy.deepcopy(self.manifest)
            mutate(candidate)
            self.refused(candidate)

    def test_each_context_field_and_public_provenance_is_exact(self):
        self.port_fixture()
        for key, value in [('public_base', self.origin), ('private_source', self.origin),
                           ('public_origin', self.private_source), ('tip', self.origin),
                           ('tip_tree', self.git('rev-parse', self.origin + '^{tree}'))]:
            with self.subTest(field=key):
                self.refused(copy.deepcopy(self.manifest) | {key: value})
        for key, value in [('commit', self.origin), ('tree', self.git('rev-parse', self.origin + '^{tree}')),
                           ('parents', [self.baseline])]:
            candidate = copy.deepcopy(self.manifest)
            candidate['commits'][0][key] = value
            self.refused(candidate)
        for key, value in [('path', 'bundled/video/renamed.py'), ('mode', '100755'),
                           ('blob', self.git('rev-parse', self.baseline + ':core.py'))]:
            candidate = copy.deepcopy(self.manifest)
            candidate['commits'][0]['exceptions'][0][key] = value
            self.refused(candidate)
        for key, value in [('path', 'absent.py'), ('mode', '100755'), ('blob', '0' * 40)]:
            candidate = copy.deepcopy(self.manifest)
            candidate['commits'][0]['exceptions'][0]['provenance']['sources'][0][key] = value
            self.refused(candidate)
        candidate = copy.deepcopy(self.manifest)
        candidate['commits'][0]['exceptions'][0]['provenance']['kind'] = 'unchanged'
        self.refused(candidate)

    def test_manifest_is_not_a_product_wildcard_or_a_global_blob_exception(self):
        self.port_fixture()
        for name, content in [('bundled/video/new.py', self.port_content),
                              ('backend/copied.py', self.port_content),
                              ('bundled/video/core.py', self.port_content + '# one extra byte\n')]:
            self.git('checkout', '-q', '--detach', self.tip)
            self.write(name, content)
            new_tip = self.commit('unapproved content')
            self.refused(tip=new_tip)
            # Even a graph updated by a reviewer must enumerate each actual tuple.
            candidate = self.manifest_for(new_tip)
            candidate['commits'][0]['exceptions'] = copy.deepcopy(self.manifest['commits'][0]['exceptions'])
            self.refused(candidate, tip=new_tip)

    def test_mode_changes_and_tag_annotations_need_separate_approval(self):
        self.port_fixture()
        self.git('update-index', '--chmod=+x', 'bundled/video/core.py')
        self.git('commit', '-q', '-m', 'unreviewed executable bit')
        tip = self.git('rev-parse', 'HEAD')
        self.refused(tip=tip)
        candidate = self.manifest_for(tip)
        candidate['commits'][0]['exceptions'][0]['mode'] = '100644'
        self.refused(candidate, tip=tip)
        self.git('tag', '-a', 'export', self.tip, '-m', 'UNREVIEWED_ANNOTATION_FIXTURE')
        self.refused(tip=self.git('rev-parse', 'export'))

    def test_deleted_private_history_and_merged_side_branch_cannot_borrow_tip_approval(self):
        self.port_fixture()
        self.write('bundled/video/unreviewed.py', 'UNREVIEWED_FIXTURE\n')
        hidden = self.commit('unreviewed intermediate version')
        self.git('rm', '-q', 'bundled/video/unreviewed.py')
        clean = self.commit('clean final tree')
        candidate = self.manifest_for(clean)
        for entry in candidate['commits']:
            entry['exceptions'] = [e for e in entry['exceptions'] if not e['path'].endswith('unreviewed.py')]
        self.refused(candidate, tip=clean)
        candidate['commits'] = [c for c in candidate['commits'] if c['commit'] != hidden]
        self.refused(candidate, tip=clean)
        self.git('checkout', '-q', '--detach', self.tip)
        self.write('another-public.py', 'PUBLIC = True\n')
        self.commit('public side')
        self.git('merge', '-q', '--no-ff', clean, '-m', 'merge cleaned branch')
        merged = self.git('rev-parse', 'HEAD')
        self.refused(tip=merged)
        candidate = self.manifest_for(merged)
        candidate['commits'] = [c for c in candidate['commits'] if c['commit'] != hidden]
        self.refused(candidate, tip=merged)

    def test_non_source_products_archives_modes_and_ambiguous_paths_are_never_exceptions(self):
        self.port_fixture()
        for path in ['bundled/manga/file.py', 'bundled/VIDEO/file.py', 'BUNDLED/video/file.py',
                     'bundled/video/file.ldsplugin', 'bundled/video/transition-pack.zip',
                     'bundled/video/renamed.zip', 'bundled/video/package.whl', 'bundled/video/package.tar.gz',
                     'bundled/video/../core.py', 'bundled\\video\\core.py', 'bundled/video//core.py',
                     'bundled/video/nested/BUNDLED/core.py', 'bundled/video/line\nname.py']:
            candidate = copy.deepcopy(self.manifest)
            candidate['commits'][0]['exceptions'][0]['path'] = path
            self.refused(candidate)
        for mode, kind in [('120000', 'blob'), ('160000', 'commit')]:
            candidate = copy.deepcopy(self.manifest)
            candidate['commits'][0]['exceptions'][0].update(mode=mode, type=kind)
            self.refused(candidate)
        self.write('bundled/manga/private.py', 'UNRELEASED_FIXTURE\n')
        tip = self.commit('unknown product')
        self.refused(self.manifest_for(tip), tip=tip)

    def test_valid_manifest_does_not_disable_shallow_graft_replace_or_blob_guards(self):
        self.port_fixture()
        blob = self.git('rev-parse', self.tip + ':bundled/video/core.py')
        self.refused(tip=blob)
        shallow = self.repo / '.git/shallow'
        shallow.write_text(self.baseline + '\n', encoding='ascii')
        self.refused()
        shallow.unlink()
        graft = self.repo / '.git/info/grafts'
        graft.write_text(self.tip + ' ' + self.baseline + '\n', encoding='ascii')
        self.refused()
        graft.unlink()
        self.git('replace', self.tip, self.origin)
        # Replacement must neither hide the exact port nor change its approved graph.
        self.assertTrue(self.approved()['allowed'])
        self.assertFalse(self.inspect(self.tip, private_source=self.private_source)['allowed'])

    def test_actual_symlink_and_gitlink_objects_cannot_receive_pinned_exceptions(self):
        self.port_fixture()
        for mode, blob in [('120000', self.git('rev-parse', self.tip + ':bundled/video/core.py')),
                           ('160000', self.private_source)]:
            self.git('checkout', '-q', '--detach', self.tip)
            self.git('update-index', '--add', '--cacheinfo', f'{mode},{blob},bundled/video/reference')
            self.git('commit', '-q', '-m', 'non-regular entry fixture')
            tip = self.git('rev-parse', 'HEAD')
            self.refused(self.manifest_for(tip), tip=tip)

    def test_install_refuses_concurrent_hook_change_without_replacing_policy(self):
        self.port_fixture()
        installer.install(self.repo, self.baseline, self.private_source, 'private')
        hook = self.repo / '.git/hooks/pre-push'
        config = hook.parent / 'lds-private-boundary/guard.json'
        before = config.read_bytes()
        original_check = installer._check_history

        def changing_hook(*args, **kwargs):
            result = original_check(*args, **kwargs)
            hook.write_bytes(b'#!/bin/sh\nexit 9\n')
            return result

        with patch.object(installer, '_check_history', side_effect=changing_hook), self.assertRaises(ValueError):
            installer.install(self.repo, self.baseline, self.private_source, 'private', **self.pin())
        self.assertEqual(hook.read_bytes(), b'#!/bin/sh\nexit 9\n')
        self.assertEqual(config.read_bytes(), before)

    def test_approved_port_install_persists_exact_bytes_and_still_chains_legacy_hook(self):
        self.port_fixture()
        original = self.repo / '.git/hooks/pre-push'
        original.write_text('#!/bin/sh\nexit 7\n', encoding='utf-8')
        options = self.pin()
        result = installer.install(self.repo, self.baseline, self.private_source, 'private', **options)
        self.assertTrue(result['existing_hook_preserved'])
        config_path = self.repo / '.git/hooks/lds-private-boundary/guard.json'
        config = json.loads(config_path.read_bytes())
        installed = Path(config['public_port_manifest'])
        self.assertNotEqual(installed, options['public_port_manifest'])
        self.assertEqual(installed.read_bytes(), options['public_port_manifest'].read_bytes())
        self.assertEqual(config['public_base'], self.baseline)
        self.assertEqual(config['private_source'], self.private_source)
        self.assertEqual(config['public_port_review_sha256'], self.review)
        options['public_port_manifest'].unlink()
        self.git('checkout', '-q', '--detach', self.baseline)
        installer.install(self.repo, self.baseline, self.private_source, 'private')
        self.assertEqual(json.loads(config_path.read_bytes()), config)
        refusal = self.installed_hook(self.tip)
        self.assertNotEqual(refusal.returncode, 0)
        self.assertIn(b'existing repository policy', refusal.stderr)
        self.assertNotEqual(self.installed_hook(self.tip, remote='https://example.invalid/owner/private.git').returncode, 0)

    def test_installed_v2_hook_checks_all_refs_and_does_not_trust_remote_alias(self):
        self.port_fixture()
        installer.install(self.repo, self.baseline, self.private_source, 'private', **self.pin())
        self.assertEqual(self.installed_hook(self.tip).returncode, 0)
        mixed = f'refs/heads/extra {self.private_source} refs/heads/extra {"0" * 40}\n'.encode()
        self.assertNotEqual(self.installed_hook(self.tip, extra=mixed).returncode, 0)
        deletion = f'refs/heads/old {"0" * 40} refs/heads/old {self.tip}\n'.encode()
        self.assertEqual(self.installed_hook(self.tip, extra=deletion).returncode, 0)
        self.assertNotEqual(self.installed_hook(self.tip, extra=b'malformed\n').returncode, 0)
        self.assertEqual(self.installed_hook(self.private_source, remote='https://example.invalid/owner/private.git').returncode, 0)
        config_path = self.repo / '.git/hooks/lds-private-boundary/guard.json'
        config = json.loads(config_path.read_bytes())
        Path(config['public_port_manifest']).write_bytes(b'{}')
        self.assertNotEqual(self.installed_hook(self.tip).returncode, 0)

    def test_invalid_approval_and_changed_installed_trust_never_replace_a_hook(self):
        self.port_fixture()
        original = self.repo / '.git/hooks/pre-push'
        original.write_bytes(b'#!/bin/sh\nexit 7\n')
        before = original.read_bytes()
        options = self.pin()
        with self.assertRaises(ValueError):
            installer.install(self.repo, self.baseline, self.private_source, 'private',
                              **(options | {'public_port_manifest_sha256': '0' * 64}))
        self.assertEqual(original.read_bytes(), before)
        self.assertFalse((original.parent / 'lds-private-boundary').exists())
        installer.install(self.repo, self.baseline, self.private_source, 'private')
        config_path = original.parent / 'lds-private-boundary/guard.json'
        before = (original.read_bytes(), config_path.read_bytes())
        for base, source in [(self.origin, self.private_source), (self.baseline, self.origin)]:
            with self.assertRaisesRegex(ValueError, 'trust inputs'):
                installer.install(self.repo, base, source, 'private', **options)
            self.assertEqual((original.read_bytes(), config_path.read_bytes()), before)
        self.git('remote', 'set-url', 'private', 'https://example.invalid/owner/another.git')
        with self.assertRaisesRegex(ValueError, 'trust inputs'):
            installer.install(self.repo, self.baseline, self.private_source, 'private', **options)
        self.assertEqual((original.read_bytes(), config_path.read_bytes()), before)

    def test_installer_copies_the_verified_snapshot_and_publishes_config_last(self):
        self.port_fixture()
        options = self.pin()
        expected = options['public_port_manifest'].read_bytes()
        original_check = installer._check_history

        def changing_input(*args, **kwargs):
            result = original_check(*args, **kwargs)
            options['public_port_manifest'].write_bytes(b'changed after validation')
            return result

        with patch.object(installer, '_check_history', side_effect=changing_input):
            installer.install(self.repo, self.baseline, self.private_source, 'private', **options)
        config_path = self.repo / '.git/hooks/lds-private-boundary/guard.json'
        config = json.loads(config_path.read_bytes())
        self.assertEqual(Path(config['public_port_manifest']).read_bytes(), expected)
        self.assertEqual(self.installed_hook(self.tip).returncode, 0)
        before = config_path.read_bytes()
        write = installer.atomic_write

        def interrupted(path, content):
            if path.name == 'public_port_manifest.py':
                raise OSError('simulated installation interruption')
            return write(path, content)

        with patch.object(installer, 'atomic_write', side_effect=interrupted), self.assertRaises(OSError):
            installer.install(self.repo, self.baseline, self.private_source, 'private')
        self.assertEqual(config_path.read_bytes(), before)
        self.assertEqual(self.installed_hook(self.tip).returncode, 0)

    def test_incomplete_or_self_extended_guard_configuration_is_refused(self):
        self.port_fixture()
        installer.install(self.repo, self.baseline, self.private_source, 'private', **self.pin())
        config_path = self.repo / '.git/hooks/lds-private-boundary/guard.json'
        config = json.loads(config_path.read_bytes())
        for field in hook_runner.MANIFEST_FIELDS:
            candidate = dict(config)
            candidate.pop(field)
            config_path.write_text(json.dumps(candidate), encoding='utf-8')
            self.assertNotEqual(self.installed_hook(self.tip).returncode, 0)
        for version in (True, 1, 3):
            config_path.write_text(json.dumps(config | {'schema_version': version}), encoding='utf-8')
            self.assertNotEqual(self.installed_hook(self.tip).returncode, 0)


if __name__ == '__main__':
    unittest.main()
