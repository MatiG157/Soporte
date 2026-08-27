from src.models.init import db
from src.models.activity import Actividad
from src.models.itinerary import Itinerario
from src.services.cost_service import ajustar_costo_por_actividades
from src.validators.activity_validator import activity_schema


def _a_float(valor, por_defecto=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return por_defecto


def _id_viaje_de(id_itinerario):
    itinerario = db.session.get(Itinerario, id_itinerario)
    return itinerario.id_viaje if itinerario else None


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
    # El costo del viaje sube lo que cuesta la actividad nueva.
    ajustar_costo_por_actividades(
        itinerario.id_viaje, _a_float(nueva_actividad.precio_estimado)
    )
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

    precio_anterior = _a_float(actividad.precio_estimado)

    actividad.nombre = datos_validados.get('nombre', actividad.nombre)
    actividad.descripcion = datos_validados.get('descripcion', actividad.descripcion)
    actividad.precio_estimado = datos_validados.get('precio_estimado', actividad.precio_estimado)
    actividad.categoria = datos_validados.get('categoria', actividad.categoria)
    actividad.horario_sugerido = datos_validados.get('horario_sugerido', actividad.horario_sugerido)
    actividad.ubicacion = datos_validados.get('ubicacion', actividad.ubicacion)

    # Sólo la diferencia de precio mueve el costo del viaje.
    diferencia = _a_float(actividad.precio_estimado) - precio_anterior
    if diferencia:
        id_viaje = _id_viaje_de(actividad.id_itinerario)
        if id_viaje is not None:
            ajustar_costo_por_actividades(id_viaje, diferencia)

    db.session.commit()
    return actividad


def eliminar_actividad(id_actividad):
    actividad = db.session.get(Actividad, id_actividad)
    if actividad:
        id_viaje = _id_viaje_de(actividad.id_itinerario)
        precio = _a_float(actividad.precio_estimado)

        db.session.delete(actividad)
        # Lo que costaba la actividad deja de contar en el viaje.
        if id_viaje is not None:
            ajustar_costo_por_actividades(id_viaje, -precio)

        db.session.commit()
        return True
    return False
