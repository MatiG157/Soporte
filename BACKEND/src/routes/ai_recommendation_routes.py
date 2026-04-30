from flask import Blueprint, request, jsonify
from src.services.ai_recommendation_service import AIRecommendationService

ai_recommendation_bp = Blueprint('ai_recommendation', __name__, url_prefix='/api/recommendations')

@ai_recommendation_bp.route('/generate', methods=['POST'])
def generate_recommendation():
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Datos no proporcionados"}), 400
        
    required_fields = ['destino', 'fecha_inicio', 'fecha_fin', 'costo_max', 'cantidad_personas']
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        return jsonify({"error": f"Campos requeridos faltantes: {', '.join(missing_fields)}"}), 400

    try:
        recommendations = AIRecommendationService.generate_recommendations(data)
        return jsonify({
            "message": "Recomendaciones generadas exitosamente",
            "data": recommendations
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
