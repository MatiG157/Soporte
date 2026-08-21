import logging

from flask import Blueprint, jsonify, request

from src.auth import es_el_mismo_usuario, prohibido, requiere_usuario
from src.models.init import db
from src.models.trip import Viaje
from src.services.cost_service import create_or_update_cost, get_cost_by_trip
from src.validators.cost_validator import validate_cost_data

logger = logging.getLogger(__name__)

cost_bp = Blueprint('cost_bp', __name__)


def _dueno_del_viaje(id_viaje):
    viaje = db.session.get(Viaje, id_viaje)
    return viaje.id_usuario if viaje else None


@cost_bp.route('/', methods=['POST', 'PUT'])
@requiere_usuario
def save_cost_route():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No se enviaron datos"}), 400

    errors = validate_cost_data(data)
    if errors:
        return jsonify({"errores": errors}), 400

    dueno = _dueno_del_viaje(data['id_viaje'])
    if dueno is None:
        return jsonify({"error": "Viaje no encontrado"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    try:
        resultado = create_or_update_cost(data)
        return jsonify({
            "mensaje": "Costo guardado aplicando la regla de cálculo",
            "datos": resultado,
        }), 201
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except Exception as e:
        logger.exception("Error guardando costos")
        return jsonify({"error": str(e)}), 500


@cost_bp.route('/viajes/<int:id_viaje>', methods=['GET'])
@requiere_usuario
def get_cost_route(id_viaje):
    dueno = _dueno_del_viaje(id_viaje)
    if dueno is None:
        return jsonify({"error": "Viaje no encontrado"}), 404
    if not es_el_mismo_usuario(dueno):
        return prohibido()

    tipo_viaje = request.args.get('tipo_viaje')

    try:
        resultado = get_cost_by_trip(id_viaje, tipo_viaje)
        if not resultado:
            return jsonify({"error": "Costos no encontrados para el viaje especificado"}), 404
        return jsonify(resultado), 200
    except Exception as e:
        logger.exception("Error obteniendo costos del viaje %s", id_viaje)
        return jsonify({"error": str(e)}), 500
