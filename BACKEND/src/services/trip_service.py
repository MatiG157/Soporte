import json
import logging
import uuid
from datetime import date, datetime

from src.models.activity import Actividad
from src.models.ai_recommendation import RecomendacionIA
from src.models.init import db
from src.models.itinerary import Itinerario
from src.models.trip import Viaje
from src.models.user import Usuario
from src.models.user_preferences import PreferenciasUsuario
from src.services.cost_service import (
    apply_cost_adjustment,
    desglosar_costo_total,
    guardar_costo_de_viaje,
)
from src.validators.trip_validator import viaje_schema

logger = logging.getLogger(__name__)

# Límites de las columnas: la IA puede devolver textos más largos de la cuenta.
LIMITES = {
    "nombre": 120,
    "categoria": 80,
    "horario_sugerido": 30,
    "ubicacion": 150,
    "tipo_viaje": 20,
    "imagen": 500,
}


def _recortar(valor, limite):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto[:limite] if len(texto) > limite else texto


def _a_fecha(valor):
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    return datetime.strptime(str(valor), "%Y-%m-%d").date()


def _a_float(valor, por_defecto=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return por_defecto


def crear_viaje(datos):
    datos_validados = viaje_schema.load(datos)

    usuario = db.session.get(Usuario, datos_validados['id_usuario'])
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
        costo_total_estimado=datos_validados.get('costo_total_estimado'),
        imagen=datos_validados.get('imagen'),
        estado=datos_validados.get('estado', 'draft'),
    )

    db.session.add(nuevo_viaje)
    db.session.commit()
    return nuevo_viaje


def obtener_viajes_por_usuario(id_usuario):
    return (
        Viaje.query
        .filter_by(id_usuario=id_usuario)
        .order_by(Viaje.fecha_inicio.desc())
        .all()
    )


def obtener_viaje_por_id(id_viaje):
    return db.session.get(Viaje, id_viaje)


def actualizar_viaje(id_viaje, datos):
    datos_validados = viaje_schema.load(datos, partial=True)
    viaje = db.session.get(Viaje, id_viaje)

    if not viaje:
        return None

    viaje.destinos = datos_validados.get('destinos', viaje.destinos)
    viaje.fecha_inicio = datos_validados.get('fecha_inicio', viaje.fecha_inicio)
    viaje.fecha_fin = datos_validados.get('fecha_fin', viaje.fecha_fin)
    viaje.tipo_viaje = datos_validados.get('tipo_viaje', viaje.tipo_viaje)
    viaje.costo_total_estimado = datos_validados.get(
        'costo_total_estimado', viaje.costo_total_estimado)
    viaje.imagen = datos_validados.get('imagen', viaje.imagen)
    viaje.estado = datos_validados.get('estado', viaje.estado)

    db.session.commit()
    return viaje


def eliminar_viaje(id_viaje):
    viaje = db.session.get(Viaje, id_viaje)
    if viaje:
        db.session.delete(viaje)
        db.session.commit()
        return True
    return False


def _presupuesto_de_preferencias(id_user_preferences):
    if not id_user_preferences:
        return None
    preferencia = db.session.get(PreferenciasUsuario, id_user_preferences)
    return preferencia.costo_max if preferencia else None


def _guardar_itinerario(viaje, itinerario_data):
    """Crea los itinerarios y actividades de un viaje. Devuelve el total de actividades."""
    total_actividades = 0

    for indice, dia_data in enumerate(itinerario_data, start=1):
        nuevo_itinerario = Itinerario(
            dia=int(dia_data.get("dia") or indice),
            resumen=dia_data.get("resumen") or "",
        )
        nuevo_itinerario.viaje = viaje
        db.session.add(nuevo_itinerario)

        for act_data in dia_data.get("actividades", []):
            nueva_actividad = Actividad(
                nombre=_recortar(act_data.get("nombre"), LIMITES["nombre"]) or "Actividad",
                descripcion=act_data.get("descripcion") or "",
                precio_estimado=_a_float(act_data.get("precio_estimado")),
                categoria=_recortar(act_data.get("categoria"), LIMITES["categoria"]) or "",
                horario_sugerido=_recortar(
                    act_data.get("horario_sugerido"), LIMITES["horario_sugerido"]) or "",
                ubicacion=_recortar(act_data.get("ubicacion"), LIMITES["ubicacion"]) or "",
            )
            nueva_actividad.itinerario = nuevo_itinerario
            db.session.add(nueva_actividad)
            total_actividades += 1

    return total_actividades


