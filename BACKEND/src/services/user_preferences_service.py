from src.models.accommodation_type import TipoAlojamiento
from src.models.init import db
from src.models.user_preferences import PreferenciasUsuario
from src.validators.user_preferences_validator import user_preferences_schema

# Los nombres que usa el formulario web contra los del catálogo en base.
ALIAS_ALOJAMIENTO = {
    "hotel": "Hotel",
    "hostel": "Hostal",
    "hostal": "Hostal",
    "airbnb": "Airbnb",
    "departamento": "Apartamento",
    "apartamento": "Apartamento",
    "resort": "Resort",
    "camping": "Camping",
}

CAMPOS_SIMPLES = (
    "origen", "destinos", "costo_min", "costo_max", "cantidad_personas",
    "grupo", "hospedaje", "edades_viajeros", "tipo_transporte",
    "fecha_inicio", "fecha_fin", "act_preferidas", "otros",
)


def _resolver_tipos_alojamiento(ids_alojamientos, hospedaje_texto):
    """Devuelve las filas de TipoAlojamiento a asociar.

    Acepta tanto una lista de ids como el string separado por comas que manda
    el formulario ("hotel, airbnb"), creando el tipo en el catálogo si falta.
    """
    if ids_alojamientos:
        return TipoAlojamiento.query.filter(
            TipoAlojamiento.id_tipo.in_(ids_alojamientos)
        ).all()

    if not hospedaje_texto:
        return []

    encontrados = []
    for crudo in str(hospedaje_texto).split(","):
        clave = crudo.strip().lower()
        if not clave:
            continue
        nombre = ALIAS_ALOJAMIENTO.get(clave, crudo.strip().capitalize())
        tipo = TipoAlojamiento.query.filter_by(tipo=nombre).first()
        if tipo is None:
            tipo = TipoAlojamiento(tipo=nombre)
            db.session.add(tipo)
            db.session.flush()
        if tipo not in encontrados:
            encontrados.append(tipo)

    return encontrados


def crear_preferencia(datos):
    datos_validados = user_preferences_schema.load(datos)
    ids_alojamientos = datos_validados.get('tipos_alojamiento', [])

    nueva_preferencia = PreferenciasUsuario(
        id_usuario=datos_validados['id_usuario'],
        **{campo: datos_validados.get(campo) for campo in CAMPOS_SIMPLES}
    )

    nueva_preferencia.tipos_alojamiento = _resolver_tipos_alojamiento(
        ids_alojamientos, datos_validados.get('hospedaje')
    )

    db.session.add(nueva_preferencia)
    db.session.commit()
    return nueva_preferencia


def eliminar_preferencia(id_preferencia):
    preferencia = db.session.get(PreferenciasUsuario, id_preferencia)
    if preferencia:
        db.session.delete(preferencia)
        db.session.commit()
        return True
    return False


def actualizar_preferencia(id_preferencia, datos):
    datos_validados = user_preferences_schema.load(datos, partial=True)
    preferencia = db.session.get(PreferenciasUsuario, id_preferencia)

    if not preferencia:
        return None

    for campo in CAMPOS_SIMPLES:
        if campo in datos_validados:
            setattr(preferencia, campo, datos_validados[campo])

    if 'tipos_alojamiento' in datos_validados or 'hospedaje' in datos_validados:
        preferencia.tipos_alojamiento = _resolver_tipos_alojamiento(
            datos_validados.get('tipos_alojamiento', []),
            datos_validados.get('hospedaje', preferencia.hospedaje),
        )

    db.session.commit()
    return preferencia


def obtener_preferencias_por_usuario(id_usuario):
    return (
        PreferenciasUsuario.query
        .filter_by(id_usuario=id_usuario)
        .order_by(PreferenciasUsuario.id_preferencia.desc())
        .all()
    )
