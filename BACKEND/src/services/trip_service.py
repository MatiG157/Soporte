import json
import logging
import uuid
from datetime import date, datetime, timedelta

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
    "titulo": 255,
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


def construir_destinos(destinos, fecha_inicio, fecha_fin):
    """Arma los ViajeDestino repartiendo los días del viaje entre los destinos.

    El flujo manda `destinos` como lista de strings. Antes cada destino se
    creaba con las fechas del viaje COMPLETO, así que todos los días caían
    dentro del rango de todos: `_guardar_itinerario` busca por rango y corta en
    la primera coincidencia, con lo cual absolutamente todas las actividades
    quedaban colgadas del primer destino y el segundo aparecía vacío.

    Si un destino trae sus propias fechas (dict con `fecha_llegada` y
    `fecha_partida`), se respetan. Si no, se reparte en tramos consecutivos con
    el mismo criterio que usa el flujo de n8n: los primeros tramos se quedan con
    el día extra cuando la división no es exacta.
    """
    from src.models.trip_destination import ViajeDestino

    inicio = _a_fecha(fecha_inicio)
    fin = _a_fecha(fecha_fin)
    total_dias = max((fin - inicio).days + 1, 1)

    limpios = [d for d in (destinos or []) if d]
    if not limpios:
        return []

    cantidad = len(limpios)
    base, resto = divmod(total_dias, cantidad)

    filas = []
    cursor = 0
    for indice, destino in enumerate(limpios):
        # Un destino con fechas propias manda sobre el reparto automático.
        if isinstance(destino, dict) and destino.get("fecha_llegada") and destino.get("fecha_partida"):
            filas.append(ViajeDestino(
                nombre=str(destino.get("nombre") or "Sin destino")[:150],
                fecha_llegada=_a_fecha(destino["fecha_llegada"]),
                fecha_partida=_a_fecha(destino["fecha_partida"]),
            ))
            continue

        nombre = destino.get("nombre") if isinstance(destino, dict) else destino
        dias_del_tramo = max(base + (1 if indice < resto else 0), 1)

        filas.append(ViajeDestino(
            nombre=str(nombre or "Sin destino")[:150],
            fecha_llegada=inicio + timedelta(days=cursor),
            # -1: `fecha_partida` es el último día EN ese destino, no el de salida.
            fecha_partida=inicio + timedelta(days=min(cursor + dias_del_tramo - 1, total_dias - 1)),
        ))
        cursor += dias_del_tramo

    return filas


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

    for vd in construir_destinos(datos_validados['destinos'],
                                 nuevo_viaje.fecha_inicio, nuevo_viaje.fecha_fin):
        nuevo_viaje.viaje_destinos.append(vd)

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

    if 'destinos' in datos_validados:
        viaje.viaje_destinos.clear()
        # Las fechas nuevas, si vienen, mandan sobre el reparto de los tramos.
        for vd in construir_destinos(
                datos_validados['destinos'],
                datos_validados.get('fecha_inicio', viaje.fecha_inicio),
                datos_validados.get('fecha_fin', viaje.fecha_fin)):
            viaje.viaje_destinos.append(vd)
            
    viaje.fecha_inicio = datos_validados.get('fecha_inicio', viaje.fecha_inicio)
    viaje.fecha_fin = datos_validados.get('fecha_fin', viaje.fecha_fin)
    viaje.tipo_viaje = datos_validados.get('tipo_viaje', viaje.tipo_viaje)
    viaje.titulo = datos_validados.get('titulo', viaje.titulo)
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

        # A qué destino pertenece este día. Tres criterios, de más a menos preciso:
        #   1. `destino_indice`, si el generador lo declara.
        #   2. La fecha del día contra el rango de cada destino.
        #   3. El primer destino, como último recurso.
        destino_del_dia = None
        destinos = viaje.viaje_destinos

        indice = dia_data.get("destino_indice")
        if isinstance(indice, int) and 0 <= indice < len(destinos):
            destino_del_dia = destinos[indice]

        if destino_del_dia is None and viaje.fecha_inicio:
            fecha_dia = _a_fecha(viaje.fecha_inicio) + timedelta(days=nuevo_itinerario.dia - 1)
            for vd in destinos:
                if vd.fecha_llegada <= fecha_dia <= vd.fecha_partida:
                    destino_del_dia = vd
                    break

        if destino_del_dia is None and destinos:
            destino_del_dia = destinos[0]

        for act_data in dia_data.get("actividades", []):
            nueva_actividad = Actividad(
                nombre=_recortar(act_data.get("nombre"), LIMITES["nombre"]) or "Actividad",
                descripcion=act_data.get("descripcion") or "",
                precio_estimado=_a_float(act_data.get("precio_estimado")),
                categoria=_recortar(act_data.get("categoria"), LIMITES["categoria"]) or "",
                horario_sugerido=_recortar(
                    act_data.get("horario_sugerido"), LIMITES["horario_sugerido"]) or "",
                ubicacion=_recortar(act_data.get("ubicacion"), LIMITES["ubicacion"]) or "",
                destino_viaje=destino_del_dia

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
            id_user_preferences=id_user_preferences,
            fecha_inicio=_a_fecha(opcion["fecha_inicio"]),
            fecha_fin=_a_fecha(opcion["fecha_fin"]),
            tipo_viaje=tipo,
            costo_total_estimado=_a_float(opcion.get("costo_total_estimado")),
            imagen=_recortar(opcion.get("imagen"), LIMITES["imagen"]),
            group_id=group_id,
            estado="draft",
        )
        
        for vd in construir_destinos(opcion.get("destinos", []),
                                     viaje.fecha_inicio, viaje.fecha_fin):
            viaje.viaje_destinos.append(vd)

        # `titulo` sólo se asignaba al editar un viaje: los generados nacían con
        # NULL y el encabezado del presupuesto quedaba vacío.
        viaje.titulo = _recortar(
            opcion.get("titulo") or " → ".join(vd.nombre for vd in viaje.viaje_destinos),
            LIMITES["titulo"],
        )
        db.session.add(viaje)
        db.session.flush()  # necesito el id_viaje para costos y recomendación

        _guardar_itinerario(viaje, opcion.get("itinerario", []))

        # Costos. Hay dos caminos, y cuál se toma depende de si el generador
        # ya hizo el trabajo:
        #
        #   - Con `desglose_costos`: el flujo de n8n cotizó vuelo y alojamiento
        #     contra APIs reales y ya diferenció los tres niveles. Ese número se
        #     respeta tal cual. Aplicarle encima el multiplicador por tipo sería
        #     contar el premium dos veces, y reoptimizar la variante Luxury la
        #     dejaría con precio de presupuesto medio y contenido de cinco
        #     estrellas. Que Luxury exceda el presupuesto es intencional: para
        #     eso están las tres opciones.
        #
        #   - Sin desglose: el costo es una estimación, así que se reparte por
        #     categoría y ahí sí corren las reglas de negocio del TP
        #     (multiplicador por tipo de viaje y reoptimización por presupuesto).
        desglose_del_generador = opcion.get("desglose_costos")

        if desglose_del_generador:
            costo, reoptimizado = guardar_costo_de_viaje(
                viaje.id_viaje, desglose_del_generador, costo_max=None)
            viaje.costo_total_estimado = costo.costo_total_base
        else:
            costo, reoptimizado = guardar_costo_de_viaje(
                viaje.id_viaje, desglosar_costo_total(viaje.costo_total_estimado), costo_max)
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
