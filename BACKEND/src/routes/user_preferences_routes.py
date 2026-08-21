import logging

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from src.auth import es_el_mismo_usuario, prohibido, requiere_usuario
from src.models.init import db
from src.models.user_preferences import PreferenciasUsuario
from src.services.user_preferences_service import (
    actualizar_preferencia,
    crear_preferencia,
    eliminar_preferencia,
    obtener_preferencias_por_usuario,
)
from src.validators.user_preferences_validator import user_preferences_schema

logger = logging.getLogger(__name__)

user_preferences_bp = Blueprint('user_preferences_bp', __name__)


def _dueno_de_preferencia(id_preferencia):
    preferencia = db.session.get(PreferenciasUsuario, id_preferencia)
    return preferencia.id_usuario if preferencia else None


@user_preferences_bp.route('/usuario/<int:id_usuario>', methods=['GET'])
@requiere_usuario
def get_preferencias_usuario(id_usuario):
    if not es_el_mismo_usuario(id_usuario):
        return prohibido()

    preferencias = obtener_preferencias_por_usuario(id_usuario)
    return jsonify(user_preferences_schema.dump(preferencias, many=True)), 200


@user_preferences_bp.route('/', methods=['POST'])
@requiere_usuario
def alta_preferencia():
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos para crear las preferencias"}), 400

    if not es_el_mismo_usuario(datos.get('id_usuario', -1)):
        return prohibido()

    try:
        nueva_preferencia = crear_preferencia(datos)
        return jsonify({
            "mensaje": "Preferencias creadas con éxito",
            "id": nueva_preferencia.id_preferencia,
        }), 201
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        logger.exception("Error creando preferencias")
        return jsonify({"error": str(e)}), 400


@user_preferences_bp.route('/<int:id_preferencia>', methods=['DELETE'])
@requiere_usuario
def baja_preferencia(id_preferencia):
    dueno = _dueno_de_preferencia(id_preferencia)
    if dueno is None:
        return jsonify({"error": "Preferencias no encontradas"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    if eliminar_preferencia(id_preferencia):
        return jsonify({"mensaje": "Preferencias eliminadas exitosamente"}), 200
    return jsonify({"error": "Preferencias no encontradas"}), 404


@user_preferences_bp.route('/<int:id_preferencia>', methods=['PUT', 'PATCH'])
@requiere_usuario
def modificar_preferencia(id_preferencia):
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos para actualizar"}), 400

    dueno = _dueno_de_preferencia(id_preferencia)
    if dueno is None:
        return jsonify({"error": "Preferencias no encontradas"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    datos.pop('id_usuario', None)

    try:
        pref_actualizada = actualizar_preferencia(id_preferencia, datos)
        return jsonify({
            "mensaje": f"Preferencias con ID {id_preferencia} actualizadas con éxito",
            "id": pref_actualizada.id_preferencia,
        }), 200
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        logger.exception("Error actualizando preferencias %s", id_preferencia)
        return jsonify({"error": f"Ocurrió un error interno: {e}"}), 500
