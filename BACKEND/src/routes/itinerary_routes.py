import logging

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from src.auth import es_el_mismo_usuario, prohibido, requiere_usuario
from src.models.init import db
from src.models.itinerary import Itinerario
from src.models.trip import Viaje
from src.services.itinerary_service import (
    actualizar_itinerario,
    crear_itinerario,
    eliminar_itinerario,
    obtener_itinerario_por_id,
    obtener_itinerarios_por_viaje,
)

logger = logging.getLogger(__name__)

itinerary_bp = Blueprint('itinerary_bp', __name__)


def _dueno_del_viaje(id_viaje):
    viaje = db.session.get(Viaje, id_viaje)
    return viaje.id_usuario if viaje else None


def _dueno_del_itinerario(id_itinerario):
    itinerario = db.session.get(Itinerario, id_itinerario)
    if itinerario is None:
        return None
    return _dueno_del_viaje(itinerario.id_viaje)


def _serializar(it):
    return {
        "id_itinerario": it.id_itinerario,
        "id_viaje": it.id_viaje,
        "dia": it.dia,
        "resumen": it.resumen,
    }


@itinerary_bp.route('/', methods=['POST'])
@requiere_usuario
def alta_itinerario():
    datos = request.get_json()

    if not datos or 'id_viaje' not in datos:
        return jsonify({"error": "No se enviaron datos suficientes para crear el itinerario"}), 400

    dueno = _dueno_del_viaje(datos['id_viaje'])
    if dueno is None:
        return jsonify({"error": "Viaje no encontrado"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    try:
        nuevo_itinerario = crear_itinerario(datos)
        return jsonify({
            "mensaje": "Itinerario creado con éxito",
            "id": nuevo_itinerario.id_itinerario,
        }), 201
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        logger.exception("Error creando itinerario")
        return jsonify({"error": str(e)}), 500


@itinerary_bp.route('/viaje/<int:id_viaje>', methods=['GET'])
@requiere_usuario
def get_itinerarios_viaje(id_viaje):
    dueno = _dueno_del_viaje(id_viaje)
    if dueno is None:
        return jsonify({"error": "Viaje no encontrado"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    itinerarios = obtener_itinerarios_por_viaje(id_viaje)
    return jsonify([_serializar(it) for it in itinerarios]), 200


@itinerary_bp.route('/<int:id_itinerario>', methods=['GET'])
@requiere_usuario
def get_itinerario(id_itinerario):
    itinerario = obtener_itinerario_por_id(id_itinerario)
    if not itinerario:
        return jsonify({"error": "Itinerario no encontrado"}), 404
    if not es_el_mismo_usuario(_dueno_del_viaje(itinerario.id_viaje)):
        return prohibido()

    return jsonify(_serializar(itinerario)), 200


@itinerary_bp.route('/<int:id_itinerario>', methods=['PUT', 'PATCH'])
@requiere_usuario
def modificar_itinerario(id_itinerario):
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos para actualizar"}), 400

    dueno = _dueno_del_itinerario(id_itinerario)
    if dueno is None:
        return jsonify({"error": "Itinerario no encontrado"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    try:
        itinerario_actualizado = actualizar_itinerario(id_itinerario, datos)
        return jsonify({
            "mensaje": f"Itinerario con ID {id_itinerario} actualizado con éxito",
            "id": itinerario_actualizado.id_itinerario,
        }), 200
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        logger.exception("Error actualizando itinerario %s", id_itinerario)
        return jsonify({"error": f"Ocurrió un error interno: {e}"}), 500


@itinerary_bp.route('/<int:id_itinerario>', methods=['DELETE'])
@requiere_usuario
def baja_itinerario(id_itinerario):
    dueno = _dueno_del_itinerario(id_itinerario)
    if dueno is None:
        return jsonify({"error": "Itinerario no encontrado"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    if eliminar_itinerario(id_itinerario):
        return jsonify({"mensaje": "Itinerario eliminado"}), 200
    return jsonify({"error": "Itinerario no encontrado"}), 404
