"""Que todas las vistas rendericen y que las rutas protegidas lo estén."""

import pytest


@pytest.mark.parametrize("ruta", ["/", "/login", "/register"])
def test_paginas_publicas_renderizan(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 200


@pytest.mark.parametrize("ruta", ["/mytrips", "/settings", "/budget", "/itinerary/1", "/compare"])
def test_rutas_protegidas_redirigen_al_login(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


@pytest.mark.parametrize("ruta", ["/mytrips", "/settings", "/budget", "/budget/1", "/itinerary/1"])
def test_vistas_privadas_renderizan_logueado(logueado, ruta):
    respuesta = logueado.get(ruta)
    assert respuesta.status_code == 200, ruta


def test_mytrips_muestra_el_viaje(logueado):
    html = logueado.get("/mytrips").get_data(as_text=True)
    assert "Kioto" in html
    assert "Balanced" in html


def test_itinerario_muestra_los_destinos_y_no_la_columna_vieja(logueado):
    html = logueado.get("/itinerary/1").get_data(as_text=True)
    assert "Kioto, Japón" in html
    assert "Actividad 1" in html
    # El bug anterior: la plantilla usaba `viaje.destino`, que ya no existe.
    assert "Trip to </h1>" not in html


def test_budget_muestra_el_desglose(logueado):
    html = logueado.get("/budget/1").get_data(as_text=True)
    assert "chart-breakdown" in html
    assert "1,000" in html   # costo_total_base
    assert "1,100" in html   # costo_total_ajustado


def test_compare_redirige_al_inicio_sin_borradores(logueado):
    respuesta = logueado.get("/compare")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/")


def test_compare_renderiza_con_borradores(logueado, backend):
    backend.drafts = [
        {**{"id_viaje": i, "destinos": ["Kioto, Japón"], "fecha_inicio": "2030-03-10",
            "fecha_fin": "2030-03-12", "costo_total_estimado": 1000.0 * i,
            "estado": "draft", "group_id": "g", "imagen": None, "created_at": None},
         "tipo_viaje": tipo}
        for i, tipo in enumerate(["Economy", "Balanced", "Luxury"], start=1)
    ]

    html = logueado.get("/compare").get_data(as_text=True)
    assert "compare_plan_eco" in html
    assert "compare_plan_bal" in html
    assert "compare_plan_lux" in html
    # Los highlights salen de las actividades reales, no de texto fijo.
    assert "Actividad 1" in html


def test_pagina_404(client):
    respuesta = client.get("/ruta-que-no-existe")
    assert respuesta.status_code == 404
    assert "err_404_title" in respuesta.get_data(as_text=True)


def test_alias_viaje_redirige_al_itinerario(logueado):
    respuesta = logueado.get("/viaje/1")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/itinerary/1")


def test_todos_los_idiomas_estan_completos():
    """Las nueve traducciones tienen exactamente las mismas claves."""
    import glob
    import json
    import os

    raiz = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "i18n")
    archivos = sorted(glob.glob(os.path.join(raiz, "*.json")))
    assert len(archivos) == 9

    referencia = None
    for ruta in archivos:
        with open(ruta, encoding="utf-8") as f:
            claves = set(json.load(f))
        if referencia is None:
            referencia = claves
        assert claves == referencia, f"{os.path.basename(ruta)} no coincide con en.json"
