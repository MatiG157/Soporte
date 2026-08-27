from marshmallow import Schema, ValidationError, fields, validate, validates_schema

# Valores aceptados para el tipo de grupo.
# El formulario web usa las claves en inglés; el dominio las guarda en español.
# Este mapa se aplica en el servicio antes de persistir.
GRUPOS_VALIDOS = ["familiar", "amigos", "educativo", "pareja", "solo"]

MAPA_GRUPOS = {
    "family": "familiar",
    "familiar": "familiar",
    "friends": "amigos",
    "amigos": "amigos",
    "educational": "educativo",
    "educativo": "educativo",
    "couple": "pareja",
    "pareja": "pareja",
    "solo": "solo",
}


def normalizar_grupo(valor):
    """Traduce el valor que llega del formulario al valor del dominio."""
    if valor is None:
        return None
    return MAPA_GRUPOS.get(str(valor).strip().lower(), None)


class GrupoField(fields.String):
    """Campo que acepta las claves en inglés del form y las normaliza."""

    def _deserialize(self, value, attr, data, **kwargs):
        crudo = super()._deserialize(value, attr, data, **kwargs)
        normalizado = normalizar_grupo(crudo)
        if normalizado is None:
            raise ValidationError(
                f"Tipo de grupo no válido. Opciones: {', '.join(GRUPOS_VALIDOS)}."
            )
        return normalizado


class UserPreferencesSchema(Schema):
    id_usuario = fields.Integer(
        required=True,
        error_messages={"required": "El ID del usuario es obligatorio para asociar sus preferencias."}
    )
    destinos = fields.List(
        fields.String(validate=validate.Length(min=1, max=120, error="Cada destino debe tener entre 1 y 120 caracteres.")),
        validate=validate.Length(min=1, error="Debe haber al menos un destino."),
        error_messages={"invalid": "Los destinos deben ser una lista."}
    )
    origen = fields.String(validate=validate.Length(max=120))
    costo_min = fields.Float(
        validate=validate.Range(min=0, error="El costo mínimo debe ser 0 o positivo.")
    )
    costo_max = fields.Float(
        validate=validate.Range(min=0, error="El costo máximo debe ser 0 o positivo.")
    )
    cantidad_personas = fields.Integer(
        validate=validate.Range(min=1, error="La cantidad de personas debe ser mayor a 0.")
    )
    grupo = GrupoField()
    tipos_alojamiento = fields.List(fields.Integer(), required=False, load_only=True)
    hospedaje = fields.String(validate=validate.Length(max=100))
    edades_viajeros = fields.String(validate=validate.Length(max=100))
    tipo_transporte = fields.String(validate=validate.Length(max=100))
    fecha_inicio = fields.Date()
    fecha_fin = fields.Date()
    act_preferidas = fields.String(validate=validate.Length(max=100))
    otros = fields.String()

    @validates_schema
    def validar_fechas(self, data, **kwargs):
        fecha_inicio = data.get("fecha_inicio")
        fecha_fin = data.get("fecha_fin")

        if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
            raise ValidationError(
                "La fecha de inicio no puede ser posterior a la fecha de fin.",
                field_name="fecha_inicio"
            )

    @validates_schema
    def validar_costos(self, data, **kwargs):
        costo_min = data.get("costo_min")
        costo_max = data.get("costo_max")

        # Se permite que sean iguales (presupuesto cerrado).
        if costo_min is not None and costo_max is not None and costo_min > costo_max:
            raise ValidationError(
                "El costo mínimo no puede ser mayor que el costo máximo.",
                field_name="costo_min"
            )


user_preferences_schema = UserPreferencesSchema()
