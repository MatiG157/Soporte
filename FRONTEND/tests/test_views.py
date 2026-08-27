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


def test_budget_muestra_el_viaje_y_embebe_el_dashboard(logueado):
    """La página pone el encabezado; los números los pone el dashboard.

    Los totales estaban duplicados: una tarjeta fija acá y el mismo número en
    el dashboard, pero sólo el del dashboard reacciona a los filtros.
    """
    html = logueado.get("/budget/1").get_data(as_text=True)

    assert "Kioto, Japón" in html
    assert 'id="budget-dashboard-frame"' in html
    assert "id_viaje=1" in html

    # Las tarjetas de totales ya no están.
    assert 'id="val-base-total"' not in html
    assert 'data-i18n="budget_adjustment"' not in html


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


def test_login_sin_viajes_va_al_formulario(client, backend, monkeypatch):
    """Mandar a una lista vacía no sirve: si no tiene viajes, va a crear uno."""
    import api_client
    monkeypatch.setattr(api_client, "get_o_defecto",
                        lambda ruta, defecto=None, **kw: [] if "usuario" in ruta else defecto)

    with client.session_transaction() as sesion:
        sesion["_csrf_token"] = "token-de-test"

    respuesta = client.post("/login", json={"email": "a@b.com", "contrasena": "x"},
                            headers={"X-CSRF-Token": "token-de-test"})
    assert respuesta.get_json()["redirect"] == "/"


def test_login_con_viajes_va_a_mytrips(client, backend):
    with client.session_transaction() as sesion:
        sesion["_csrf_token"] = "token-de-test"

    respuesta = client.post("/login", json={"email": "a@b.com", "contrasena": "x"},
                            headers={"X-CSRF-Token": "token-de-test"})
    assert respuesta.get_json()["redirect"] == "/mytrips"


def test_el_sidebar_de_compare_tiene_todos_los_links(logueado, backend):
    """Regresión: en /compare no existía `viaje`, así que faltaba el link de
    Compare y el de Itinerary caía a My Trips."""
    backend.drafts = [
        {"id_viaje": i, "destinos": ["Osaka, Japan"], "fecha_inicio": "2030-03-10",
         "fecha_fin": "2030-03-14", "costo_total_estimado": 1000.0 * i, "estado": "draft",
         "group_id": "g", "imagen": None, "created_at": None, "tipo_viaje": tipo}
        for i, tipo in enumerate(["Economy", "Balanced", "Luxury"], start=1)
    ]

    html = logueado.get("/compare").get_data(as_text=True)

    assert 'href="/compare"' in html
    assert 'href="/itinerary/1"' in html      # al primer borrador, no a mytrips
    assert 'href="/budget/1"' in html


def test_index_muestra_la_pantalla_de_espera(client):
    """La generación tarda ~25s: sin feedback la espera se siente rota."""
    html = client.get("/").get_data(as_text=True)

    assert 'id="loading-overlay"' in html
    assert "loading.css" in html
    assert 'data-i18n="load_subtitle"' in html


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


# ─── Edición del itinerario recomendado ──────────────────────────────────────

def test_itinerario_muestra_los_controles_de_edicion(logueado):
    html = logueado.get("/itinerary/1").get_data(as_text=True)
    assert "act-edit-btn" in html
    assert "act-delete-btn" in html
    assert "act-add-btn" in html
    assert 'id="activityModal"' in html
    # El día se pasa al alta para saber a qué itinerario agregar la actividad.
    assert 'data-itinerario="1"' in html


def test_el_formulario_de_actividad_tiene_los_campos_asistidos(logueado):
    """Horario en dos selects, categoría en desplegable y ubicación con sugerencias."""
    html = logueado.get("/itinerary/1").get_data(as_text=True)

    assert 'id="act-hora-inicio"' in html
    assert 'id="act-hora-fin"' in html
    assert 'id="act-horario-ocupado"' in html          # qué franjas ya están tomadas
    assert '<select id="act-categoria"' in html        # ya no es texto libre
    assert 'id="act-categoria-otra"' in html           # …salvo eligiendo "Otra"
    assert 'id="act-ubicacion-options"' in html        # lista de sugerencias


