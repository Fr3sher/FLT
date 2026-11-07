"""Bounded public host adapters. Trusted Python extensions are not sandboxed."""
from app.plugins.api import LDS_PLUGIN_API_MAJOR as API_MAJOR, LDS_PLUGIN_API_MINOR as API_MINOR
VERSION = f'{API_MAJOR}.{API_MINOR}'
__all__ = ['VERSION', 'API_MAJOR', 'API_MINOR']
