"""Que todas las vistas rendericen y que las rutas protegidas lo estén."""

import pytest


@pytest.mark.parametrize("ruta", ["/", "/login", "/register", "/about"])
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


def _viaje_de_las_capturas():
    """El caso real: el flujo manda el vuelo y el hotel como actividades."""
    return {
        "costos": {"costo_alojamiento": 440.0, "costo_transporte": 168.0,
                   "costo_actividades": 122.0, "costo_comidas": 144.0,
                   "costo_total_base": 874.0},
        "itinerarios": [
            {"dia": 1, "actividades": [
                {"categoria": "Transporte", "precio_estimado": 121.0},
                {"categoria": "Alojamiento", "precio_estimado": 440.0}]},
            {"dia": 2, "actividades": [
                {"categoria": "Naturaleza", "precio_estimado": 5.0},
                {"categoria": "Compras", "precio_estimado": 10.0},
                {"categoria": "Gastronomía", "precio_estimado": 8.0}]},
        ] + [{"dia": d, "actividades": []} for d in range(3, 9)],
    }


def test_el_gasto_del_dia_sale_de_sus_propias_actividades(app):
    """Regresión: un día de $561 aparecía como $100 en actividades.

    Se escalaban los precios con `costo_actividades / total cotizado`, pero el
    flujo manda el vuelo y el alojamiento COMO actividades y además dentro del
    desglose: el divisor incluía plata que no era de actividades y achicaba todo.
    """
    import app as modulo

    viaje = _viaje_de_las_capturas()
    modulo._calcular_costos_por_dia(viaje, cantidad_personas=1)

    dia1 = viaje["itinerarios"][0]
    # El vuelo y el check-in van a su rubro, no a "actividades".
    assert dia1["costos_dia"]["transporte"] == 121.0
    assert dia1["costos_dia"]["alojamiento"] == 440.0
    assert dia1["costos_dia"]["actividades"] == 0.0
    # Y lo cotizado es exactamente lo que suman las tarjetas de arriba.
    assert dia1["actividades_cotizadas"] == 561.0


def test_solo_se_estima_el_rubro_que_el_dia_no_cubre(app):
    """Sumarle el per-diem a un día que ya cotizó la cena la contaría dos veces."""
    import app as modulo

    viaje = _viaje_de_las_capturas()
    modulo._calcular_costos_por_dia(viaje, cantidad_personas=1)

    dia1, dia2 = viaje["itinerarios"][0], viaje["itinerarios"][1]

    # Día 1: tiene vuelo y hotel propios, sólo se le estima la comida.
    assert dia1["costos_dia_estimados"] == ["comidas"]
    assert dia1["costos_dia"]["comidas"] == 18.0        # 144 / 8 días

    # Día 2: la cena está cotizada en $8, así que no se estima.
    assert "comidas" not in dia2["costos_dia_estimados"]
    assert dia2["costos_dia"]["comidas"] == 8.0
    assert sorted(dia2["costos_dia_estimados"]) == ["alojamiento", "transporte"]


def test_un_vuelo_de_cero_no_se_reemplaza_por_el_promedio(app):
    """El vuelo de vuelta cuesta $0 porque ya viene en el de ida.

    La condición miraba el MONTO del rubro, así que un día con un vuelo de $0
    contaba como "sin transporte" y se le sumaba el promedio diario encima.
    """
    import app as modulo

    viaje = {
        "costos": {"costo_transporte": 1900.0, "costo_comidas": 0,
                   "costo_alojamiento": 0, "costo_actividades": 0},
        "itinerarios": [
            {"dia": 1, "actividades": [{"categoria": "Transporte", "precio_estimado": 900.0}]},
            {"dia": 2, "actividades": [{"categoria": "Cultural", "precio_estimado": 30.0}]},
            {"dia": 3, "actividades": [{"categoria": "Transporte", "precio_estimado": 0.0}]},
        ],
    }
    modulo._calcular_costos_por_dia(viaje, cantidad_personas=1)

    dia1, dia2, dia3 = viaje["itinerarios"]
    assert dia1["costos_dia"]["transporte"] == 900.0
    assert dia3["costos_dia"]["transporte"] == 0.0            # el vuelo incluido
    assert "transporte" not in dia3["costos_dia_estimados"]
    # El día sin ningún vuelo sí recibe el promedio.
    assert "transporte" in dia2["costos_dia_estimados"]


