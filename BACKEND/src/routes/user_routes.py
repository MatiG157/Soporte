import logging

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from src.auth import es_el_mismo_usuario, prohibido, requiere_usuario
from src.models.init import db
from src.models.user import Usuario
from src.services.user_service import (
    actualizar_usuario,
    crear_usuario,
    eliminar_usuario,
    obtener_o_crear_usuario_google,
    verificar_login,
)

logger = logging.getLogger(__name__)

user_bp = Blueprint('user_bp', __name__)


def _serializar(usuario):
    return {
        "id_usuario": usuario.id_usuario,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "email": usuario.email,
        "nacionalidad": usuario.nacionalidad,
        "foto": usuario.foto,
        "idioma": usuario.idioma or "en",
        "auth_provider": usuario.auth_provider,
    }


@user_bp.route('/login', methods=['POST'])
def login_usuario():
    datos = request.get_json()
    if not datos or not datos.get('email') or not datos.get('contrasena'):
        return jsonify({"error": "Debe proveer email y contraseña"}), 400

    usuario = verificar_login(datos['email'], datos['contrasena'])
    if usuario:
        return jsonify({"mensaje": "Login exitoso", **_serializar(usuario)}), 200

    # Mensaje genérico a propósito: no revelamos si el email existe.
    return jsonify({"error": "Credenciales inválidas"}), 401


@user_bp.route('/', methods=['POST'])
def alta_usuario():
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos para crear el usuario"}), 400

    if not datos.get('contrasena'):
        return jsonify({
            "errores_validacion": {"contrasena": ["La contraseña es obligatoria."]}
        }), 400

    if Usuario.query.filter_by(email=datos.get('email')).first():
        return jsonify({"error": "Ya existe una cuenta con ese email"}), 409

    try:
        nuevo_user = crear_usuario(datos)
        return jsonify({"mensaje": "Usuario creado con éxito", "id": nuevo_user.id_usuario}), 201
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        logger.exception("Error creando usuario")
        return jsonify({"error": str(e)}), 400


@user_bp.route('/<int:id_usuario>', methods=['GET'])
@requiere_usuario
def get_usuario(id_usuario):
    if not es_el_mismo_usuario(id_usuario):
        return prohibido()

    usuario = db.session.get(Usuario, id_usuario)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado"}), 404
    return jsonify(_serializar(usuario)), 200


@user_bp.route('/<int:id_usuario>', methods=['DELETE'])
@requiere_usuario
def baja_usuario(id_usuario):
    if not es_el_mismo_usuario(id_usuario):
        return prohibido()

    if eliminar_usuario(id_usuario):
        return jsonify({"mensaje": "Usuario eliminado"}), 200
    return jsonify({"error": "Usuario no encontrado"}), 404


@user_bp.route('/<int:id_usuario>', methods=['PUT', 'PATCH'])
@requiere_usuario
def modificar_usuario(id_usuario):
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos para actualizar"}), 400

    if not es_el_mismo_usuario(id_usuario):
        return prohibido()

    # El email nuevo no puede pisar el de otra cuenta.
    nuevo_email = datos.get('email')
    if nuevo_email:
        existente = Usuario.query.filter_by(email=nuevo_email).first()
        if existente and existente.id_usuario != id_usuario:
            return jsonify({"error": "Ya existe una cuenta con ese email"}), 409

    try:
        usuario_actualizado = actualizar_usuario(id_usuario, datos)
        if not usuario_actualizado:
            return jsonify({"error": "Usuario no encontrado"}), 404

        return jsonify({
            "mensaje": f"Usuario con ID {id_usuario} actualizado con éxito",
            **_serializar(usuario_actualizado),
        }), 200
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        logger.exception("Error actualizando usuario %s", id_usuario)
        return jsonify({"error": f"Ocurrió un error interno: {e}"}), 500


@user_bp.route('/google-login', methods=['POST'])
def google_login():
    datos = request.get_json()
    if not datos or 'email' not in datos:
        return jsonify({'error': 'Datos de Google inválidos'}), 400

    try:
        usuario = obtener_o_crear_usuario_google(datos)
        return jsonify({'mensaje': 'Login exitoso', **_serializar(usuario)}), 200
    except Exception as e:
        logger.exception("Error en login con Google")
        return jsonify({'error': str(e)}), 500
