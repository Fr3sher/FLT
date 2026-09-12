"""Real Git DAGs: checking only the final tree would expose deleted products."""

from __future__ import annotations

import importlib.util
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('public_history', SCRIPTS / 'check_public_history.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
import install_public_push_guard as installer
import private_plugin_pre_push as hook_runner


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
