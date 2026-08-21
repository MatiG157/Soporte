"""Consulta de las recomendaciones de IA guardadas.

No hay endpoint de generación: los itinerarios los produce el flujo de n8n,
que llama el frontend. Acá sólo se leen las recomendaciones ya persistidas.
"""

import logging

from flask import Blueprint, jsonify

from src.auth import es_el_mismo_usuario, prohibido, requiere_usuario
from src.models.init import db
from src.models.trip import Viaje
from src.services.ai_recommendation_service import AIRecommendationService

logger = logging.getLogger(__name__)

ai_recommendation_bp = Blueprint('ai_recommendation', __name__)


@ai_recommendation_bp.route('/viaje/<int:id_viaje>', methods=['GET'])
@requiere_usuario
def listar_recomendaciones(id_viaje):
    viaje = db.session.get(Viaje, id_viaje)
    if not viaje:
        return jsonify({"error": "Viaje no encontrado"}), 404
    if not es_el_mismo_usuario(viaje.id_usuario):
        return prohibido()

    recomendaciones = AIRecommendationService.listar_por_viaje(id_viaje)
    return jsonify([
        {
            "id_recomendacion": r.id_recomendacion,
            "id_viaje": r.id_viaje,
            "tipo": r.tipo,
            "texto_generado": r.texto_generado,
            "fecha_generacion": r.fecha_generacion.isoformat() if r.fecha_generacion else None,
        } for r in recomendaciones
    ]), 200
