import json
import logging

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError
from sqlalchemy.orm import joinedload

from src.auth import es_el_mismo_usuario, prohibido, requiere_usuario, usuario_actual_id
from src.models.init import db
from src.models.itinerary import Itinerario
from src.models.ai_recommendation import RecomendacionIA
from src.models.trip import Viaje
from src.services.cost_service import get_cost_by_trip
from src.services.trip_service import (
    actualizar_viaje,
    confirmar_viaje,
    crear_viaje,
    eliminar_viaje,
    guardar_viajes_generados,
    obtener_drafts_activos,
    obtener_viajes_por_usuario,
)

logger = logging.getLogger(__name__)

trip_bp = Blueprint('trip_bp', __name__)



def _fuente_de_datos(id_viaje):
    """De dónde salió cada precio, según lo que informó el generador.

    Va dentro de la salida cruda que se guarda en `recomendaciones_ia`, así que
    se lee de ahí en vez de duplicarla en una columna propia. Es informativo: si
    no está, o si el JSON quedó viejo, la vista simplemente no muestra el origen.
    """
    recomendacion = (
        RecomendacionIA.query
        .filter_by(id_viaje=id_viaje)
        .order_by(RecomendacionIA.id_recomendacion.desc())
        .first()
    )
    if not recomendacion:
        return None

    try:
        crudo = json.loads(recomendacion.texto_generado)
    except (ValueError, TypeError):
        return None

    fuente = crudo.get("fuente_datos") if isinstance(crudo, dict) else None
    return fuente if isinstance(fuente, dict) else None


def _serializar_resumen(v):
    return {
        "id_viaje": v.id_viaje,
        "destinos": [
            {
                "id_viaje_destino": d.id_viaje_destino,
                "nombre": d.nombre,
                "fecha_llegada": d.fecha_llegada.isoformat() if d.fecha_llegada else None,
                "fecha_partida": d.fecha_partida.isoformat() if d.fecha_partida else None
            } for d in v.viaje_destinos
        ] if hasattr(v, 'viaje_destinos') else [],
        "fecha_inicio": v.fecha_inicio.isoformat(),
        "fecha_fin": v.fecha_fin.isoformat(),
        "tipo_viaje": v.tipo_viaje,
        "titulo": v.titulo,
        "costo_total_estimado": v.costo_total_estimado,
        "estado": v.estado,
        "group_id": v.group_id,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "imagen": v.imagen,
    }


@trip_bp.route('/', methods=['POST'])
@requiere_usuario
def alta_viaje():
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos para crear el viaje"}), 400

    if not es_el_mismo_usuario(datos.get('id_usuario', -1)):
        return prohibido()

    try:
        nuevo_viaje = crear_viaje(datos)
        return jsonify({"mensaje": "Viaje creado", "id": nuevo_viaje.id_viaje}), 201
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        logger.exception("Error creando viaje")
        return jsonify({"error": str(e)}), 500


@trip_bp.route('/usuario/<int:id_usuario>', methods=['GET'])
@requiere_usuario
def get_viajes_usuario(id_usuario):
    if not es_el_mismo_usuario(id_usuario):
        return prohibido()

    viajes = obtener_viajes_por_usuario(id_usuario)
    return jsonify([_serializar_resumen(v) for v in viajes]), 200


@trip_bp.route('/<int:id_viaje>', methods=['GET'])
@requiere_usuario
def get_viaje(id_viaje):
    v = (
        Viaje.query
        .options(
            joinedload(Viaje.viaje_destinos),
            joinedload(Viaje.itinerarios).joinedload(Itinerario.actividades)
        )
        .filter_by(id_viaje=id_viaje)
        .first()
    )

    if not v:
        return jsonify({"error": "Viaje no encontrado"}), 404

    if not es_el_mismo_usuario(v.id_usuario):
        return prohibido()

    respuesta = _serializar_resumen(v)
    respuesta.update({
        "id_usuario": v.id_usuario,
        "id_user_preferences": v.id_user_preferences,
        # Sin tipo explícito: informa el costo tal como quedó guardado,
        # sin volver a aplicarle el multiplicador.
        "costos": get_cost_by_trip(v.id_viaje),
        "fuente_datos": _fuente_de_datos(v.id_viaje),
        "itinerarios": [
            {
                "id_itinerario": iti.id_itinerario,
                "dia": iti.dia,
                "resumen": iti.resumen,
                "actividades": [
                    {
                        "id_actividad": act.id_actividad,
                        "nombre": act.nombre,
                        "descripcion": act.descripcion,
                        "precio_estimado": act.precio_estimado,
                        "categoria": act.categoria,
                        "horario_sugerido": act.horario_sugerido,
                        "ubicacion": act.ubicacion,
                        "link": act.link,
                        "nota": act.nota,
                        "precio_sospechoso": bool(act.precio_sospechoso),
                    } for act in iti.actividades
                ],
            } for iti in sorted(v.itinerarios, key=lambda i: i.dia)
        ],
    })
    return jsonify(respuesta), 200


