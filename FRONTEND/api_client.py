"""Cliente HTTP del backend.

Centraliza la URL base, la API key compartida y el `X-User-Id` del usuario
logueado, para que las vistas no tengan que repetir esa plomería ni tragarse
los errores de conexión con `except: pass`.
"""

import logging
import os

import requests
from flask import session

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000").rstrip("/")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")
TIMEOUT = float(os.getenv("BACKEND_TIMEOUT", "15"))


class BackendError(Exception):
    """Error devuelto por el backend o de conexión contra él."""

    def __init__(self, mensaje, status=None, payload=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.payload = payload or {}


def _cabeceras(con_usuario=True):
    cabeceras = {"X-API-KEY": BACKEND_API_KEY}
    if con_usuario and session.get("user_id"):
        cabeceras["X-User-Id"] = str(session["user_id"])
    return cabeceras


def _mensaje_de_error(respuesta):
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return respuesta.text[:200] or f"Error {respuesta.status_code}", {}

    if isinstance(cuerpo, dict):
        # Un 401 por API key mal configurada se parece a un 401 por contraseña
        # incorrecta. El backend los distingue con `codigo`, así el usuario ve
        # el problema real en vez de "credenciales inválidas".
        codigo = cuerpo.get("codigo")
        if codigo in ("api_key_invalida", "api_key_no_configurada"):
            return (
                "Problema de configuración del servidor: la clave compartida "
                "entre el frontend y el backend no coincide. Corré "
                "'python setup.py' desde la raíz del proyecto y reiniciá los dos.",
                cuerpo,
            )

        if "error" in cuerpo:
            return cuerpo["error"], cuerpo
        if "errores_validacion" in cuerpo:
            errores = cuerpo["errores_validacion"]
            if isinstance(errores, dict):
                planos = [m for lista in errores.values()
                          for m in (lista if isinstance(lista, list) else [lista])]
            else:
                planos = errores if isinstance(errores, list) else [str(errores)]
            return " ".join(str(m) for m in planos), cuerpo
        if "errores" in cuerpo:
            return " ".join(str(m) for m in cuerpo["errores"]), cuerpo

    return f"Error {respuesta.status_code}", cuerpo if isinstance(cuerpo, dict) else {}


def request(metodo, ruta, *, json=None, params=None, con_usuario=True, timeout=None):
    """Hace una petición al backend. Lanza BackendError si no sale bien."""
    url = f"{BACKEND_URL}{ruta}"

    try:
        respuesta = requests.request(
            metodo,
            url,
            json=json,
            params=params,
            headers=_cabeceras(con_usuario),
            timeout=timeout or TIMEOUT,
        )
    except requests.exceptions.Timeout as exc:
        logger.error("Timeout llamando a %s %s", metodo, url)
        raise BackendError("El servidor tardó demasiado en responder.") from exc
    except requests.exceptions.RequestException as exc:
        logger.error("No se pudo conectar con el backend (%s %s): %s", metodo, url, exc)
        raise BackendError("No se pudo conectar con el servidor.") from exc

    if respuesta.status_code >= 400:
        mensaje, payload = _mensaje_de_error(respuesta)
        logger.warning("%s %s → %s: %s", metodo, url, respuesta.status_code, mensaje)
        raise BackendError(mensaje, status=respuesta.status_code, payload=payload)

    if respuesta.status_code == 204 or not respuesta.content:
        return None

    try:
        return respuesta.json()
    except ValueError:
        return respuesta.text


def get(ruta, **kwargs):
    return request("GET", ruta, **kwargs)


def post(ruta, **kwargs):
    return request("POST", ruta, **kwargs)


def put(ruta, **kwargs):
    return request("PUT", ruta, **kwargs)


def delete(ruta, **kwargs):
    return request("DELETE", ruta, **kwargs)


def get_o_defecto(ruta, defecto=None, **kwargs):
    """GET que devuelve un valor por defecto en vez de reventar la vista."""
    try:
        return get(ruta, **kwargs)
    except BackendError as exc:
        logger.info("GET %s falló (%s), se usa el valor por defecto", ruta, exc.mensaje)
        return defecto
