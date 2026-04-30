import os
import google.generativeai as genai
from flask import current_app
from src.models.init import db
from src.models.ai_recommendation import RecomendacionIA
from src.models.trip import Viaje
import json

class AIRecommendationService:
    @staticmethod
    def generate_recommendations(preferences_data):
        # Configuracion de la API key
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY variable no seteada en el entorno")
            
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-pro-latest')

        prompt = f"""
        Actúa como un planificador de viajes experto. Genera 3 opciones de viaje (Económico, Estándar, Lujo) 
        basadas en las siguientes preferencias del usuario:
        
        Destino: {preferences_data.get('destino')}
        Fecha de Inicio: {preferences_data.get('fecha_inicio')}
        Fecha de Fin: {preferences_data.get('fecha_fin')}
        Presupuesto Máximo Estimado: {preferences_data.get('costo_max')}
        Cantidad de Personas: {preferences_data.get('cantidad_personas')}
        Grupo: {preferences_data.get('grupo')}
        Preferencias de Clima/Otras: {preferences_data.get('clima')}, {preferences_data.get('otros')}
        
        Para cada opción de viaje, devuelve un un objeto JSON estructurado que incluya:
        - tipo_viaje: "Económico", "Estándar" o "Lujo"
        - destino: El destino elegido
        - costo_total_estimado: Un valor numérico estimado del costo total.
        - desglose_costos: un objeto con (alojamiento, transporte, actividades, comidas)
        - itinerario: Un array de días, cada uno con un 'dia' (número) y un array de 'actividades'.
        - actividades: cada actividad debe tener (nombre, descripcion, categoria, horario, precio_estimado).
        
        Asegúrate de que la IA considere los costos reales promedio.
        Devuelve estrictamente un JSON válido con una lista de 3 viajes. Sin markdown.
        """

        response = model.generate_content(prompt)
        
        try:
            # En un entorno real deberíamos limpiar la respuesta de mardown si Gemini devuelve ```json
            result_text = response.text.replace("```json", "").replace("```", "").strip()
            viajes_recomendados = json.loads(result_text)
            return viajes_recomendados
        except Exception as e:
            raise RuntimeError(f"Error parseando la respuesta de la IA: {str(e)}")

    @staticmethod
    def save_recommendation(id_viaje, texto_generado, tipo="itinerario"):
        nueva_recomendacion = RecomendacionIA(
            id_viaje=id_viaje,
            texto_generado=texto_generado,
            tipo=tipo
        )
        db.session.add(nueva_recomendacion)
        db.session.commit()
        return nueva_recomendacion
