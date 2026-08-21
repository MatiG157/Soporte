def validate_cost_data(data):
    """Valida el payload de costos antes de aplicar la regla de negocio."""
    errors = []

    if "id_viaje" not in data:
        errors.append("El campo 'id_viaje' es obligatorio.")

    cost_fields = [
        "costo_alojamiento",
        "costo_transporte",
        "costo_actividades",
        "costo_comidas",
        "costo_max",
    ]

    for field in cost_fields:
        if field in data and data[field] is not None:
            try:
                if float(data[field]) < 0:
                    errors.append(f"El costo en '{field}' no puede ser negativo.")
            except (TypeError, ValueError):
                errors.append(f"El campo '{field}' debe ser un valor numérico válido.")

    return errors
