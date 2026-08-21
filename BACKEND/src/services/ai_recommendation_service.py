"""Persistencia de las recomendaciones generadas por la IA.

La generación de itinerarios la hace **exclusivamente el flujo de n8n**, que
llama el frontend (`FRONTEND/trip_generator.py`). El backend no habla con
ningún proveedor de IA: sólo guarda lo que n8n devolvió, para poder auditar
después con qué datos se armó cada viaje.
"""

import json
import logging

from src.models.ai_recommendation import RecomendacionIA
from src.models.init import db

logger = logging.getLogger(__name__)


class AIRecommendationService:

    @staticmethod
    def save_recommendation(id_viaje, texto_generado, tipo="itinerario"):
        """Guarda la salida cruda de la IA asociada a un viaje."""
        if not isinstance(texto_generado, str):
            texto_generado = json.dumps(texto_generado, ensure_ascii=False, default=str)

        nueva_recomendacion = RecomendacionIA(
            id_viaje=id_viaje,
            texto_generado=texto_generado,
            tipo=tipo,
        )
        db.session.add(nueva_recomendacion)
        db.session.commit()
        return nueva_recomendacion

    @staticmethod
    def listar_por_viaje(id_viaje):
        return (
            RecomendacionIA.query
            .filter_by(id_viaje=id_viaje)
            .order_by(RecomendacionIA.fecha_generacion.desc())
            .all()
        )
