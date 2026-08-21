"""Catálogo de tipos de alojamiento.

La lectura está disponible para cualquier cliente autenticado con la API key.
La escritura es una operación de administración: exige además `X-ADMIN-KEY`.
"""

import logging
import os
from functools import wraps

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from src.services.accommodation_service import (
    actualizar_tipo_alojamiento,
    crear_tipo_alojamiento,
    eliminar_tipo_alojamiento,
    obtener_tipo_alojamiento_por_id,
    obtener_tipos_alojamiento,
)

logger = logging.getLogger(__name__)

accommodation_types_bp = Blueprint('accommodation_types_bp', __name__)


def requiere_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        esperada = os.getenv("ADMIN_KEY")
        if not esperada:
            return jsonify({"error": "Operación de administración no habilitada"}), 403
        if request.headers.get("X-ADMIN-KEY") != esperada:
            return jsonify({"error": "No tenés permiso para modificar el catálogo"}), 403
        return f(*args, **kwargs)
    return wrapper


@accommodation_types_bp.route('/', methods=['GET'])
def get_tipos_alojamiento():
    tipos = obtener_tipos_alojamiento()
    return jsonify([{"id_tipo": t.id_tipo, "tipo": t.tipo} for t in tipos]), 200


@accommodation_types_bp.route('/<int:id_tipo>', methods=['GET'])
def get_tipo_alojamiento(id_tipo):
    tipo = obtener_tipo_alojamiento_por_id(id_tipo)
    if not tipo:
        return jsonify({"error": "Tipo de alojamiento no encontrado"}), 404
    return jsonify({"id_tipo": tipo.id_tipo, "tipo": tipo.tipo}), 200


@accommodation_types_bp.route('/', methods=['POST'])
@requiere_admin
def alta_tipo_alojamiento():
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos para crear el tipo de alojamiento"}), 400

    try:
        nuevo_tipo = crear_tipo_alojamiento(datos)
        return jsonify({"mensaje": "Tipo de alojamiento creado", "id": nuevo_tipo.id_tipo}), 201
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        logger.exception("Error creando tipo de alojamiento")
        return jsonify({"error": str(e)}), 500


@accommodation_types_bp.route('/<int:id_tipo>', methods=['PUT', 'PATCH'])
@requiere_admin
def modificar_tipo_alojamiento(id_tipo):
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos"}), 400

    try:
        tipo_actualizado = actualizar_tipo_alojamiento(id_tipo, datos)
        if not tipo_actualizado:
            return jsonify({"error": "Tipo de alojamiento no encontrado"}), 404
        return jsonify({
            "mensaje": "Tipo de alojamiento actualizado",
            "id": tipo_actualizado.id_tipo,
        }), 200
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        logger.exception("Error actualizando tipo de alojamiento %s", id_tipo)
        return jsonify({"error": str(e)}), 500


@accommodation_types_bp.route('/<int:id_tipo>', methods=['DELETE'])
@requiere_admin
def baja_tipo_alojamiento(id_tipo):
    if eliminar_tipo_alojamiento(id_tipo):
        return jsonify({"mensaje": "Tipo de alojamiento eliminado"}), 200
    return jsonify({"error": "Tipo de alojamiento no encontrado"}), 404
