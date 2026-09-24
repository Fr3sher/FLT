"""SQLAlchemy mapping for tables owned by one plugin, using the host transaction.

The facade never returns the host database/session or host ORM models. Mapped
classes live in the plugin; a shared Session is resolved at each operation so
installation savepoints and normal request transactions retain their meaning.
This is an API ownership boundary, not a Python sandbox.
"""


import re

from sqlalchemy import func, or_

from sqlalchemy.sql import visitors


from sqlalchemy.sql.elements import TextClause


from sqlalchemy.sql.schema import Table


_HISTORICAL_OWNERS = {
    'canvas': frozenset({'canvas_node_position', 'canvas_image_node',
                         'canvas_lane_placement', 'canvas_layout_preset'}),
    'civitai_publish': frozenset({'civitai_link', 'video_civitai_link'}),
    'cloud_training': frozenset({'cloud_training_run'}),
    'creature_battle': frozenset({'creature_battle_run', 'plugin_video__creature_image'}),
    'video': frozenset({'video_bank', 'video_source', 'video_clip', 'video_dataset',
                        'video_dataset_clip', 'video_test_clip', 'video_checkpoint_preview'}),
}


class _OwnedSession:
    def __init__(self, owner):
        self._owner = owner

    def _model(self, model):
        if not isinstance(model, type) or not issubclass(model, self._owner.BaseMapped):
            raise ValueError('This mapped model does not belong to the plugin.')

    @staticmethod
    def _current():
        from app.extensions import db
        return db.session

    def get(self, model, identity, **kwargs):
        self._model(model)
        return self._current().get(model, identity, **kwargs)

    def add(self, row):
        self._model(type(row))
        self._current().add(row)

    def add_all(self, rows):
        rows = list(rows)
        for row in rows:
            self._model(type(row))
        self._current().add_all(rows)

    def delete(self, row):
        self._model(type(row))
        self._current().delete(row)

    def commit(self):
        self._current().commit()

    def flush(self):
        self._current().flush()

    def rollback(self):
        self._current().rollback()

    def refresh(self, row, **kwargs):
        self._model(type(row))
        self._current().refresh(row, **kwargs)

    def _expression(self, value):
        if isinstance(value, type):
            self._model(value)
            value = value.__table__
        if hasattr(value, '__clause_element__'):
            value = value.__clause_element__()
        for node in visitors.iterate(value):
            if isinstance(node, TextClause):
                raise ValueError('Raw SQL is not part of the plugin database API.')
            table = node if isinstance(node, Table) else getattr(node, 'table', None)
            if table is not None and isinstance(table, Table):
                # ORM queries annotate the same Table without changing its identity.
                actual = table._deannotate()
                if table.name not in self._owner.tables or actual is not self._owner.table(table.name):
                    raise ValueError('This table does not belong to the plugin.')

    def query(self, *entities):
        for entity in entities:
            self._expression(entity)
        return _OwnedQuery(self, self._current().query(*entities))

    def execute(self, statement, parameters=None):
        self._expression(statement)
        if parameters is None:
            return self._current().execute(statement)
        return self._current().execute(statement, parameters)

    def remove(self):
        """End this thread's host session at worker teardown, never open another."""
        self._current().remove()


class _OwnedQuery:
    def __init__(self, session, query):
        self._session, self._query = session, query

    def _chain(self, operation, *args, **kwargs):
        query = getattr(self._query, operation)(*args, **kwargs)
        self._session._expression(query.statement)
        return _OwnedQuery(self._session, query)

    def filter(self, *criteria):
        return self._chain('filter', *criteria)

    def filter_by(self, **fields):
        return self._chain('filter_by', **fields)

    def order_by(self, *criteria):
        return self._chain('order_by', *criteria)

    def join(self, *args, **kwargs):
        return self._chain('join', *args, **kwargs)

    def select_from(self, *entities):
        return self._chain('select_from', *entities)

    def group_by(self, *criteria):
        return self._chain('group_by', *criteria)

    def distinct(self, *criteria):
        return self._chain('distinct', *criteria)

    def limit(self, count):
        return self._chain('limit', count)

    def offset(self, count):
        return self._chain('offset', count)

    def all(self):
        return self._query.all()

    def first(self):
        return self._query.first()

    def scalar(self):
        return self._query.scalar()

    def count(self):
        return self._query.count()

    def __iter__(self):
        return iter(self._query)


class _PluginDatabase:
    def __init__(self, plugin_id, tables):
        from app.extensions import db
        self.id, self.tables = plugin_id, frozenset(tables)
        owner = self

        class BaseMapped(db.Model):
            __abstract__ = True

            def __init_subclass__(cls, **kwargs):
                table = cls.__dict__.get('__table__')
                name = table.name if table is not None else cls.__dict__.get('__tablename__')
                if not cls.__dict__.get('__abstract__', False) and name not in owner.tables:
                    raise ValueError('This table does not belong to the plugin.')
                super().__init_subclass__(**kwargs)

        self.BaseMapped = BaseMapped
        self.session = _OwnedSession(self)
        # Expression constructors do not open a session. Every query still
        # validates its complete statement against this owner's mapped tables.
        self.func = func
        self.or_ = or_

    def table(self, name):
        if name not in self.tables:
            raise ValueError('This table does not belong to the plugin.')
        from app.extensions import db
        if name == 'creature_battle_run' and name not in db.metadata.tables:
            from ._schema_extend import persistent_table
            persistent_table(name,
                db.Column('id', db.Integer, primary_key=True),
                db.Column('user_id', db.String(36), nullable=False, index=True),
                db.Column('run_id', db.String(64), nullable=False, unique=True))
        return db.metadata.tables[name]


def for_plugin(plugin_id, *, tables):
    """Declare a plugin mapping boundary, without opening a database connection.

    New tables use ``plugin_<publisher>_<name>__<table>``. The shipped products
    retain their documented historical table names; this never authorizes an
    archive or grants a publisher identity (the installer does that).
    """
    if not isinstance(plugin_id, str) or not re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*', plugin_id):
        raise ValueError('Invalid plugin id.')
    names = frozenset(tables)
    prefix = 'plugin_' + plugin_id.replace('.', '_') + '__'
    historical = _HISTORICAL_OWNERS.get(plugin_id, frozenset())
    if not names or any(not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', name)
                        or (name not in historical and not name.startswith(prefix)) for name in names):
        raise ValueError('This table does not belong to the plugin.')
    return _PluginDatabase(plugin_id, names)


__all__ = ['for_plugin']
