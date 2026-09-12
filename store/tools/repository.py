"""Small operator tool for a reviewed TUF repository, never shipped private keys.

Install store/tools/requirements.txt in a separate operator environment. Keep
the keys directory outside the served repository and source checkout. Publish
versioned metadata first and timestamp last; clients keep using the old snapshot
until that final atomic publication. Archive paths are immutable.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from filelock import FileLock
from packaging.version import Version
from securesystemslib.signer import CryptoSigner
from tuf.api.metadata import Metadata, MetaFile, Root, Snapshot, TargetFile, Targets, Timestamp

_media_spec = importlib.util.spec_from_file_location(
    'lds_store_media_contract', Path(__file__).resolve().parents[2] / 'backend/app/plugins/store/media_contract.py')
_media = importlib.util.module_from_spec(_media_spec)
_media_spec.loader.exec_module(_media)


def _plain_path(value, *, private=False):
    path = Path(value).absolute()
    for current in (path, *path.parents):
        try:
            info = current.lstat()
        except FileNotFoundError:
            info = None
        if info is not None:
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Symbolic links and junctions are not operator storage folders.')
            if current != path and not stat.S_ISDIR(info.st_mode):
                raise ValueError('An operator destination parent is not a directory.')
            if current == path and stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError('Operator files cannot be hardlinked.')
        if private and (current / '.git').exists():
            raise ValueError('Private artifacts must be kept outside source control.')
    return path.resolve()


def _public_tree(repo):
    """A public alias could expose a private directory after it is populated."""
    pending = [repo] if repo.exists() else []
    while pending:
        for entry in pending.pop().iterdir():
            meta = entry.lstat()
            if stat.S_ISLNK(meta.st_mode) or getattr(meta, 'st_file_attributes', 0) & 0x400:
                raise ValueError('The public tree cannot contain links to private or external storage.')
            if stat.S_ISDIR(meta.st_mode):
                pending.append(entry)


def _file_destination(path, data=None, *, immutable=False, private=False):
    _plain_path(path, private=private)
    if path.exists():
        if not path.is_file():
            raise ValueError('An operator file destination is not a regular file.')
        if immutable and path.read_bytes() != data:
            raise ValueError('A published immutable artifact cannot be replaced.')


def _atomic(path, data, *, immutable=False):
    _file_destination(path, data, immutable=immutable)
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        if path.read_bytes() != data:
            raise ValueError('A published immutable artifact cannot be replaced.')
        return
    fd, temporary = tempfile.mkstemp(prefix='.publish-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            try:
                # Same-filesystem linking publishes the complete file without
                # any interval in which a reader can observe a partial write.
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise ValueError('A published immutable artifact cannot be replaced.') from None
        else:
            os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _locations(repo, keys):
    repo, keys = _plain_path(repo), _plain_path(keys, private=True)
    if keys == repo or repo in keys.parents or keys in repo.parents:
        raise ValueError('Private keys and the public repository must be separate folders.')
    # An operator may run the tool from a cloned checkout, but never place keys
    # in any Git working tree. This also covers worktrees with a .git file.
    if any((parent / '.git').exists() for parent in (keys, *keys.parents)):
        raise ValueError('Private keys must be kept outside source control.')
    return repo, keys


def _private_location(repo, keys, value):
    if value is None:
        raise ValueError('Paid packages require an explicit private artifact folder.')
    private = _plain_path(value, private=True)
    for other in (repo, keys):
        if private == other or private in other.parents or other in private.parents:
            raise ValueError('Private artifacts, offline keys and public files must be separate folders.')
    return private


def _target(name):
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}
    if (not isinstance(name, str) or len(name) > 400 or not name.endswith('.ldsplugin')
            or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,179}', p)
                   or p in ('.', '..') or p.endswith('.') or p.split('.')[0].upper() in reserved
                   for p in name.split('/'))):
        raise ValueError('A package target must be a safe relative .ldsplugin path.')
    return name


def _price(value):
    if not isinstance(value, dict) or value.get('kind') not in ('free', 'paid'):
        raise ValueError('Invalid release price.')
    if value['kind'] == 'free':
        if set(value) != {'kind'}:
            raise ValueError('A free release cannot declare a commerce product.')
    elif (set(value) != {'kind', 'product'} or not isinstance(value.get('product'), str)
          or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value['product'])):
        raise ValueError('A paid release requires an explicit commerce product identifier.')
    return dict(value)


def _date(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except (AttributeError, TypeError, ValueError):
        raise ValueError('A release publication date must be an explicit timezone-aware ISO timestamp.') from None


def _expiry(days):
    return datetime.now(timezone.utc) + timedelta(days=days)


def _new_key(keys, name):
    signer = CryptoSigner.generate_ed25519()
    path = keys / (name + '.pem')
    keys.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        if os.name != 'nt':
            os.fchmod(stream.fileno(), 0o600)
        stream.write(signer.private_bytes)
    return signer


def _key(keys, name):
    return CryptoSigner(serialization.load_pem_private_key((keys / (name + '.pem')).read_bytes(), password=None))


def _current_key(repo, keys, role):
    """The root selects the signer even after an interrupted file rename."""
    root = Metadata.from_file(str(repo / 'metadata' / 'root.json')).signed
    allowed = set(root.roles[role].keyids)
    for path in sorted(keys.glob(role + '*.pem')):
        signer = _key(keys, path.stem)
        if signer.public_key.keyid in allowed:
            return signer
    raise ValueError('No available private key is authorized for this role by the current root.')


def _initialize(repo, keys):
    repo, keys = _locations(repo, keys)
    if (repo / 'metadata').exists() or (keys.exists() and any(keys.iterdir())):
        raise ValueError('Initialization requires a new repository and an empty private key folder.')
    signers = {name: _new_key(keys, name) for name in ('root-a', 'root-b', 'targets', 'snapshot', 'timestamp')}
    root = Metadata(Root(expires=_expiry(365)))
    for name in ('root-a', 'root-b'):
        root.signed.add_key(signers[name].public_key, 'root')
    root.signed.roles['root'].threshold = 2
    for name in ('targets', 'snapshot', 'timestamp'):
        root.signed.add_key(signers[name].public_key, name)
    root.sign(signers['root-a'])
    root.sign(signers['root-b'], append=True)
    data = root.to_bytes()
    _atomic(repo / 'metadata' / '1.root.json', data, immutable=True)
    _atomic(repo / 'metadata' / 'root.json', data)
    _atomic(repo / 'bootstrap.root.json', data, immutable=True)
    _publish(repo, keys, {'schema_version': 1, 'products': []}, {})


def _prepare(repo, keys, catalog, artifacts, private_artifacts):
    """Read and validate the complete publication before changing durable data."""
    history_path = keys / 'published.json'
    _plain_path(history_path, private=True)
    history = json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else {
        'targets': {}, 'releases': {}, 'access': {}}
    history.setdefault('access', {})
    if not isinstance(catalog, dict) or catalog.get('schema_version') != 1 or not isinstance(catalog.get('products'), list):
        raise ValueError('Invalid catalog format.')
    if not isinstance(artifacts, dict) or any(not isinstance(data, bytes) for data in artifacts.values()):
        raise ValueError('Artifacts must map target names to bytes.')
    entries, identities, products, media_entries = {}, set(), set(), {}
    for product in catalog['products']:
        if (not isinstance(product, dict) or not re.fullmatch(r'[a-z][a-z0-9_]{1,63}', product.get('id', ''))
                or product['id'] in products or not isinstance(product.get('releases'), list)
                or not 1 <= len(product['releases']) <= 100):
            raise ValueError('Invalid or duplicate catalog product.')
        products.add(product['id'])
        for release in product['releases']:
            try:
                manifest = release['manifest']
                if manifest['id'] != product['id']:
                    raise ValueError('Catalog product and manifest identities differ.')
                name, version = _target(release['target']), str(Version(manifest['version']))
                digest = release['manifest_sha256']
                if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                    raise ValueError('Invalid manifest digest.')
                if 'price' not in release:
                    raise ValueError('Every release requires an explicit free or paid classification.')
                price = _price(release['price'])
                identity = json.dumps([product['id'], version])
            except (KeyError, TypeError, AttributeError):
                raise ValueError('Invalid catalog release.') from None
            if name in entries:
                raise ValueError('A target cannot be shared by catalog releases, including free and paid.')
            if identity in identities:
                raise ValueError('A catalog contains a duplicate product version.')
            identities.add(identity)
            previous = history['releases'].get(identity)
            value = {'target': name, 'manifest_sha256': digest, 'price': price}
            if previous:
                # Legacy publisher history means public/free: that tool wrote
                # every package into the public tree, regardless of its label.
                old_value = {k: previous[k] for k in ('target', 'manifest_sha256')}
                old_value['price'] = previous.get('price', {'kind': 'free'})
                if old_value != value:
                    raise ValueError('A published product version and price are immutable. Publish a new version.')
            published = _date(release.get('published_at') or (previous or {}).get('published_at')
                              or datetime.now(timezone.utc).isoformat())
            if previous and previous.get('published_at') and published != previous['published_at']:
                raise ValueError('A published release date is immutable.')
            value['published_at'] = published
            history['releases'][identity] = value
            entries[name] = {'plugin_id': product['id'], 'version': version, 'price': price,
                             'published_at': published}
            for item in _media.parse_presentation(release.get('presentation'), product['id'], manifest['version']):
                if item['target'] in media_entries:
                    raise ValueError('A presentation target cannot be shared by releases.')
                media_entries[item['target']] = item
    if set(artifacts) - entries.keys() - media_entries.keys():
        raise ValueError('Every supplied artifact must belong to the reviewed catalog.')
    paid = any(e['price']['kind'] == 'paid' for e in entries.values())
    had_paid = any(v == 'paid' for v in history['access'].values())
    private = _private_location(repo, keys, private_artifacts) if paid or had_paid or private_artifacts is not None else None
    if paid or had_paid:
        _public_tree(repo)
    writes, targets, registry = [], {}, []
    for name, entry in entries.items():
        kind = entry['price']['kind']
        expected = history['targets'].get(name)
        old_access = history['access'].get(name, 'free') if expected else None
        if old_access is not None and old_access != kind:
            raise ValueError('A published target price is immutable; public bytes cannot become paid.')
        if name in artifacts:
            data = artifacts[name]
            digest = hashlib.sha256(data).hexdigest()
            if expected is not None and expected != digest:
                raise ValueError('A published package target is immutable, including withdrawn releases.')
        else:
            if expected is None:
                raise ValueError('The catalog references a package that has not been published.')
            digest = expected
            path = Path(name)
            source = (private / 'artifacts' if kind == 'paid' else repo / 'targets') / path.parent / (digest + '.' + path.name)
            _plain_path(source, private=kind == 'paid')
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('A retained immutable archive has been modified.')
        if len(data) > 512 * 1024 * 1024:
            raise ValueError('A plugin archive exceeds the supported size.')
        for old_name, old_digest in history['targets'].items():
            if old_digest == digest and history['access'].get(old_name, 'free') != kind:
                raise ValueError('Identical bytes cannot be both a public and a paid archive.')
        history['targets'][name] = digest
        history['access'][name] = kind
        path = Path(name)
        relative = path.parent / (digest + '.' + path.name)
        public_path = repo / 'targets' / relative
        _plain_path(public_path)
        if kind == 'paid' and public_path.exists():
            raise ValueError('Paid archive bytes already exist in the public repository.')
        destination = (private / 'artifacts' if kind == 'paid' else repo / 'targets') / relative
        _file_destination(destination, data, immutable=True, private=kind == 'paid')
        writes.append((destination, data))
        targets[name] = TargetFile.from_data(name, data, ['sha256'])
        if kind == 'paid':
            registry.append({'plugin_id': entry['plugin_id'], 'version': entry['version'],
                             'target': name, 'sha256': digest,
                             'file': (Path('artifacts') / relative).as_posix(),
                             'published_at': entry['published_at'], 'withdrawn': False})
    registry_path = private / 'registry.json' if private is not None else None
    # Reviewed inert images are readable before acquisition. They never enter
    # the paid archive registry and cannot alias .ldsplugin targets.
    for name, item in media_entries.items():
        path = Path(name)
        digest = path.name.split('.')[0]
        source = repo / 'targets' / path.parent / (digest + '.' + path.name)
        if name in artifacts:
            data = artifacts[name]
        else:
            _plain_path(source)
            data = source.read_bytes()
        _media.validate_image(data, item)
        if any(old_digest == digest and history['access'].get(old_name) == 'paid'
               for old_name, old_digest in history['targets'].items()):
            raise ValueError('Private archive bytes cannot be published as presentation media.')
        _file_destination(source, data, immutable=True)
        writes.append((source, data))
        targets[name] = TargetFile.from_data(name, data, ['sha256'])
    if registry_path:
        _file_destination(registry_path, private=True)
    return {'history_path': history_path, 'history': json.dumps(history, sort_keys=True).encode('utf-8'),
            'writes': writes, 'targets': targets, 'registry_path': registry_path,
            'registry': json.dumps({'releases': registry}, sort_keys=True, indent=2).encode('utf-8')}


def _publish(repo, keys, catalog, artifacts, private_artifacts=None, *, prepared=None):
    """Paid TargetInfo is public; paid archive bytes are exclusively private."""
    repo, keys = _locations(repo, keys)
    plan = prepared or _prepare(repo, keys, catalog, artifacts, private_artifacts)
    metadata = repo / 'metadata'
    old_path = metadata / 'targets.json'
    old = Metadata.from_file(str(old_path)) if old_path.exists() else None
    # Never reuse immutable metadata generations after interrupted publication.
    generations = [int(path.name.split('.', 1)[0]) for path in metadata.glob('*.targets.json')
                   if path.name.split('.', 1)[0].isdigit()]
    version = max([old.signed.version if old else 0, *generations]) + 1
    targets = plan['targets']
    catalog_bytes = json.dumps(catalog, sort_keys=True, indent=2).encode('utf-8') + b'\n'
    catalog_info = TargetFile.from_data('catalog.json', catalog_bytes, ['sha256'])
    catalog_path = repo / 'targets' / (catalog_info.hashes['sha256'] + '.catalog.json')
    _file_destination(catalog_path, catalog_bytes, immutable=True)
    targets['catalog.json'] = catalog_info
    target_meta = Metadata(Targets(version=version, expires=_expiry(30), targets=targets))
    target_meta.sign(_current_key(repo, keys, 'targets'))
    target_bytes = target_meta.to_bytes()
    snapshot = Metadata(Snapshot(version=version, expires=_expiry(7),
                                  meta={'targets.json': MetaFile.from_data(version, target_bytes, ['sha256'])}))
    snapshot.sign(_current_key(repo, keys, 'snapshot'))
    snapshot_bytes = snapshot.to_bytes()
    timestamp = Metadata(Timestamp(version=version, expires=_expiry(1),
                                    snapshot_meta=MetaFile.from_data(version, snapshot_bytes, ['sha256'])))
    timestamp.sign(_current_key(repo, keys, 'timestamp'))
    for role, data in (('targets', target_bytes), ('snapshot', snapshot_bytes)):
        _file_destination(metadata / f'{version}.{role}.json', data, immutable=True)
        _file_destination(metadata / f'{role}.json')
    _file_destination(metadata / 'timestamp.json')
    # All identities, prices, inputs, destinations and signers are now valid.
    # Reservation comes first: a crash can reserve but never reassign a release.
    _atomic(plan['history_path'], plan['history'])
    for destination, data in plan['writes']:
        _atomic(destination, data, immutable=True)
    _atomic(catalog_path, catalog_bytes, immutable=True)
    if plan['registry_path']:
        # Withdrawals reach the private service before the new public timestamp.
        # A crash may deny a download temporarily; it cannot publish paid bytes.
        _atomic(plan['registry_path'], plan['registry'])
    for role, data in (('targets', target_bytes), ('snapshot', snapshot_bytes)):
        _atomic(metadata / f'{version}.{role}.json', data, immutable=True)
        _atomic(metadata / f'{role}.json', data)
    _atomic(metadata / 'timestamp.json', timestamp.to_bytes())
    return version


def _rotate(repo, keys, role):
    """Online-role rotation is authorized by both offline root keys."""
    if role not in ('targets', 'snapshot', 'timestamp'):
        raise ValueError('This command rotates an online role; root recovery uses the documented offline ceremony.')
    repo, keys = _locations(repo, keys)
    root = Metadata.from_file(str(repo / 'metadata' / 'root.json'))
    generation = root.signed.version + 1
    name = f'{role}-{generation}-{uuid4().hex}'
    signer = _new_key(keys, name)
    for keyid in list(root.signed.roles[role].keyids):
        root.signed.revoke_key(keyid, role)
    root.signed.add_key(signer.public_key, role)
    root.signed.version = generation
    root.signed.expires = _expiry(365)
    root.sign(_key(keys, 'root-a'))
    root.sign(_key(keys, 'root-b'), append=True)
    _atomic(repo / 'metadata' / f'{generation}.root.json', root.to_bytes(), immutable=True)
    _atomic(repo / 'metadata' / 'root.json', root.to_bytes())
    # Keep versioned private keys in place. The current root selects the signer;
    # key file renames cannot interrupt publication or lose the active signer.
    return generation


def _locked(operation, repo, keys, *args):
    repo, keys = _locations(repo, keys)
    # Keep the advisory lock alongside the private key folder, outside the
    # public tree, so initialization still observes an empty key directory.
    keys.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(keys.parent / ('.' + keys.name + '.publisher.lock')), timeout=30):
        prepared = _prepare(repo, keys, *args) if operation is _publish else None
        metadata = repo / 'metadata'
        roots = [p for p in metadata.glob('*.root.json') if p.name.split('.', 1)[0].isdigit()]
        if roots:
            latest = max(roots, key=lambda p: int(p.name.split('.', 1)[0]))
            # A versioned root is the publication point. Recover the unversioned
            # alias after a crash before using it to choose online signers.
            alias = metadata / 'root.json'
            if operation is not _publish or not alias.exists() or alias.read_bytes() != latest.read_bytes():
                _atomic(alias, latest.read_bytes())
        if operation is _publish:
            return operation(repo, keys, *args, prepared=prepared)
        return operation(repo, keys, *args)


def initialize(repo, keys):
    return _locked(_initialize, repo, keys)


def publish(repo, keys, catalog, artifacts, *, private_artifacts=None):
    return _locked(_publish, repo, keys, catalog, artifacts, private_artifacts)


def rotate(repo, keys, role):
    return _locked(_rotate, repo, keys, role)


class OperatorParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, json.dumps({'error': 'invalid_arguments'}) + '\n')


def main():
    parser = OperatorParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--keys', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    command = sub.add_parser('publish')
    command.add_argument('--catalog', type=Path, required=True)
    command.add_argument('--artifact', action='append', default=[], metavar='TARGET=FILE')
    command.add_argument('--private-artifacts', type=Path)
    command = sub.add_parser('rotate')
    command.add_argument('role', choices=['targets', 'snapshot', 'timestamp'])
    args = parser.parse_args()
    try:
        if args.command == 'init':
            initialize(args.repo, args.keys)
        elif args.command == 'rotate':
            rotate(args.repo, args.keys, args.role)
        else:
            artifacts = {}
            for value in args.artifact:
                name, path = value.split('=', 1)
                if name in artifacts:
                    raise ValueError('Duplicate package target.')
                artifacts[name] = Path(path).read_bytes()
            publish(args.repo, args.keys, json.loads(args.catalog.read_text(encoding='utf-8')), artifacts,
                    private_artifacts=args.private_artifacts)
    except Exception as exc:
        code = 'invalid_inputs' if isinstance(exc, (ValueError, TypeError, KeyError)) else 'operation_failed'
        parser.exit(1, json.dumps({'error': code}) + '\n')
    print(json.dumps({'status': 'completed', 'operation': args.command}))


if __name__ == '__main__':
    main()
