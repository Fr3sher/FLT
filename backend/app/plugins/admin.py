"""Installing code requires local administration or a separate operator token."""
import hmac
import ipaddress
import os
from urllib.parse import urlsplit

from flask import jsonify, request


def _loopback(value):
    try:
        return ipaddress.ip_address(value).is_loopback
    except (ValueError, TypeError):
        return value == 'localhost'


def is_admin():
    expected = os.environ.get('LDS_PLUGIN_ADMIN_TOKEN', '')
    supplied = request.headers.get('X-LDS-Plugin-Admin', '')
    if expected:
        return len(expected) >= 32 and hmac.compare_digest(expected.encode('utf-8'), supplied.encode('utf-8'))
    # Ignore forwarded addresses as credentials. Remote/proxied administration
    # must explicitly enable a distinct token; the shared app access token is
    # not a store administrator credential.
    if any(name in request.headers for name in ('Forwarded', 'X-Forwarded-For', 'X-Real-IP')):
        return False
    try:
        if not _loopback(request.remote_addr) or not _loopback(urlsplit('http://' + request.host).hostname):
            return False
        origin = request.headers.get('Origin')
        if not origin:
            return True
        parsed = urlsplit(origin)
        return (parsed.scheme in ('http', 'https') and not parsed.username and not parsed.password
                and not parsed.path and not parsed.query and not parsed.fragment and _loopback(parsed.hostname))
    except ValueError:
        return False


def require_admin():
    if not is_admin():
        return jsonify({'error': 'Plugin changes require local administration or the operator’s plugin admin token.',
                        'code': 'plugin_admin_required'}), 403
    return None