def test_cada_dia_tiene_su_franja_horaria(logueado):
    """La franja se arma en JS; la plantilla deja el contenedor por día."""
    html = logueado.get("/itinerary/1").get_data(as_text=True)

    assert html.count('class="day-timeline ps-4 mb-4"') == 3   # tres días
    assert "dibujarFranjaHoraria" in html


def test_borrar_actividad_llama_al_backend(logueado, csrf, backend):
    respuesta = logueado.delete("/activities/3", headers=csrf)
    assert respuesta.status_code == 200
    assert ("DELETE", "/actividades/3", None) in backend.llamadas


def test_editar_actividad_manda_solo_los_campos_permitidos(logueado, csrf, backend):
    respuesta = logueado.patch("/activities/3", json={
        "nombre": "  Paseo por Gion  ",
        "precio_estimado": "80",
        "ubicacion": "Gion",
        "descripcion": "Caminata",
        "horario_sugerido": "18:00 - 20:00",
        "categoria": "Cultural",
        "id_itinerario": 99,        # no editable: se descarta
        "estado": "guardado",       # ajeno a la actividad: se descarta
    }, headers=csrf)

    assert respuesta.status_code == 200

    enviado = next(c[2] for c in backend.llamadas if c[1] == "/actividades/3")
    assert enviado["nombre"] == "Paseo por Gion"     # recortado
    assert enviado["precio_estimado"] == 80.0        # convertido a número
    assert "id_itinerario" not in enviado
    assert "estado" not in enviado


def test_editar_actividad_rechaza_un_precio_no_numerico(logueado, csrf):
    respuesta = logueado.patch("/activities/3", json={"precio_estimado": "gratis"},
                               headers=csrf)
    assert respuesta.status_code == 400


def test_crear_actividad_exige_titulo_y_dia(logueado, csrf):
    sin_dia = logueado.post("/activities", json={"nombre": "Cena"}, headers=csrf)
    assert sin_dia.status_code == 400

    sin_titulo = logueado.post("/activities", json={"id_itinerario": 1, "nombre": "  "},
                               headers=csrf)
    assert sin_titulo.status_code == 400


def test_crear_actividad_llama_al_backend(logueado, csrf, backend):
    respuesta = logueado.post("/activities", json={
        "id_itinerario": 2,
        "nombre": "Cena kaiseki",
        "precio_estimado": 120,
    }, headers=csrf)

    assert respuesta.status_code == 201
    enviado = next(c[2] for c in backend.llamadas if c[1] == "/actividades/")
    assert enviado["id_itinerario"] == 2
    assert enviado["precio_estimado"] == 120.0


@pytest.mark.parametrize("metodo, ruta", [
    ("delete", "/activities/3"),
    ("patch", "/activities/3"),
    ("post", "/activities"),
])
def test_las_rutas_de_actividades_exigen_sesion(client, metodo, ruta):
    """Sin sesión no se toca el itinerario de nadie.

    Se le da un token CSRF válido a propósito: sin él la petición muere antes,
    en el `before_request` de seguridad, y no se estaría probando el login.
    """
    with client.session_transaction() as sesion:
        sesion["_csrf_token"] = "token-de-test"

    respuesta = getattr(client, metodo)(ruta, json={"nombre": "x"},
                                        headers={"X-CSRF-Token": "token-de-test"})
    assert respuesta.status_code == 401


def test_el_viaje_no_se_puede_editar_desde_la_web(logueado, csrf):
    """Sólo se editan actividades: el viaje en sí ya no tiene formulario."""
    html = logueado.get("/itinerary/1").get_data(as_text=True)
    assert "editTripModal" not in html

    # Y la ruta que lo guardaba tampoco existe.
    respuesta = logueado.patch("/trips/1", json={"fecha_inicio": "2030-01-01"}, headers=csrf)
    assert respuesta.status_code == 405

    # Borrar el viaje sí sigue siendo posible desde My Trips.
    assert logueado.delete("/trips/1", headers=csrf).status_code == 200


def test_mytrips_no_ofrece_editar_el_viaje(logueado):
    html = logueado.get("/mytrips").get_data(as_text=True)
    assert "mytrips_edit" not in html
    assert "?edit=1" not in html
    assert "mytrips_delete" in html      # el resto del menú sigue
