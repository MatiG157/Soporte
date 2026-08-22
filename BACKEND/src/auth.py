"""Capa de autenticación del backend.

El backend es un servicio interno: el único cliente legítimo es el frontend Flask.
Por eso toda la API exige una API key compartida (`X-API-KEY`).

Además, para los recursos que pertenecen a un usuario, el frontend envía
`X-User-Id` con el id del usuario logueado en su sesión. Las rutas usan
`usuario_actual_id()` y los helpers de ownership para impedir que un usuario
acceda o modifique datos de otro.
"""

import os
from functools import wraps

from flask import jsonify, request

# Rutas que no exigen API key (health check).
RUTAS_PUBLICAS = {"/", "/health"}


def api_key_esperada():
    return os.getenv("API_KEY")


def verificar_api_key():
    """Se engancha como `before_request`. Devuelve una respuesta si rechaza."""
    if request.method == "OPTIONS":
        return None
    if request.path in RUTAS_PUBLICAS:
        return None

    esperada = api_key_esperada()
    if not esperada:
        return jsonify({
            "codigo": "api_key_no_configurada",
            "error": "El backend no tiene API_KEY configurada en BACKEND/.env. "
                     "Corré 'python setup.py' desde la raíz del proyecto.",
        }), 500

    recibida = request.headers.get("X-API-KEY")
    if not recibida or not _comparar_seguro(recibida, esperada):
        # `codigo` distingue esto de un 401 por credenciales del usuario:
        # sin él, un login fallaba con "credenciales inválidas" cuando en
        # realidad lo que estaba mal era la configuración.
        return jsonify({
            "codigo": "api_key_invalida",
            "error": "La API key del frontend no coincide con la del backend.",
        }), 401

    return None


def _comparar_seguro(a, b):
    """Comparación en tiempo constante para no filtrar la key por timing."""
    if len(a) != len(b):
        return False
    resultado = 0
    for x, y in zip(a, b):
        resultado |= ord(x) ^ ord(y)
    return resultado == 0


def usuario_actual_id():
    """Id del usuario logueado en el frontend, o None."""
    valor = request.headers.get("X-User-Id")
    if not valor:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def requiere_usuario(f):
    """Exige que venga un X-User-Id válido."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if usuario_actual_id() is None:
            return jsonify({"error": "Falta el identificador de usuario"}), 401
        return f(*args, **kwargs)
    return wrapper


def es_el_mismo_usuario(id_usuario):
    return usuario_actual_id() == int(id_usuario)


def prohibido():
    return jsonify({"error": "No tenés permiso sobre este recurso"}), 403