def test_un_vuelo_por_tramo_cae_en_su_dia(app):
    """Con un vuelo por etapa, cada día muestra el precio de ESE vuelo."""
    import app as modulo

    viaje = {
        "costos": {"costo_transporte": 1300.0, "costo_comidas": 0,
                   "costo_alojamiento": 0, "costo_actividades": 0},
        "itinerarios": [
            {"dia": 1, "actividades": [{"categoria": "Transporte", "precio_estimado": 900.0}]},
            {"dia": 2, "actividades": [{"categoria": "Transporte", "precio_estimado": 180.0}]},
            {"dia": 3, "actividades": [{"categoria": "Transporte", "precio_estimado": 220.0}]},
        ],
    }
    modulo._calcular_costos_por_dia(viaje, cantidad_personas=1)

    assert [i["costos_dia"]["transporte"] for i in viaje["itinerarios"]] == [900.0, 180.0, 220.0]
    assert all(not i["costos_dia_estimados"] for i in viaje["itinerarios"])


def test_el_desglose_se_convierte_a_por_persona(app):
    """Las actividades vienen por persona y el desglose es del grupo."""
    import app as modulo

    viaje = _viaje_de_las_capturas()
    modulo._calcular_costos_por_dia(viaje, cantidad_personas=2)

    # 144 de comidas / 8 días / 2 personas
    assert viaje["itinerarios"][0]["costos_dia"]["comidas"] == 9.0


def test_sin_costos_solo_se_muestran_las_actividades(app):
    import app as modulo

    viaje = {"costos": {}, "itinerarios": [
        {"dia": 1, "actividades": [{"categoria": "Cultural", "precio_estimado": 10.0}]}]}
    modulo._calcular_costos_por_dia(viaje)

    itin = viaje["itinerarios"][0]
    assert itin["costos_dia"]["actividades"] == 10.0
    assert itin["total_dia"] == 10.0
    assert itin["costos_dia_estimados"] == []


def test_compare_no_aparece_en_un_viaje_guardado(logueado, backend):
    """Regresión: bastaba con que existiera un borrador para que el link de
    Compare saliera en TODOS los viajes, incluso en uno guardado sin relación."""
    backend.drafts = [{
        "id_viaje": 99, "destinos": [], "fecha_inicio": "2030-03-10",
        "fecha_fin": "2030-03-12", "costo_total_estimado": 1000.0, "estado": "draft",
        "group_id": "g", "imagen": None, "created_at": None, "tipo_viaje": "Economy",
    }]

    # VIAJE_GUARDADO tiene estado "guardado": no pertenece al grupo de borradores.
    html = logueado.get("/itinerary/1").get_data(as_text=True)
    assert 'href="/compare"' not in html


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


# ─── Aviso de presupuesto en /compare ────────────────────────────────────────

def _tres_borradores():
    return [
        {"id_viaje": i, "destinos": ["Kioto, Japón"], "fecha_inicio": "2030-03-10",
         "fecha_fin": "2030-03-12", "costo_total_estimado": 900.0, "estado": "draft",
         "group_id": "g", "imagen": None, "created_at": None, "tipo_viaje": tipo}
        for i, tipo in enumerate(["Economy", "Balanced", "Luxury"], start=1)
    ]


def test_compare_avisa_que_el_presupuesto_no_alcanza(logueado, backend):
    backend.drafts = _tres_borradores()
    with logueado.session_transaction() as sesion:
        sesion["presupuesto"] = {
            "estado": "presupuesto_insuficiente",
            "aviso": {"presupuesto_solicitado": 100, "costo_minimo_estimado": 9256,
                      "dias_que_entran": 0, "alcanza_para_el_vuelo": False,
                      "mensaje": "Con $100 no alcanza ni para el vuelo.",
                      "sugerencias": ["Subí el presupuesto", "Acortá el viaje"]},
        }

    html = logueado.get("/compare").get_data(as_text=True)

    assert "budget_short_title" in html
    assert "Con $100 no alcanza ni para el vuelo." in html
    assert "Acortá el viaje" in html
    # `0` y `False` son datos válidos: no se pueden esconder por ser falsy.
    assert "budget_days_fit" in html
    assert "budget_covers_flight" in html
    # Las 3 opciones vienen igual, así que se siguen ofreciendo.
    assert "budget_cheapest" in html
    assert "compare_plan_eco" in html