def guardar_viajes_generados(id_usuario, opciones_generadas, id_user_preferences=None):
    """Persiste las N variantes generadas por la capa de integración (IA / n8n).

    Guarda, por cada opción: el viaje, su itinerario con actividades, el desglose
    de costos (aplicando la regla de negocio y la reoptimización por presupuesto)
    y la recomendación cruda de la IA para trazabilidad.
    """
    usuario = db.session.get(Usuario, id_usuario)
    if not usuario:
        raise ValueError(f"No se encontró un usuario con ID {id_usuario}")

    if not opciones_generadas:
        raise ValueError("No se recibió ninguna opción de viaje para guardar")

    # Los drafts previos se descartan: sólo vive un grupo de opciones por usuario.
    for draft in Viaje.query.filter_by(id_usuario=id_usuario, estado="draft").all():
        db.session.delete(draft)

    costo_max = _presupuesto_de_preferencias(id_user_preferences)
    group_id = str(uuid.uuid4())
    viajes_creados = []

    for opcion in opciones_generadas:
        tipo = _recortar(opcion.get("tipo") or opcion.get("tipo_viaje"), LIMITES["tipo_viaje"])
        if not tipo:
            raise ValueError("Cada opción de viaje debe indicar su tipo")

        viaje = Viaje(
            id_usuario=id_usuario,
            destinos=opcion["destinos"],
            id_user_preferences=id_user_preferences,
            fecha_inicio=_a_fecha(opcion["fecha_inicio"]),
            fecha_fin=_a_fecha(opcion["fecha_fin"]),
            tipo_viaje=tipo,
            costo_total_estimado=_a_float(opcion.get("costo_total_estimado")),
            imagen=_recortar(opcion.get("imagen"), LIMITES["imagen"]),
            group_id=group_id,
            estado="draft",
        )
        db.session.add(viaje)
        db.session.flush()  # necesito el id_viaje para costos y recomendación

        _guardar_itinerario(viaje, opcion.get("itinerario", []))

        # Regla de negocio de cálculo + reoptimización si se pasa del presupuesto.
        desglose = opcion.get("desglose_costos") or desglosar_costo_total(
            viaje.costo_total_estimado)
        costo, reoptimizado = guardar_costo_de_viaje(viaje.id_viaje, desglose, costo_max)
        viaje.costo_total_estimado = apply_cost_adjustment(costo.costo_total_base, tipo)

        if reoptimizado:
            logger.info(
                "Viaje %s reoptimizado para entrar en el presupuesto de %s",
                viaje.id_viaje, costo_max,
            )

        # Trazabilidad: se guarda la salida cruda de la IA.
        db.session.add(RecomendacionIA(
            id_viaje=viaje.id_viaje,
            texto_generado=json.dumps(opcion, ensure_ascii=False, default=str),
            tipo="reoptimizacion" if reoptimizado else "itinerario",
        ))

        viajes_creados.append(viaje)

    db.session.commit()
    return group_id


def obtener_drafts_activos(id_usuario):
    ultimo_viaje = (
        Viaje.query
        .filter_by(id_usuario=id_usuario, estado="draft")
        .order_by(Viaje.created_at.desc(), Viaje.id_viaje.desc())
        .first()
    )

    if not ultimo_viaje:
        return []

    return (
        Viaje.query
        .filter_by(id_usuario=id_usuario, group_id=ultimo_viaje.group_id)
        .order_by(Viaje.id_viaje.asc())
        .all()
    )


def confirmar_viaje(id_viaje):
    viaje_seleccionado = db.session.get(Viaje, id_viaje)
    if not viaje_seleccionado or viaje_seleccionado.estado != "draft":
        return None

    viaje_seleccionado.estado = "guardado"

    otros_drafts = Viaje.query.filter(
        Viaje.group_id == viaje_seleccionado.group_id,
        Viaje.id_usuario == viaje_seleccionado.id_usuario,
        Viaje.id_viaje != id_viaje,
    ).all()

    for draft in otros_drafts:
        db.session.delete(draft)

    db.session.commit()
    return viaje_seleccionado
