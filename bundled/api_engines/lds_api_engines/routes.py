"""The ChatGPT subscription lane's routes (Codex device-code OAuth), at the URLs
the Settings and Setup screens already call — registered under ``/api`` by the
plugin's ``register``. One upstream check per poll call — the SPA polls every
few seconds, no server thread."""
from flask import Blueprint, jsonify

from . import chatgpt_oauth

bp = Blueprint('api_engines', __name__)


@bp.post('/settings/chatgpt-oauth/start')
def chatgpt_oauth_start():
    out = chatgpt_oauth.login_start()
    return jsonify(out), (200 if out.get('ok') else 502)


@bp.get('/settings/chatgpt-oauth/poll')
def chatgpt_oauth_poll():
    return jsonify(chatgpt_oauth.login_poll())


@bp.post('/settings/chatgpt-oauth/import-codex')
def chatgpt_oauth_import_codex():
    out = chatgpt_oauth.import_codex_cli()
    return jsonify(out), (200 if out.get('ok') else 404)


@bp.post('/settings/chatgpt-oauth/logout')
def chatgpt_oauth_logout():
    chatgpt_oauth.logout()
    return jsonify({'ok': True})
