from marshmallow import Schema, ValidationError, fields, validate, validates_schema

# Los tres niveles que genera la capa de integración (IA / n8n).
TIPOS_VIAJE = ["Economy", "Balanced", "Luxury"]


class ViajeSchema(Schema):
    id_usuario = fields.Integer(
        required=True,
        error_messages={"required": "El ID del usuario es obligatorio."}
    )
    destinos = fields.List(
        fields.String(validate=validate.Length(min=2, max=120)),
        required=True,
        validate=validate.Length(min=1, error="Debe haber al menos un destino."),
        error_messages={"required": "Los destinos son obligatorios."}
    )
    fecha_inicio = fields.Date(
        required=True,
        error_messages={
            "required": "La fecha de inicio es obligatoria.",
            "invalid": "Formato inválido. Usa YYYY-MM-DD."
        }
    )
    fecha_fin = fields.Date(
        required=True,
        error_messages={
            "required": "La fecha de fin es obligatoria.",
            "invalid": "Formato inválido. Usa YYYY-MM-DD."
        }
    )
    tipo_viaje = fields.String(
        required=True,
        validate=validate.Length(max=20),
        error_messages={"required": "El tipo de viaje es obligatorio."}
    )
    costo_total_estimado = fields.Float()
    imagen = fields.String(validate=validate.Length(max=500), allow_none=True)
    estado = fields.String(
        validate=validate.OneOf(["draft", "guardado"], error="Estado no válido.")
    )
    id_user_preferences = fields.Integer(
        allow_none=True,
        validate=validate.Range(min=1, error="El ID de preferencias debe ser un número positivo."),
        error_messages={"invalid": "El ID de preferencias debe ser un número entero."}
    )

    @validates_schema
    def validar_fechas(self, data, **kwargs):
        fecha_inicio = data.get("fecha_inicio")
        fecha_fin = data.get("fecha_fin")

        if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
            raise ValidationError(
                "La fecha de inicio no puede ser posterior a la fecha de fin.",
                field_name="fecha_inicio"
            )


viaje_schema = ViajeSchema()
