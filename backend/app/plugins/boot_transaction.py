"""Boot-only package transaction, bounded by an actual SQLite write transaction.

The journal coordinates files with a marker committed with plugin SQL. Recovery
never restores a database snapshot: other writers retain their own commits.
Python imports are irreversible, so a failed trial boot exits before serving.
"""
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import scoped_session, sessionmaker

from ..extensions import db
from . import storage, transactions as txs

_MARKER = 'lds_plugin_transaction_commits'
_SCHEMAS = 'lds_plugin_data_schemas'


class BootTransaction:
    def __init__(self, app, root, transaction, connection):
        self.app, self.root, self.transaction, self.connection = app, root, transaction, connection
        self.confirmed = False

    def apply(self):
        txs.snapshot(self.root, self.transaction)
        self.transaction['phase'] = 'applying'
        txs._save(self.root, self.transaction)
        txs.publish(self.root, self.transaction)
        self.transaction['phase'] = 'awaiting_health'
        txs._save(self.root, self.transaction)

    def confirm_health(self, registry):
        changed = {item['id'] for item in self.transaction['items']}
        affected = set(changed)
        while True:
            previous = set(affected)
            affected.update(record.id for record in registry.records.values()
                            if set(record.manifest.requires) & affected)
            if affected == previous:
                break
        for item in self.transaction['items']:
            record = registry.records.get(item['id'])
            if item['action'] == 'remove':
                if record is not None:
                    raise storage.StorageError('A removed plugin was still discovered during its trial boot.')
            elif record is None or (item['desired_enabled'] and record.state != 'loaded'):
                raise storage.StorageError('An installed plugin failed its trial boot.')
            elif record.manifest.contract.get('schema_version', 1) >= 2:
                assets = [record.manifest.frontend, *record.manifest.contract.get('frontend_styles', [])]
                if any(asset and not storage.managed_path(storage.Path(record.dir), *asset.split('/')).is_file()
                       for asset in assets):
                    raise storage.StorageError('The installed plugin is missing a declared screen or stylesheet.')
        for pid in affected - changed:
            record = registry.records[pid]
            if record.enabled and record.state != 'loaded':
                raise storage.StorageError('The changed plugin broke a dependent plugin during its trial boot.')
        self._migrate(registry)
        for pid in affected:
            record = registry.records.get(pid)
            if record is None or record.state != 'loaded':
                continue
            for check in self.app.extensions.get('lds_plugin_health_checks', {}).get(pid, {}).values():
                if check() is not True:
                    raise storage.StorageError('A plugin failed its local trial-boot health check.')
        db.session.flush()
        self.connection.execute(text(f'CREATE TABLE IF NOT EXISTS {_MARKER} (id TEXT PRIMARY KEY NOT NULL)'))
        self.connection.execute(text(f'INSERT INTO {_MARKER} (id) VALUES (:id)'), {'id': self.transaction['id']})
        self.confirmed = True

    def _migrate(self, registry):
        self.connection.execute(text(f'CREATE TABLE IF NOT EXISTS {_SCHEMAS} '
                                     '(plugin_id TEXT PRIMARY KEY NOT NULL, schema_version INTEGER NOT NULL)'))
        plans = []
        for item in self.transaction['items']:
            pid = item['id']
            saved = self.connection.execute(text(f'SELECT schema_version FROM {_SCHEMAS} WHERE plugin_id=:id'), {'id': pid}).scalar()
            old = saved if saved is not None else item.get('before_schema', 1 if item.get('had_data') else 0)
            if item['action'] == 'remove':
                target, steps = old, {}
            else:
                record = registry.records[pid]
                target = record.manifest.contract.get('data_schema', 1)
                if old > target:
                    raise storage.StorageError('The retained plugin data uses a newer schema than this package.')
                steps = self.app.extensions.get('lds_plugin_migrations', {}).get(pid, {})
                if old and old != target:
                    if record.state != 'loaded' or any(version not in steps for version in range(old, target)):
                        raise storage.StorageError('The plugin does not provide the complete data migration path.')
            plans.append((pid, old, target, steps))
        for pid, old, target, steps in plans:
            for version in range(old or target, target):
                steps[version]()
            if target:
                self.connection.execute(text(f'INSERT INTO {_SCHEMAS} (plugin_id, schema_version) VALUES (:id, :schema) '
                                              'ON CONFLICT(plugin_id) DO UPDATE SET schema_version=excluded.schema_version'),
                                        {'id': pid, 'schema': target})


def _committed(connection, txid):
    exists = connection.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (_MARKER,)).first()
    return bool(exists and connection.execute(text(f'SELECT 1 FROM {_MARKER} WHERE id=:id'), {'id': txid}).first())


@contextmanager
def boot_transaction(app, root):
    """Apply before discovery and commit only after the loader's health check."""
    with txs.admission(root):
        transaction = txs.active(root)
        if transaction is None:
            yield None
            return
        if transaction['phase'] == 'preparing':
            transaction['phase'] = 'rolled_back'
            txs._save(root, transaction)
            yield None
            return
        with app.app_context():
            engines = db._app_engines[app]
            if set(engines) != {None} or engines[None].dialect.name != 'sqlite':
                raise storage.StorageError('Plugin transactions require the supported single SQLite database.')
            db.session.remove()
            original_session = db.session
            with engines[None].connect() as connection:
                # Explicit BEGIN prevents SQLite legacy transaction mode from
                # autocommitting DDL or the first released SAVEPOINT.
                connection.exec_driver_sql('BEGIN IMMEDIATE')
                if _committed(connection, transaction['id']):
                    transaction['phase'] = 'committed'
                    txs._save(root, transaction)
                    connection.rollback()
                    yield None
                    return
                if transaction['phase'] != 'prepared':
                    txs.rollback(root, transaction)
                    connection.rollback()
                    raise txs.PluginBootRollback('The interrupted plugin change was rolled back. Restarting with its previous packages.')
                session = scoped_session(sessionmaker(bind=connection, join_transaction_mode='create_savepoint'))
                db.session = session
                db._app_engines[app] = {None: connection}
                boot = BootTransaction(app, root, transaction, connection)
                app.extensions['lds_plugin_boot_transaction'] = boot
                committed = False
                try:
                    yield boot
                    if not boot.confirmed:
                        raise storage.StorageError('Plugin startup did not confirm the complete installation plan.')
                    session.commit()  # RELEASE SAVEPOINT only; outer BEGIN still owns SQL.
                    connection.commit()
                    committed = True
                    transaction['phase'] = 'committed'
                    txs._save(root, transaction)
                except BaseException as exc:
                    # An interrupted final journal write is resolved by the DB
                    # marker on the next boot; never undo files after DB commit.
                    if not committed:
                        transaction['reason'] = 'The trial boot or migration failed; the previous packages and data were restored.'
                        session.rollback()
                        txs.rollback(root, transaction)
                        connection.rollback()
                    raise txs.PluginBootRollback('The plugin trial boot failed. Restart LDS to finish recovery safely.') from exc
                finally:
                    session.remove()
                    db.session = original_session
                    db._app_engines[app] = engines
                    app.extensions.pop('lds_plugin_boot_transaction', None)
