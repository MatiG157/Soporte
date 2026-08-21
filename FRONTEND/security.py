"""Protección CSRF para los formularios y los fetch del frontend.

Se genera un token por sesión. Cada request que modifica estado (POST/PUT/
PATCH/DELETE) tiene que traerlo, sea en el campo oculto `csrf_token` del
formulario o en la cabecera `X-CSRF-Token` cuando se usa fetch.
"""

import logging
import secrets

from flask import abort, request, session

logger = logging.getLogger(__name__)

METODOS_INSEGUROS = {"POST", "PUT", "PATCH", "DELETE"}

# Endpoints que no pueden llevar token porque el request lo origina un tercero.
EXENTOS = {"authorize_google"}


def csrf_token():
    """Token de la sesión actual. Se crea la primera vez que se pide."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


def _token_recibido():
    return (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token")
        or (request.get_json(silent=True) or {}).get("csrf_token")
    )


def verificar_csrf():
    """Se engancha como `before_request`."""
    if request.method not in METODOS_INSEGUROS:
        return
    if request.endpoint in EXENTOS:
        return

    esperado = session.get("_csrf_token")
    recibido = _token_recibido()

    if not esperado or not recibido or not secrets.compare_digest(esperado, recibido):
        logger.warning("CSRF rechazado en %s (endpoint=%s)", request.path, request.endpoint)
        abort(400, description="Token de seguridad inválido o vencido. Recargá la página.")


def registrar(app):
    app.before_request(verificar_csrf)
    app.jinja_env.globals["csrf_token"] = csrf_token