def test_compare_avisa_que_el_viaje_se_ajusto(logueado, backend):
    backend.drafts = _tres_borradores()
    with logueado.session_transaction() as sesion:
        sesion["presupuesto"] = {"estado": "ajustado",
                                 "aviso": {"mensaje": "Recortamos a 3 días."}}

    html = logueado.get("/compare").get_data(as_text=True)

    assert "budget_tight_title" in html
    assert "Recortamos a 3 días." in html
    assert "budget_cheapest" not in html   # el viaje entra: no hay que disculparse
    # El aviso sólo trae `mensaje`; el resto de las claves no puede aparecer vacío.
    assert "budget_days_fit" not in html
    assert "budget_minimum" not in html


def test_compare_sin_aviso_no_dibuja_el_cartel(logueado, backend):
    backend.drafts = _tres_borradores()

    html = logueado.get("/compare").get_data(as_text=True)

    assert "budget_short_title" not in html
    assert "budget_tight_title" not in html


# ─── Procedencia de los precios ──────────────────────────────────────────────

def test_fuentes_por_rubro_acepta_los_nombres_del_flujo(app):
    """El flujo nombra `vuelos`/`hoteles`, no `transporte`/`alojamiento`."""
    import app as modulo

    fuentes = modulo._fuentes_por_rubro({"fuente_datos": {"fuentes": {
        "vuelos": "Aviasales", "hoteles": "Hotellook", "comidas": "estimado"}}})

    assert fuentes == {"transporte": "Aviasales", "alojamiento": "Hotellook",
                       "comidas": "estimado"}


def test_fuentes_por_rubro_tolera_que_no_venga_nada(app):
    import app as modulo

    assert modulo._fuentes_por_rubro({}) == {}
    assert modulo._fuentes_por_rubro({"fuente_datos": "Aviasales"}) == {}
    assert modulo._fuentes_por_rubro({"fuente_datos": {"fuentes": []}}) == {}


def test_itinerario_muestra_el_origen_del_precio(logueado, backend):
    """El origen se muestra sólo en los rubros cotizados, no en los estimados."""
    backend.extra_viaje = {"fuente_datos": {"fuentes": {
        "actividades": "Google Places",   # el viaje tiene actividades reales
        "vuelos": "Aviasales",            # sin vuelos ese día: queda estimado
    }}}

    html = logueado.get("/itinerary/1").get_data(as_text=True)

    assert "Google Places" in html
    assert "Aviasales" not in html


def test_itinerario_muestra_link_nota_y_precio_dudoso(logueado, backend):
    base = backend.responder("GET", "/viajes/1")
    detalle = {**base}
    detalle["itinerarios"] = [{
        **base["itinerarios"][0],
        "actividades": [{
            **base["itinerarios"][0]["actividades"][0],
            "categoria": "Vuelo",
            "link": "https://aviasales.com/oferta-42",
            "nota": "Tarifa con una escala en Doha.",
            "precio_sospechoso": True,
        }],
    }]
    backend.extra_viaje = detalle

    html = logueado.get("/itinerary/1").get_data(as_text=True)

    assert "https://aviasales.com/oferta-42" in html
    assert "Tarifa con una escala en Doha." in html
    assert "act_price_odd" in html
    assert "act_see_flight" in html


def test_itinerario_sin_procedencia_no_dibuja_nada(logueado, backend):
    html = logueado.get("/itinerary/1").get_data(as_text=True)

    assert "act_see_flight" not in html
    assert "act_price_odd" not in html


# ─── Fotos de Google Places ──────────────────────────────────────────────────

def test_la_foto_del_lugar_pasa_por_el_proxy(logueado, backend):
    """La URL firmada de Google lleva la API key: no puede llegar al HTML."""
    base = backend.responder("GET", "/viajes/1")
    detalle = {**base}
    detalle["itinerarios"] = [{
        **base["itinerarios"][0],
        "actividades": [{
            **base["itinerarios"][0]["actividades"][0],
            "imagen_ref": "places/P1/photos/AF9",
            "rating": 4.7, "opiniones": 90000,
            "mapa": "https://maps.google.com/?cid=9",
            "web": "https://ejemplo.com",
            "lat": 28.41, "lng": -81.58,
        }],
    }]
    backend.extra_viaje = detalle

    html = logueado.get("/itinerary/1").get_data(as_text=True)

    assert "/place-photo?ref=places" in html
    assert "places.googleapis.com" not in html   # jamás la URL con la key
    assert "4.7" in html and "90,000" in html
    assert "act_open_maps" in html and "act_website" in html
    assert 'data-lat="28.41"' in html


