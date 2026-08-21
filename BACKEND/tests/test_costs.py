"""Regla de negocio de cálculo, ajuste por tipo de viaje y reoptimización."""

import pytest

from src.services.cost_service import (
    apply_cost_adjustment,
    calculate_base_cost,
    desglosar_costo_total,
    reoptimizar_por_presupuesto,
)


def test_costo_base_suma_las_cuatro_categorias():
    total = calculate_base_cost({
        "costo_alojamiento": 500,
        "costo_transporte": 300,
        "costo_actividades": 150,
        "costo_comidas": 50,
    })
    assert total == 1000


def test_costo_base_ignora_valores_invalidos():
    assert calculate_base_cost({"costo_alojamiento": "no es un número"}) == 0
    assert calculate_base_cost({}) == 0


@pytest.mark.parametrize("tipo, esperado", [
    ("Economy", 900.0),
    ("economico", 900.0),
    ("Balanced", 1100.0),
    ("confort", 1100.0),
    ("Luxury", 1250.0),
    ("lujo", 1250.0),
    ("desconocido", 1000.0),
    (None, 1000.0),
])
def test_ajuste_por_tipo_de_viaje(tipo, esperado):
    assert apply_cost_adjustment(1000.0, tipo) == esperado


def test_desglose_por_defecto_suma_el_total():
    desglose = desglosar_costo_total(2000)
    assert calculate_base_cost(desglose) == pytest.approx(2000, abs=0.01)
    assert desglose["costo_alojamiento"] == 700.0


def test_no_reoptimiza_si_entra_en_el_presupuesto():
    desglose = desglosar_costo_total(1000)
    resultado, reoptimizado = reoptimizar_por_presupuesto(desglose, 1500)

    assert reoptimizado is False
    assert resultado == desglose


def test_no_reoptimiza_sin_presupuesto():
    desglose = desglosar_costo_total(1000)
    _, reoptimizado = reoptimizar_por_presupuesto(desglose, None)
    assert reoptimizado is False


def test_reoptimiza_recortando_hasta_entrar_en_el_presupuesto():
    desglose = desglosar_costo_total(2000)
    resultado, reoptimizado = reoptimizar_por_presupuesto(desglose, 1500)

    assert reoptimizado is True
    assert calculate_base_cost(resultado) == pytest.approx(1500, abs=1.0)


def test_reoptimiza_recortando_primero_lo_discrecional():
    desglose = desglosar_costo_total(2000)
    resultado, _ = reoptimizar_por_presupuesto(desglose, 1900)

    # Un exceso chico se cubre sólo con actividades y comidas.
    assert resultado["costo_alojamiento"] == desglose["costo_alojamiento"]
    assert resultado["costo_transporte"] == desglose["costo_transporte"]
    assert resultado["costo_actividades"] < desglose["costo_actividades"]


def test_reoptimizacion_extrema_no_deja_valores_negativos():
    desglose = desglosar_costo_total(5000)
    resultado, _ = reoptimizar_por_presupuesto(desglose, 100)

    assert all(valor >= 0 for valor in resultado.values())
    assert calculate_base_cost(resultado) <= 101
