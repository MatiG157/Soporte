from src.models.init import db
from src.models.accommodation_type import TipoAlojamiento
from src.validators.accommodation_type_validator import accommodation_type_schema


def crear_tipo_alojamiento(datos):
    datos_validados = accommodation_type_schema.load(datos)

    nuevo_tipo = TipoAlojamiento(
        tipo=datos_validados['tipo']
    )

    db.session.add(nuevo_tipo)
    db.session.commit()
    return nuevo_tipo


def obtener_tipos_alojamiento():
    return TipoAlojamiento.query.all()


def obtener_tipo_alojamiento_por_id(id_tipo):
    return db.session.get(TipoAlojamiento, id_tipo)


def actualizar_tipo_alojamiento(id_tipo, datos):
    datos_validados = accommodation_type_schema.load(datos, partial=True)
    tipo_alojamiento = db.session.get(TipoAlojamiento, id_tipo)

    if not tipo_alojamiento:
        return None

    tipo_alojamiento.tipo = datos_validados.get('tipo', tipo_alojamiento.tipo)

    db.session.commit()
    return tipo_alojamiento


def eliminar_tipo_alojamiento(id_tipo):
    tipo_alojamiento = db.session.get(TipoAlojamiento, id_tipo)
    if tipo_alojamiento:
        db.session.delete(tipo_alojamiento)
        db.session.commit()
        return True
    return False
