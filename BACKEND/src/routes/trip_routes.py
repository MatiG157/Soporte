from flask import Blueprint, request, jsonify
from marshmallow import ValidationError
from src.services.trip_service import (
    crear_viaje,
    obtener_viajes_por_usuario,
    obtener_viaje_por_id,
    actualizar_viaje,
    eliminar_viaje,
    guardar_viajes_generados,
    obtener_drafts_activos,
    confirmar_viaje
)

trip_bp = Blueprint('trip_bp', __name__)


@trip_bp.route('/', methods=['POST'])
def alta_viaje():
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos para crear el viaje"}), 400

    try:
        nuevo_viaje = crear_viaje(datos)
        return jsonify({"mensaje": "Viaje creado", "id": nuevo_viaje.id_viaje}), 201
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trip_bp.route('/usuario/<int:id_usuario>', methods=['GET'])
def get_viajes_usuario(id_usuario):
    viajes = obtener_viajes_por_usuario(id_usuario)
    if not viajes:
        return jsonify({"mensaje": "No hay viajes para este usuario"}), 404

    resultado = [{
        "id_viaje": v.id_viaje,
        "destinos": v.destinos,
        "fecha_inicio": v.fecha_inicio.isoformat(),
        "fecha_fin": v.fecha_fin.isoformat(),
        "tipo_viaje": v.tipo_viaje,
        "costo_total_estimado": v.costo_total_estimado,
        "estado": v.estado,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "imagen": v.imagen
    } for v in viajes]

    return jsonify(resultado), 200


@trip_bp.route('/<int:id_viaje>', methods=['GET'])
def get_viaje(id_viaje):
    from sqlalchemy.orm import joinedload
    from src.models.trip import Viaje
    from src.models.itinerary import Itinerario
    
    # Cargar viaje con sus itinerarios y actividades de manera optimizada
    v = Viaje.query.options(joinedload(Viaje.itinerarios).joinedload(Itinerario.actividades)).filter_by(id_viaje=id_viaje).first()
    
    if not v:
        return jsonify({"error": "Viaje no encontrado"}), 404

    return jsonify({
        "id_viaje": v.id_viaje,
        "id_usuario": v.id_usuario,
        "id_user_preferences": v.id_user_preferences,
        "destinos": v.destinos,
        "fecha_inicio": v.fecha_inicio.isoformat(),
        "fecha_fin": v.fecha_fin.isoformat(),
        "tipo_viaje": v.tipo_viaje,
        "costo_total_estimado": v.costo_total_estimado,
        "imagen": v.imagen,
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
                        "ubicacion": act.ubicacion
                    } for act in iti.actividades
                ]
            } for iti in v.itinerarios
        ]
    }), 200


@trip_bp.route('/<int:id_viaje>', methods=['PUT', 'PATCH'])
def modificar_viaje(id_viaje):
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos"}), 400

    try:
        viaje_actualizado = actualizar_viaje(id_viaje, datos)
        if not viaje_actualizado:
            return jsonify({"error": "Viaje no encontrado"}), 404

        return jsonify({"mensaje": "Viaje actualizado", "id": viaje_actualizado.id_viaje}), 200

    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trip_bp.route('/<int:id_viaje>', methods=['DELETE'])
def baja_viaje(id_viaje):
    if eliminar_viaje(id_viaje):
        return jsonify({"mensaje": "Viaje eliminado"}), 200
    return jsonify({"error": "Viaje no encontrado"}), 404


@trip_bp.route('/generate', methods=['POST'])
def generate_viajes():
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se enviaron datos"}), 400
    id_usuario = datos.get('id_usuario')
    opciones = datos.get('opciones')
    id_user_preferences = datos.get('id_user_preferences')
    if not id_usuario or not opciones:
        return jsonify({"error": "Faltan datos requeridos (id_usuario, opciones)"}), 400

    try:
        group_id = guardar_viajes_generados(id_usuario, opciones, id_user_preferences)
        return jsonify({"mensaje": "Viajes generados", "group_id": group_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trip_bp.route('/usuario/<int:id_usuario>/drafts', methods=['GET'])
def get_drafts_usuario(id_usuario):
    viajes = obtener_drafts_activos(id_usuario)
    if not viajes:
        return jsonify({"mensaje": "No hay drafts activos"}), 404

    resultado = [{
        "id_viaje": v.id_viaje,
        "destinos": v.destinos,
        "fecha_inicio": v.fecha_inicio.isoformat(),
        "fecha_fin": v.fecha_fin.isoformat(),
        "tipo_viaje": v.tipo_viaje,
        "costo_total_estimado": v.costo_total_estimado,
        "estado": v.estado,
        "group_id": v.group_id
    } for v in viajes]
    return jsonify(resultado), 200


@trip_bp.route('/<int:id_viaje>/select', methods=['POST'])
def select_viaje(id_viaje):
    try:
        viaje = confirmar_viaje(id_viaje)
        if not viaje:
            return jsonify({"error": "Viaje no encontrado o no es un draft"}), 404
        return jsonify({"mensaje": "Viaje confirmado", "id_viaje": viaje.id_viaje}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
