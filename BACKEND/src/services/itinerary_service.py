from src.models.init import db
from src.models.itinerary import Itinerario
from src.models.trip import Viaje
from src.validators.itinerary_validator import itinerario_schema


def crear_itinerario(datos):

    datos_validados = itinerario_schema.load(datos)

    id_viaje = datos_validados['id_viaje']
    viaje = db.session.get(Viaje, id_viaje)
    if not viaje:
        raise ValueError(f"No se encontró el viaje con ID {id_viaje}")

    nuevo_itinerario = Itinerario(
        id_viaje=id_viaje,
        dia=datos.get('dia'),
        resumen=datos.get('resumen')
    )
    db.session.add(nuevo_itinerario)
    db.session.commit()
    return nuevo_itinerario


def obtener_itinerarios_por_viaje(id_viaje):

    return Itinerario.query.filter_by(id_viaje=id_viaje).all()


def obtener_itinerario_por_id(id_itinerario):

    return db.session.get(Itinerario, id_itinerario)


def actualizar_itinerario(id_itinerario, datos):

    datos_validados = itinerario_schema.load(datos, partial=True)
    itinerario = db.session.get(Itinerario, id_itinerario)
    if not itinerario:
        return None

    itinerario.dia = datos_validados.get('dia', itinerario.dia)
    itinerario.resumen = datos_validados.get('resumen', itinerario.resumen)

    db.session.commit()
    return itinerario


def eliminar_itinerario(id_itinerario):

    itinerario = db.session.get(Itinerario, id_itinerario)
    if itinerario:
        db.session.delete(itinerario)
        db.session.commit()
        return True
    return False
