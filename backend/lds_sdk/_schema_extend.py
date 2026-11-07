"""Retain historical host mappings while adding product-owned persistent fields."""
from sqlalchemy import Column
from app.extensions import db


def persistent_table(name, *declarations):
    existing = db.metadata.tables.get(name)
    if existing is None:
        return db.Table(name, *declarations)
    for declaration in declarations:
        if isinstance(declaration, Column) and declaration.name not in existing.c:
            existing.append_column(declaration)
    return existing
