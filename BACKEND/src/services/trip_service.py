import uuid
from datetime import datetime, timedelta
from src.models.init import db
from src.models.trip import Viaje
from src.models.user import Usuario
from src.models.itinerary import Itinerario
from src.models.activity import Actividad
from src.validators.trip_validator import viaje_schema


def crear_viaje(datos):
    # Deserializa y valida con Marshmallow
    datos_validados = viaje_schema.load(datos)

    # Validamos que el usuario "dueño" del viaje exista en la DB
    usuario = Usuario.query.get(datos_validados['id_usuario'])
    if not usuario:
        raise ValueError(
            f"No se encontró un usuario con ID {datos_validados['id_usuario']}")

    nuevo_viaje = Viaje(
        id_usuario=datos_validados['id_usuario'],
        destinos=datos_validados['destinos'],
        id_user_preferences=datos_validados.get('id_user_preferences'),
        fecha_inicio=datos_validados['fecha_inicio'],
        fecha_fin=datos_validados['fecha_fin'],
        tipo_viaje=datos_validados['tipo_viaje'],
        costo_total_estimado=datos_validados.get('costo_total_estimado')
    )

    db.session.add(nuevo_viaje)
    db.session.commit()
    return nuevo_viaje


def obtener_viajes_por_usuario(id_usuario):
    return Viaje.query.filter_by(id_usuario=id_usuario).all()


def obtener_viaje_por_id(id_viaje):
    return Viaje.query.get(id_viaje)


def actualizar_viaje(id_viaje, datos):
    datos_validados = viaje_schema.load(datos, partial=True)
    viaje = Viaje.query.get(id_viaje)

    if not viaje:
        return None

    viaje.destinos = datos_validados.get('destinos', viaje.destinos)
    viaje.fecha_inicio = datos_validados.get(
        'fecha_inicio', viaje.fecha_inicio)
    viaje.fecha_fin = datos_validados.get('fecha_fin', viaje.fecha_fin)
    viaje.tipo_viaje = datos_validados.get('tipo_viaje', viaje.tipo_viaje)
    viaje.costo_total_estimado = datos_validados.get(
        'costo_total_estimado', viaje.costo_total_estimado)

    db.session.commit()
    return viaje


def eliminar_viaje(id_viaje):
    viaje = Viaje.query.get(id_viaje)
    if viaje:
        db.session.delete(viaje)
        db.session.commit()
        return True
    return False


def guardar_viajes_generados(id_usuario, opciones_generadas, id_user_preferences=None):
    # Borrar drafts previos del usuario obteniéndolos para que ORM aplique cascade
    drafts_previos = Viaje.query.filter_by(id_usuario=id_usuario, estado="draft").all()
    for draft in drafts_previos:
        db.session.delete(draft)

    group_id = str(uuid.uuid4())
    viajes_creados = []

    for opcion in opciones_generadas:
        viaje = Viaje(
            id_usuario=id_usuario,
            destinos=opcion["destinos"],
            id_user_preferences=id_user_preferences,
            fecha_inicio=opcion["fecha_inicio"],
            fecha_fin=opcion["fecha_fin"],
            tipo_viaje=opcion["tipo"],
            costo_total_estimado=opcion.get("costo_total_estimado"),
            group_id=group_id,
            estado="draft"
        )
        db.session.add(viaje)
        
        # Guardar itinerario
        itinerario_data = opcion.get("itinerario", [])
        for dia_data in itinerario_data:
            nuevo_itinerario = Itinerario(
                dia=dia_data["dia"],
                resumen=dia_data["resumen"]
            )
            nuevo_itinerario.viaje = viaje
            db.session.add(nuevo_itinerario)
            
            # Guardar actividades
            for act_data in dia_data.get("actividades", []):
                nueva_actividad = Actividad(
                    nombre=act_data["nombre"],
                    descripcion=act_data.get("descripcion", ""),
                    precio_estimado=act_data.get("precio_estimado", 0.0),
                    categoria=act_data.get("categoria", ""),
                    horario_sugerido=act_data.get("horario_sugerido", ""),
                    ubicacion=act_data.get("ubicacion", "")
                )
                nueva_actividad.itinerario = nuevo_itinerario
                db.session.add(nueva_actividad)
                
        viajes_creados.append(viaje)

    db.session.commit()
    return group_id


def obtener_drafts_activos(id_usuario):
    # Busca el group_id más reciente
    ultimo_viaje = Viaje.query.filter_by(id_usuario=id_usuario, estado="draft")\
        .order_by(Viaje.created_at.desc()).first()

    if not ultimo_viaje:
        return []

    return Viaje.query.filter_by(group_id=ultimo_viaje.group_id).all()


def confirmar_viaje(id_viaje):
    viaje_seleccionado = Viaje.query.get(id_viaje)
    if not viaje_seleccionado or viaje_seleccionado.estado != "draft":
        return None

    # Cambiar estado a guardado
    viaje_seleccionado.estado = "guardado"

    # Borrar los otros drafts del mismo grupo obteniéndolos para que ORM aplique cascade
    otros_drafts = Viaje.query.filter(
        Viaje.group_id == viaje_seleccionado.group_id,
        Viaje.id_viaje != id_viaje
    ).all()
    
    for draft in otros_drafts:
        db.session.delete(draft)

    db.session.commit()
    return viaje_seleccionado
