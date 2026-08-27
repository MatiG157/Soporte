"""Capa de negocio: regla de cálculo de costos y ajuste por tipo de viaje."""

import logging

from src.models.cost import Costo
from src.models.init import db
from src.models.trip import Viaje

logger = logging.getLogger(__name__)

# Regla de negocio: multiplicador según el tipo de viaje elegido.
# Se aceptan tanto las claves que genera la IA (Economy/Balanced/Luxury)
# como sus equivalentes en español.
MULTIPLICADORES = {
    "economy": 0.90,
    "economico": 0.90,
    "económico": 0.90,
    "mochilero": 0.90,
    "balanced": 1.10,
    "confort": 1.10,
    "estandar": 1.10,
    "estándar": 1.10,
    "luxury": 1.25,
    "lujo": 1.25,
    "premium": 1.25,
}

# Reparto por defecto del costo total cuando no llega un desglose de la IA.
REPARTO_POR_DEFECTO = {
    "costo_alojamiento": 0.35,
    "costo_transporte": 0.30,
    "costo_actividades": 0.20,
    "costo_comidas": 0.15,
}


def _a_float(valor, por_defecto=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return por_defecto


def calculate_base_cost(data):
    """Regla de Negocio de Cálculo: alojamiento + transporte + actividades + comidas."""
    return (
        _a_float(data.get("costo_alojamiento"))
        + _a_float(data.get("costo_transporte"))
        + _a_float(data.get("costo_actividades"))
        + _a_float(data.get("costo_comidas"))
    )


def apply_cost_adjustment(base_cost, tipo_viaje):
    """Regla de Negocio: ajusta el valor final según el tipo de viaje elegido."""
    if tipo_viaje is None:
        return base_cost
    multiplicador = MULTIPLICADORES.get(str(tipo_viaje).strip().lower(), 1.0)
    return round(_a_float(base_cost) * multiplicador, 2)


def desglosar_costo_total(costo_total):
    """Reparte un costo total entre las cuatro categorías, con el reparto por defecto."""
    total = _a_float(costo_total)
    return {
        clave: round(total * proporcion, 2)
        for clave, proporcion in REPARTO_POR_DEFECTO.items()
    }


def reoptimizar_por_presupuesto(desglose, costo_max):
    """Si el costo supera el presupuesto del usuario, escala el desglose para entrar.

    Se recorta primero lo discrecional (actividades y comidas) y recién después
    alojamiento y transporte, que son gastos difíciles de evitar.
    """
    presupuesto = _a_float(costo_max, 0.0)
    if presupuesto <= 0:
        return desglose, False

    total = calculate_base_cost(desglose)
    if total <= presupuesto:
        return desglose, False

    exceso = total - presupuesto
    ajustado = dict(desglose)

    # Primera pasada: recortar hasta 40% de actividades y comidas.
    for clave in ("costo_actividades", "costo_comidas"):
        if exceso <= 0:
            break
        disponible = _a_float(ajustado.get(clave)) * 0.40
        recorte = min(disponible, exceso)
        ajustado[clave] = round(_a_float(ajustado.get(clave)) - recorte, 2)
        exceso -= recorte

    # Segunda pasada: escalar proporcionalmente lo que quede.
    if exceso > 0:
        total_restante = calculate_base_cost(ajustado)
        if total_restante > 0:
            factor = max((total_restante - exceso) / total_restante, 0.0)
            ajustado = {
                clave: round(_a_float(valor) * factor, 2)
                for clave, valor in ajustado.items()
            }

    return ajustado, True


def guardar_costo_de_viaje(id_viaje, desglose, costo_max=None):
    """Crea o actualiza el Costo de un viaje aplicando la regla de negocio.

    Devuelve `(objeto_costo, fue_reoptimizado)`.
    """
    desglose_final, reoptimizado = reoptimizar_por_presupuesto(desglose, costo_max)
    total_base = calculate_base_cost(desglose_final)

    costo = Costo.query.filter_by(id_viaje=id_viaje).first()
    if costo is None:
        costo = Costo(id_viaje=id_viaje)
        db.session.add(costo)

    costo.costo_alojamiento = _a_float(desglose_final.get("costo_alojamiento"))
    costo.costo_transporte = _a_float(desglose_final.get("costo_transporte"))
    costo.costo_actividades = _a_float(desglose_final.get("costo_actividades"))
    costo.costo_comidas = _a_float(desglose_final.get("costo_comidas"))
    costo.costo_total_base = round(total_base, 2)

    return costo, reoptimizado


def ajustar_costo_por_actividades(id_viaje, delta):
    """Mueve el costo del viaje cuando se agrega, edita o borra una actividad.

    Se aplica la **diferencia** en vez de recalcular `costo_actividades` como la
    suma de las actividades cargadas. El motivo es que el desglose que manda n8n
    y la suma de los precios actividad por actividad son dos salidas
    independientes del flujo y no coinciden: recalcular haría saltar el costo
    del viaje entero la primera vez que el usuario toca cualquier actividad.
    Con el delta, borrar una actividad de $380 baja el viaje exactamente $380,
    que es lo que el usuario espera ver.

    No hace commit: lo hace quien llama, junto con el cambio de la actividad.
    """
    delta = _a_float(delta)
    if not delta:
        return None

    costo = Costo.query.filter_by(id_viaje=id_viaje).first()
    viaje = db.session.get(Viaje, id_viaje)
    if costo is None or viaje is None:
        return None

    # El viaje puede tener el multiplicador del tipo aplicado (cuando el costo
    # fue una estimación) o no (cuando n8n mandó desglose). Se conserva la
    # relación que ya tenía en vez de volver a decidirla acá, que es lo que
    # haría `apply_cost_adjustment` y contaría el premium dos veces.
    base_previa = _a_float(costo.costo_total_base)
    factor = (_a_float(viaje.costo_total_estimado) / base_previa) if base_previa else 1.0

    costo.costo_actividades = max(
        0.0, round(_a_float(costo.costo_actividades) + delta, 2)
    )
    costo.costo_total_base = round(
        calculate_base_cost({
            "costo_alojamiento": costo.costo_alojamiento,
            "costo_transporte": costo.costo_transporte,
            "costo_actividades": costo.costo_actividades,
            "costo_comidas": costo.costo_comidas,
        }),
        2,
    )
    viaje.costo_total_estimado = round(costo.costo_total_base * factor, 2)

    return costo


def create_or_update_cost(data):
    id_viaje = data["id_viaje"]

    viaje = db.session.get(Viaje, id_viaje)
    if viaje is None:
        raise ValueError(f"No se encontró el viaje con ID {id_viaje}")

    costo, reoptimizado = guardar_costo_de_viaje(id_viaje, data, data.get("costo_max"))

    # Mantener sincronizado el costo total del viaje con la regla de ajuste.
    viaje.costo_total_estimado = apply_cost_adjustment(
        costo.costo_total_base, viaje.tipo_viaje
    )

    db.session.commit()

    return {
        "id_costo": costo.id_costo,
        "id_viaje": costo.id_viaje,
        "costo_total_base": costo.costo_total_base,
        "costo_total_ajustado": viaje.costo_total_estimado,
        "reoptimizado_por_presupuesto": reoptimizado,
    }


def get_cost_by_trip(id_viaje, tipo_viaje=None):
    costo = Costo.query.filter_by(id_viaje=id_viaje).first()
    if not costo:
        return None

    respuesta = {
        "id_costo": costo.id_costo,
        "id_viaje": costo.id_viaje,
        "costo_alojamiento": costo.costo_alojamiento,
        "costo_transporte": costo.costo_transporte,
        "costo_actividades": costo.costo_actividades,
        "costo_comidas": costo.costo_comidas,
        "costo_total_base": costo.costo_total_base,
    }

    # Sin `tipo_viaje` explícito se informa lo que quedó persistido en el viaje:
    # el ajuste se decide al guardar, no al leer. Recalcularlo acá volvería a
    # aplicar el multiplicador sobre costos que ya venían cotizados.
    if tipo_viaje is None:
        viaje = db.session.get(Viaje, id_viaje)
        if viaje:
            respuesta["tipo_viaje_aplicado"] = viaje.tipo_viaje
            respuesta["costo_total_ajustado"] = (
                viaje.costo_total_estimado
                if viaje.costo_total_estimado is not None
                else costo.costo_total_base
            )
        return respuesta

    # Con `tipo_viaje` explícito se simula: "¿cuánto costaría este viaje si
    # fuera de otro nivel?". Ahí sí se recalcula.
    respuesta["tipo_viaje_aplicado"] = tipo_viaje
    respuesta["costo_total_ajustado"] = apply_cost_adjustment(
        costo.costo_total_base, tipo_viaje
    )
    return respuesta
