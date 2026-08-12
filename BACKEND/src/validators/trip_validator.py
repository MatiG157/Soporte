from marshmallow import Schema, fields, validate, validates_schema, ValidationError


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
    id_user_preferences = fields.Integer(
        validate=validate.Range(min=1, error="El ID de preferencias debe ser un número positivo."),
        error_messages={"invalid": "El ID de preferencias debe ser un número entero."}
    )


viaje_schema = ViajeSchema()
