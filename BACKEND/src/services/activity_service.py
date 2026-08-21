from src.models.init import db
from src.models.activity import Actividad
from src.models.itinerary import Itinerario
from src.validators.activity_validator import activity_schema


def crear_actividad(datos):
    datos_validados = activity_schema.load(datos)

    itinerario = db.session.get(Itinerario, datos_validados['id_itinerario'])
    if not itinerario:
        raise ValueError(
            f"No se encontró un itinerario con ID {datos_validados['id_itinerario']}")

    nueva_actividad = Actividad(
        id_itinerario=datos_validados['id_itinerario'],
        nombre=datos_validados['nombre'],
        descripcion=datos_validados.get('descripcion'),
        precio_estimado=datos_validados.get('precio_estimado'),
        categoria=datos_validados.get('categoria'),
        horario_sugerido=datos_validados.get('horario_sugerido'),
        ubicacion=datos_validados.get('ubicacion')
    )

    db.session.add(nueva_actividad)
    db.session.commit()
    return nueva_actividad


def obtener_actividades_por_itinerario(id_itinerario):
    return Actividad.query.filter_by(id_itinerario=id_itinerario).all()


def obtener_actividad_por_id(id_actividad):
    return db.session.get(Actividad, id_actividad)


def actualizar_actividad(id_actividad, datos):
    datos_validados = activity_schema.load(datos, partial=True)
    actividad = db.session.get(Actividad, id_actividad)

    if not actividad:
        return None

    actividad.nombre = datos_validados.get('nombre', actividad.nombre)
    actividad.descripcion = datos_validados.get('descripcion', actividad.descripcion)
    actividad.precio_estimado = datos_validados.get('precio_estimado', actividad.precio_estimado)
    actividad.categoria = datos_validados.get('categoria', actividad.categoria)
    actividad.horario_sugerido = datos_validados.get('horario_sugerido', actividad.horario_sugerido)
    actividad.ubicacion = datos_validados.get('ubicacion', actividad.ubicacion)

    db.session.commit()
    return actividad


def eliminar_actividad(id_actividad):
    actividad = db.session.get(Actividad, id_actividad)
    if actividad:
        db.session.delete(actividad)
        db.session.commit()
        return True
    return False
