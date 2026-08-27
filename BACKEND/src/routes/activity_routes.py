import logging

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from src.auth import es_el_mismo_usuario, prohibido, requiere_usuario
from src.models.init import db
from src.models.activity import Actividad
from src.models.itinerary import Itinerario
from src.models.trip import Viaje
from src.services.cost_service import get_cost_by_trip
from src.services.activity_service import (
    actualizar_actividad,
    crear_actividad,
    eliminar_actividad,
    obtener_actividad_por_id,
    obtener_actividades_por_itinerario,
)

logger = logging.getLogger(__name__)

activity_bp = Blueprint('activity_bp', __name__)


def _dueno_del_itinerario(id_itinerario):
    itinerario = db.session.get(Itinerario, id_itinerario)
    if itinerario is None:
        return None
    viaje = db.session.get(Viaje, itinerario.id_viaje)
    return viaje.id_usuario if viaje else None


def _dueno_de_actividad(id_actividad):
    actividad = db.session.get(Actividad, id_actividad)
    if actividad is None:
        return None
    return _dueno_del_itinerario(actividad.id_itinerario)


def _id_viaje_de_itinerario(id_itinerario):
    itinerario = db.session.get(Itinerario, id_itinerario)
    return itinerario.id_viaje if itinerario else None


def _id_viaje_de_actividad(id_actividad):
    actividad = db.session.get(Actividad, id_actividad)
    if actividad is None:
        return None
    return _id_viaje_de_itinerario(actividad.id_itinerario)


def _costos_del_viaje(id_viaje):
    """Costos del viaje después de tocar una actividad.

    Se devuelven en la misma respuesta para que el cliente pueda refrescar el
    presupuesto sin tener que volver a pedir el viaje entero.
    """
    if id_viaje is None:
        return None
    return get_cost_by_trip(id_viaje)


def _serializar(a):
    return {
        "id_actividad": a.id_actividad,
        "id_itinerario": a.id_itinerario,
        "nombre": a.nombre,
        "descripcion": a.descripcion,
        "precio_estimado": a.precio_estimado,
        "categoria": a.categoria,
        "horario_sugerido": a.horario_sugerido,
        "ubicacion": a.ubicacion,
    }


@activity_bp.route('/', methods=['POST'])
@requiere_usuario
def alta_actividad():
    datos = request.get_json()
    if not datos or 'id_itinerario' not in datos:
        return jsonify({"error": "No se enviaron datos para crear la actividad"}), 400

    dueno = _dueno_del_itinerario(datos['id_itinerario'])
    if dueno is None:
        return jsonify({"error": "Itinerario no encontrado"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    try:
        nueva_actividad = crear_actividad(datos)
        return jsonify({
            "mensaje": "Actividad creada",
            "id": nueva_actividad.id_actividad,
            "costos": _costos_del_viaje(_id_viaje_de_itinerario(datos['id_itinerario'])),
        }), 201
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        logger.exception("Error creando actividad")
        return jsonify({"error": str(e)}), 500


@activity_bp.route('/itinerario/<int:id_itinerario>', methods=['GET'])
@requiere_usuario
def get_actividades_itinerario(id_itinerario):
    dueno = _dueno_del_itinerario(id_itinerario)
    if dueno is None:
        return jsonify({"error": "Itinerario no encontrado"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    actividades = obtener_actividades_por_itinerario(id_itinerario)
    return jsonify([_serializar(a) for a in actividades]), 200


@activity_bp.route('/<int:id_actividad>', methods=['GET'])
@requiere_usuario
def get_actividad(id_actividad):
    dueno = _dueno_de_actividad(id_actividad)
    if dueno is None:
        return jsonify({"error": "Actividad no encontrada"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    return jsonify(_serializar(obtener_actividad_por_id(id_actividad))), 200


@activity_bp.route('/<int:id_actividad>', methods=['PUT', 'PATCH'])
@requiere_usuario
def modificar_actividad(id_actividad):
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos"}), 400

    dueno = _dueno_de_actividad(id_actividad)
    if dueno is None:
        return jsonify({"error": "Actividad no encontrada"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    datos.pop('id_itinerario', None)

    try:
        id_viaje = _id_viaje_de_actividad(id_actividad)
        actividad_actualizada = actualizar_actividad(id_actividad, datos)
        return jsonify({
            "mensaje": "Actividad actualizada",
            "id": actividad_actualizada.id_actividad,
            "costos": _costos_del_viaje(id_viaje),
        }), 200
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        logger.exception("Error actualizando actividad %s", id_actividad)
        return jsonify({"error": str(e)}), 500


@activity_bp.route('/<int:id_actividad>', methods=['DELETE'])
@requiere_usuario
def baja_actividad(id_actividad):
    dueno = _dueno_de_actividad(id_actividad)
    if dueno is None:
        return jsonify({"error": "Actividad no encontrada"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    id_viaje = _id_viaje_de_actividad(id_actividad)
    if eliminar_actividad(id_actividad):
        return jsonify({
            "mensaje": "Actividad eliminada",
            "costos": _costos_del_viaje(id_viaje),
        }), 200
    return jsonify({"error": "Actividad no encontrada"}), 404
