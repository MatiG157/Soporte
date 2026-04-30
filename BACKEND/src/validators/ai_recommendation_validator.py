class AIRecommendationValidator:
    @staticmethod
    def validate_generation_request(data):
        errors = []
        if not data.get('destino'):
            errors.append("El destino es requerido")
        if not data.get('fecha_inicio'):
            errors.append("La fecha de inicio es requerida")
        if not data.get('fecha_fin'):
            errors.append("La fecha de fin es requerida")
        if not data.get('costo_max') or not isinstance(data.get('costo_max'), (int, float)):
             errors.append("El costo máximo debe ser un número")
        if not data.get('cantidad_personas') or not isinstance(data.get('cantidad_personas'), int):
            errors.append("La cantidad de personas debe ser un número entero")
            
        return len(errors) == 0, errors