@trip_bp.route('/<int:id_viaje>', methods=['PUT', 'PATCH'])
@requiere_usuario
def modificar_viaje(id_viaje):
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos"}), 400

    viaje = db.session.get(Viaje, id_viaje)
    if not viaje:
        return jsonify({"error": "Viaje no encontrado"}), 404
    if not es_el_mismo_usuario(viaje.id_usuario):
        return prohibido()

    # El dueño del viaje no se puede reasignar desde la API.
    datos.pop('id_usuario', None)

    try:
        viaje_actualizado = actualizar_viaje(id_viaje, datos)
        return jsonify({"mensaje": "Viaje actualizado", "id": viaje_actualizado.id_viaje}), 200
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        logger.exception("Error actualizando viaje %s", id_viaje)
        return jsonify({"error": str(e)}), 500


@trip_bp.route('/<int:id_viaje>', methods=['DELETE'])
@requiere_usuario
def baja_viaje(id_viaje):
    viaje = db.session.get(Viaje, id_viaje)
    if not viaje:
        return jsonify({"error": "Viaje no encontrado"}), 404
    if not es_el_mismo_usuario(viaje.id_usuario):
        return prohibido()

    if eliminar_viaje(id_viaje):
        return jsonify({"mensaje": "Viaje eliminado"}), 200
    return jsonify({"error": "Viaje no encontrado"}), 404


@trip_bp.route('/generate', methods=['POST'])
@requiere_usuario
def generate_viajes():
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos"}), 400

    id_usuario = datos.get('id_usuario')
    opciones = datos.get('opciones')
    id_user_preferences = datos.get('id_user_preferences')

    if not id_usuario or not opciones:
        return jsonify({"error": "Faltan datos requeridos (id_usuario, opciones)"}), 400

    if not es_el_mismo_usuario(id_usuario):
        return prohibido()

    try:
        group_id = guardar_viajes_generados(id_usuario, opciones, id_user_preferences)
        return jsonify({"mensaje": "Viajes generados", "group_id": group_id}), 200
    except (ValueError, KeyError) as ve:
        return jsonify({"error": f"Opciones de viaje inválidas: {ve}"}), 400
    except Exception as e:
        logger.exception("Error guardando viajes generados")
        return jsonify({"error": str(e)}), 500


@trip_bp.route('/usuario/<int:id_usuario>/drafts', methods=['GET'])
@requiere_usuario
def get_drafts_usuario(id_usuario):
    if not es_el_mismo_usuario(id_usuario):
        return prohibido()

    viajes = obtener_drafts_activos(id_usuario)
    return jsonify([_serializar_resumen(v) for v in viajes]), 200


@trip_bp.route('/<int:id_viaje>/select', methods=['POST'])
@requiere_usuario
def select_viaje(id_viaje):
    viaje = db.session.get(Viaje, id_viaje)
    if not viaje:
        return jsonify({"error": "Viaje no encontrado"}), 404
    if not es_el_mismo_usuario(viaje.id_usuario):
        return prohibido()

    try:
        confirmado = confirmar_viaje(id_viaje)
        if not confirmado:
            return jsonify({"error": "El viaje no es un borrador seleccionable"}), 409
        return jsonify({"mensaje": "Viaje confirmado", "id_viaje": confirmado.id_viaje}), 200
    except Exception as e:
        logger.exception("Error confirmando viaje %s", id_viaje)
        return jsonify({"error": str(e)}), 500
