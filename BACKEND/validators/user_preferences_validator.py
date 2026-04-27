from marshmallow import Schema, fields, validate, validates_schema, ValidationError

class UserPreferencesSchema(Schema):
    id_usuario = fields.Integer(
        required=True, 
        error_messages={"required": "El ID del usuario es obligatorio para asociar sus preferencias."}
    )
    destino = fields.String(validate=validate.Length(max=120))
    costo_min = fields.Float(
        validate=validate.Range(min=0, error="El costo mínimo debe ser 0 o positivo.")
    )
    costo_max = fields.Float(
        validate=validate.Range(min=0, error="El costo máximo debe ser 0 o positivo.")
    )
    cantidad_personas = fields.Integer(
        validate=validate.Range(min=1, error="La cantidad de personas debe ser mayor a 0.")
    )
    grupo = fields.String(
        validate=validate.OneOf(
            ["familiar", "amigos", "educativo", "pareja", "solo"],
            error="Tipo de grupo no válido."
        )
    )
    tipos_alojamiento = fields.List(
        fields.Integer(),
        required=False
    )
    clima = fields.String(validate=validate.Length(max=50))
    edades_viajeros = fields.String(validate=validate.Length(max=100))
    tipo_transporte = fields.String(validate=validate.Length(max=50))
    fecha_inicio = fields.Date()
    fecha_fin = fields.Date()
    otros = fields.String()

    # Validación a nivel de esquema para comparar fechas
    @validates_schema
    def validar_fechas(self, data, **kwargs):
        fecha_inicio = data.get("fecha_inicio")
        fecha_fin = data.get("fecha_fin")
        
        if fecha_inicio and fecha_fin:
            if fecha_inicio >= fecha_fin:
                raise ValidationError(
                    "La fecha de inicio debe ser anterior a la fecha de fin.",
                    field_name="fecha_inicio"
                )

    # Validación a nivel de esquema para comparar los dos campos
    @validates_schema
    def validar_costos(self, data, **kwargs):
        costo_min = data.get("costo_min")
        costo_max = data.get("costo_max")
        
        # Validar solo si ambos campos están presentes en la petición
        if costo_min is not None and costo_max is not None:
            if costo_min >= costo_max:
                raise ValidationError(
                    "El costo mínimo debe ser estrictamente menor que el costo máximo.",
                    field_name="costo_min" # Esto asignará el error a este campo en la respuesta JSON
                )

# Instanciamos el validador
user_preferences_schema = UserPreferencesSchema()