def test_el_proxy_de_fotos_rechaza_referencias_inventadas(logueado, monkeypatch):
    """Sin validar el `ref`, la ruta sería un proxy abierto con nuestra clave."""
    import app as modulo
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "clave-de-test")

    def no_llamar(*args, **kwargs):
        raise AssertionError("no se debería salir a la red con un ref inválido")

    monkeypatch.setattr(modulo.requests, "get", no_llamar)

    for ref in ["", "../../etc/passwd", "https://evil.example.com/x",
                "places/P1/photos/AF9/../../..", "otracosa/P1/photos/AF9",
                "places/P1 P2/photos/AF9", "places//photos/AF9"]:
        assert logueado.get("/place-photo", query_string={"ref": ref}).status_code == 404


def test_el_proxy_de_fotos_no_rompe_sin_clave(logueado, monkeypatch):
    """Sin clave configurada la tarjeta usa el fondo por categoría, no un 500."""
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "")

    respuesta = logueado.get("/place-photo",
                             query_string={"ref": "places/P1/photos/AF9"})

    assert respuesta.status_code == 404


def test_el_proxy_de_fotos_requiere_sesion(client):
    respuesta = client.get("/place-photo", query_string={"ref": "places/P1/photos/AF9"})

    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


# ─── Caché de fotos y referencias reales ─────────────────────────────────────

REF_REAL = ("places/ChIJd5jmZ1JrcRcRQl_4xTdQFZo/photos/"
            + "A" * 258)   # los ids de foto de Google rondan los 258 caracteres


def test_el_proxy_acepta_las_referencias_reales_de_google(logueado, monkeypatch, tmp_path):
    """El límite viejo era 200 y rechazaba TODAS: por eso no se veía ninguna foto."""
    import app as modulo
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "clave-de-test")
    monkeypatch.setattr(modulo, "CACHE_DE_FOTOS", tmp_path / "fotos")

    class RespuestaFalsa:
        status_code = 200
        headers = {"Content-Type": "image/jpeg"}
        content = b"\xff\xd8\xff-una-foto"

    monkeypatch.setattr(modulo.requests, "get", lambda *a, **k: RespuestaFalsa())

    respuesta = logueado.get("/place-photo", query_string={"ref": REF_REAL})

    assert respuesta.status_code == 200
    assert respuesta.data == b"\xff\xd8\xff-una-foto"


def test_la_foto_se_baja_una_sola_vez(logueado, monkeypatch, tmp_path):
    """Google factura cuando el navegador carga la foto, no cuando n8n la arma."""
    import app as modulo
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "clave-de-test")
    monkeypatch.setattr(modulo, "CACHE_DE_FOTOS", tmp_path / "fotos")

    llamadas = []

    class RespuestaFalsa:
        status_code = 200
        headers = {"Content-Type": "image/jpeg"}
        content = b"\xff\xd8\xff-una-foto"

    def falso_get(*args, **kwargs):
        llamadas.append(args)
        return RespuestaFalsa()

    monkeypatch.setattr(modulo.requests, "get", falso_get)

    for _ in range(3):
        respuesta = logueado.get("/place-photo", query_string={"ref": REF_REAL})
        assert respuesta.status_code == 200
        assert respuesta.data == b"\xff\xd8\xff-una-foto"

    assert len(llamadas) == 1, "la segunda visita volvió a facturarle a Google"


def test_una_foto_cacheada_no_necesita_la_clave(logueado, monkeypatch, tmp_path):
    """Si alguien borra la key del .env, lo ya bajado se sigue viendo."""
    import app as modulo
    monkeypatch.setattr(modulo, "CACHE_DE_FOTOS", tmp_path / "fotos")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "clave-de-test")

    class RespuestaFalsa:
        status_code = 200
        headers = {"Content-Type": "image/jpeg"}
        content = b"\xff\xd8\xff-una-foto"

    monkeypatch.setattr(modulo.requests, "get", lambda *a, **k: RespuestaFalsa())
    logueado.get("/place-photo", query_string={"ref": REF_REAL})

    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "")

    def no_llamar(*args, **kwargs):
        raise AssertionError("estaba en disco: no hacía falta salir a la red")

    monkeypatch.setattr(modulo.requests, "get", no_llamar)

    assert logueado.get("/place-photo", query_string={"ref": REF_REAL}).status_code == 200


# ─── Sugerencias del presupuesto ─────────────────────────────────────────────

AVISO_CON_CODIGOS = {
    "presupuesto_solicitado": 4000, "costo_minimo_estimado": 4772,
    "costo_fijo_transporte": 3800, "presupuesto_restante_tras_vuelo": 200,
    "costo_por_dia": 121.5, "dias_solicitados": 8, "dias_que_entran": 1,
    "alcanza_para_el_vuelo": True,
    "mensaje": "No alcanza.",
    "sugerencias": ["El vuelo se come casi todo", "Subí el presupuesto"],
    "sugerencias_codigos": [
        {"codigo": "vuelo_come_casi_todo", "vuelo": 3800, "presupuesto": 4000,
         "restante": 200, "dias": 1, "dias_pedidos": 8},
        {"codigo": "subir_presupuesto", "minimo": 4772, "faltante": 772, "dias": 8},
    ],
}


def test_el_cartel_arma_las_sugerencias_con_la_i18n_propia(logueado, backend):
    backend.drafts = _tres_borradores()
    with logueado.session_transaction() as sesion:
        sesion["presupuesto"] = {"estado": "presupuesto_insuficiente",
                                 "aviso": AVISO_CON_CODIGOS}

    html = logueado.get("/compare").get_data(as_text=True)

    assert "budget_tip_flight_eats_it" in html
    assert "budget_tip_raise" in html
    # Los números viajan como parámetros para que los interpole la traducción.
    assert "&#34;vuelo&#34;: &#34;3,800&#34;" in html or '"vuelo": "3,800"' in html
    # El texto del flujo queda como respaldo hasta que carga el idioma.
    assert "Sub" in html and "presupuesto" in html


def test_el_cartel_explica_por_que_entra_un_solo_dia(logueado, backend):
    """'1 de 8 días' leído solo parece un error: falta decir qué se lleva el vuelo."""
    backend.drafts = _tres_borradores()
    with logueado.session_transaction() as sesion:
        sesion["presupuesto"] = {"estado": "presupuesto_insuficiente",
                                 "aviso": AVISO_CON_CODIGOS}

    html = logueado.get("/compare").get_data(as_text=True)

    assert "budget_breakdown" in html and "budget_per_day" in html
    assert "$3,800" in html and "$122" in html
    assert "budget_left_after_flight" in html and "$200" in html
    assert "/ 8" in html          # 1 de 8 días


def test_un_codigo_desconocido_se_muestra_con_el_texto_del_flujo(logueado, backend):
    backend.drafts = _tres_borradores()
    with logueado.session_transaction() as sesion:
        sesion["presupuesto"] = {"estado": "ajustado", "aviso": {
            "mensaje": "Se ajustó.",
            "sugerencias": ["Probá con otra aerolínea"],
            "sugerencias_codigos": [{"codigo": "algo_que_no_existe_todavia"}],
        }}

    html = logueado.get("/compare").get_data(as_text=True)

    assert "Probá con otra aerolínea" in html


def test_el_pintor_de_iconos_no_borra_la_foto_del_lugar():
    """La foto vive dentro de `.activity-icon-wrapper`, que el JS reescribe.

    `pintarIconos()` pisa el innerHTML del contenedor para poner el icono de
    categoría. Como la foto es hija de ese mismo nodo, se borraba apenas
    cargaba la página: el dato y el proxy estaban bien y aun así no se veía
    nada. Si alguien vuelve a escribir ese innerHTML sin rescatarla, esto falla.
    """
    from pathlib import Path

    plantilla = Path(__file__).resolve().parent.parent / "templates" / "itinerary.html"
    cuerpo = plantilla.read_text(encoding="utf-8")

    inicio = cuerpo.index("function pintarIconos()")
    fin = cuerpo.index("\n  }", inicio)
    funcion = cuerpo[inicio:fin]

    assert "innerHTML" in funcion, "cambió la función: revisar este test"
    assert "querySelector('.foto-lugar')" in funcion
    assert "appendChild(foto)" in funcion


def test_el_mapa_descarta_puntos_lejos_del_destino():
    """El sesgo de Photon es una sugerencia, no un filtro.

    Con una ubicación genérica ("mercado local") puede devolver un homónimo de
    otro país, y en un viaje a Punta Cana aparecía un marcador en Europa. Un
    punto falso es peor que ninguno.
    """
    from pathlib import Path

    plantilla = Path(__file__).resolve().parent.parent / "templates" / "itinerary.html"
    cuerpo = plantilla.read_text(encoding="utf-8")

    assert "KM_MAXIMOS_DEL_DESTINO" in cuerpo
    assert "function kmEntre" in cuerpo
    # Y el filtro tiene que estar aplicado, no sólo definido.
    assert "kmEntre(coords, sesgo) > KM_MAXIMOS_DEL_DESTINO" in cuerpo


# ─── Procedencia del precio ──────────────────────────────────────────────────

def _viaje_con_actividad(backend, **campos):
    base = backend.responder("GET", "/viajes/1")
    detalle = {**base}
    detalle["itinerarios"] = [{
        **base["itinerarios"][0],
        "actividades": [{**base["itinerarios"][0]["actividades"][0], **campos}],
    }]
    backend.extra_viaje = detalle
    return detalle


def test_un_precio_consultado_a_google_se_muestra_como_tal(logueado, backend):
    _viaje_con_actividad(backend, precio_estimado=35.0,
                         precio_fuente="google_price_range",
                         precio_desde=25.0, precio_hasta=50.0, precio_moneda="USD")

    html = logueado.get("/itinerary/1").get_data(as_text=True)

    assert "act_price_from_google" in html
    assert "USD 25–50" in html
    assert "act_price_approx" not in html
    assert "act_price_from_ai" not in html


def test_un_precio_estimado_no_se_hace_pasar_por_consultado(logueado, backend):
    """El lugar es real; el precio, cuando lo estimó un modelo, no es un dato."""
    _viaje_con_actividad(backend, precio_estimado=35.0, precio_fuente="tasacion_ia")

    html = logueado.get("/itinerary/1").get_data(as_text=True)

    assert "act_price_approx" in html
    assert "act_price_from_ai" in html
    assert "act_price_from_google" not in html


def test_sin_procedencia_el_precio_se_muestra_a_secas(logueado, backend):
    """Los viajes viejos no tienen el campo: no pueden quedar mal etiquetados."""
    _viaje_con_actividad(backend, precio_estimado=35.0, precio_fuente=None)

    html = logueado.get("/itinerary/1").get_data(as_text=True)

    assert "act_price_from_google" not in html
    assert "act_price_from_ai" not in html
    assert "$35" in html


def test_el_campo_de_texto_libre_llega_entero_a_n8n(logueado, backend, csrf, monkeypatch):
    """De ahí salen el reparto de días por ciudad y la búsqueda por intereses.

    Si se recortara o se perdiera en el camino, el flujo repartiría los días en
    partes iguales sin que nadie se entere de por qué.
    """
    import trip_generator

    capturado = {}

    def espiar(preferencias, idioma="en"):
        capturado.update(preferencias)
        return None    # sin webhook: sigue con el generador local

    monkeypatch.setattr(trip_generator, "_generar_con_n8n", espiar)

    texto = ("5 días en Miami y 3 en Nueva York, nos gusta el trekking y la "
             "comida vegana, no queremos madrugar")
    respuesta = logueado.post("/create_trip", json={
        "destinos": ["Miami, United States", "New York, United States"],
        "fecha_inicio": "2030-03-10", "fecha_fin": "2030-03-17",
        "costo_max": 4000, "cantidad_personas": 2, "otros": texto,
    }, headers=csrf)

    assert respuesta.status_code == 200, respuesta.get_data(as_text=True)
    assert capturado.get("otros") == texto


def test_el_formulario_explica_para_que_sirve_el_texto_libre():
    """El campo dejó de ser decorativo, pero eso no se puede adivinar."""
    from pathlib import Path

    plantilla = Path(__file__).resolve().parent.parent / "templates" / "index.html"
    cuerpo = plantilla.read_text(encoding="utf-8")

    assert 'data-i18n="index_extras_hint"' in cuerpo
    assert "5 days in Miami" in cuerpo     # el formato que el flujo reconoce


def test_el_mapa_dibuja_el_recorrido_del_dia():
    """El orden de las actividades es una ruta resuelta: se puede mostrar."""
    from pathlib import Path

    plantilla = Path(__file__).resolve().parent.parent / "templates" / "itinerary.html"
    cuerpo = plantilla.read_text(encoding="utf-8")

    assert "function dibujarRecorridoDelDia" in cuerpo
    assert "dibujarRecorridoDelDia();" in cuerpo      # y está llamada
    assert "L.polyline(puntosDelDiaActual" in cuerpo
