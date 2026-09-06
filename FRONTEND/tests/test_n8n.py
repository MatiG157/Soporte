"""El flujo de n8n es el único proveedor de IA: contrato, fallos y respaldo."""

import json

import pytest

import trip_generator


PREFERENCIAS = {
    "destinos": ["Kioto, Japón"],
    "origen": "Córdoba, Argentina",
    "fecha_inicio": "2030-03-10",
    "fecha_fin": "2030-03-14",
    "cantidad_personas": 2,
    "costo_max": 3000,
    "act_preferidas": "cultural",
}


def _opcion(tipo, dias=5):
    return {
        "destinos": ["Kioto, Japón"],
        "fecha_inicio": "2030-03-10",
        "fecha_fin": "2030-03-14",
        "tipo": tipo,
        "costo_total_estimado": 2000.0,
        "imagen": "https://example.com/kioto.jpg",
        "desglose_costos": {
            "costo_alojamiento": 700.0,
            "costo_transporte": 600.0,
            "costo_actividades": 400.0,
            "costo_comidas": 300.0,
        },
        "itinerario": [
            {
                "dia": dia,
                "resumen": f"Día {dia}",
                "actividades": [{
                    "nombre": f"Templo {dia}",
                    "descripcion": "Visita guiada",
                    "precio_estimado": 20.0,
                    "categoria": "Cultural",
                    "horario_sugerido": "10:00 - 12:00",
                    "ubicacion": "Kioto",
                }],
            } for dia in range(1, dias + 1)
        ],
    }


class RespuestaFalsa:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def n8n(monkeypatch):
    """Configura N8N_WEBHOOK_URL y captura lo que se le manda al webhook."""
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/webhook/generate-trips")
    monkeypatch.setenv("N8N_TOKEN", "token-secreto")
    monkeypatch.delenv("N8N_BASIC_USER", raising=False)
    monkeypatch.setattr(trip_generator, "obtener_imagen_destino", lambda destino: None)

    capturado = {}

    def falso_post(url, json=None, headers=None, auth=None, timeout=None):
        capturado["url"] = url
        capturado["body"] = json
        capturado["headers"] = headers
        capturado["auth"] = auth
        return capturado["respuesta"]

    monkeypatch.setattr(trip_generator.requests, "post", falso_post)
    return capturado


def test_usa_n8n_cuando_esta_configurado(n8n):
    n8n["respuesta"] = RespuestaFalsa([_opcion(t) for t in ("Economy", "Balanced", "Luxury")])

    opciones, proveedor, _ = trip_generator.generar_opciones(PREFERENCIAS)

    assert proveedor == "n8n"
    assert len(opciones) == 3
    assert {o["tipo"] for o in opciones} == {"Economy", "Balanced", "Luxury"}


def test_manda_el_token_y_la_cantidad_de_dias(n8n):
    n8n["respuesta"] = RespuestaFalsa([_opcion(t) for t in ("Economy", "Balanced", "Luxury")])

    trip_generator.generar_opciones(PREFERENCIAS)

    assert n8n["headers"]["X-N8N-TOKEN"] == "token-secreto"
    assert n8n["body"]["cantidad_dias"] == 5
    assert n8n["body"]["destinos"] == ["Kioto, Japón"]


def test_usa_basic_auth_cuando_esta_configurado(n8n, monkeypatch):
    """El nodo Webhook de n8n puede pedir Basic Auth en vez de un header."""
    monkeypatch.setenv("N8N_BASIC_USER", "pepe")
    monkeypatch.setenv("N8N_BASIC_PASSWORD", "secreta")
    n8n["respuesta"] = RespuestaFalsa([_opcion(t) for t in ("Economy", "Balanced", "Luxury")])

    _, proveedor, _ = trip_generator.generar_opciones(PREFERENCIAS)

    assert proveedor == "n8n"
    assert n8n["auth"] == ("pepe", "secreta")
    # Con Basic no se manda el header del token.
    assert "X-N8N-TOKEN" not in n8n["headers"]


def test_header_configurable(n8n, monkeypatch):
    """N8N_HEADER se adapta al campo `Name` de la credencial Header Auth."""
    monkeypatch.setenv("N8N_HEADER", "X-API-KEY")
    n8n["respuesta"] = RespuestaFalsa([_opcion(t) for t in ("Economy", "Balanced", "Luxury")])

    trip_generator.generar_opciones(PREFERENCIAS)

    assert n8n["headers"]["X-API-KEY"] == "token-secreto"
    assert n8n["auth"] is None


def test_lee_el_estado_del_presupuesto(n8n):
    """El flujo pasó a devolver {estado, opciones, aviso_presupuesto}."""
    aviso = {"presupuesto_solicitado": 100, "costo_minimo_estimado": 9256,
             "dias_que_entran": 0, "mensaje": "No alcanza."}
    n8n["respuesta"] = RespuestaFalsa({
        "estado": "presupuesto_insuficiente",
        "opciones": [_opcion(t) for t in ("Economy", "Balanced", "Luxury")],
        "aviso_presupuesto": aviso,
    })

    opciones, proveedor, presupuesto = trip_generator.generar_opciones(PREFERENCIAS)

    assert proveedor == "n8n"
    assert len(opciones) == 3          # las opciones vienen igual
    assert presupuesto["estado"] == "presupuesto_insuficiente"
    assert presupuesto["aviso"]["dias_que_entran"] == 0


def test_un_array_pelado_sigue_siendo_valido(n8n):
    """La forma vieja (array sin sobre) no puede romper."""
    n8n["respuesta"] = RespuestaFalsa([_opcion(t) for t in ("Economy", "Balanced", "Luxury")])

    _, proveedor, presupuesto = trip_generator.generar_opciones(PREFERENCIAS)

    assert proveedor == "n8n"
    assert presupuesto == {"estado": "ok", "aviso": None}


def test_conserva_el_indice_de_destino_de_cada_dia(n8n):
    """Sin `destino_indice` el backend cuelga todo del primer destino."""
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        for indice, dia in enumerate(opcion["itinerario"]):
            dia["destino_indice"] = 0 if indice < 2 else 1
            dia["destino"] = "Osaka" if indice < 2 else "Kioto"

    validadas = trip_generator.validar_opciones(opciones, PREFERENCIAS)
    dias = validadas[0]["itinerario"]

    assert [d["destino_indice"] for d in dias] == [0, 0, 1, 1, 1]
    assert dias[4]["destino"] == "Kioto"


def test_acepta_la_respuesta_envuelta_en_un_objeto(n8n):
    n8n["respuesta"] = RespuestaFalsa(
        {"data": [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]}
    )

    _, proveedor, _ = trip_generator.generar_opciones(PREFERENCIAS)
    assert proveedor == "n8n"


def test_cae_al_generador_local_si_n8n_devuelve_error(n8n):
    n8n["respuesta"] = RespuestaFalsa({"error": "algo explotó"}, status=502)

    opciones, proveedor, _ = trip_generator.generar_opciones(PREFERENCIAS)

    assert proveedor == "local"
    assert len(opciones) == 3


def test_cae_al_generador_local_si_faltan_tipos(n8n):
    n8n["respuesta"] = RespuestaFalsa([_opcion("Economy"), _opcion("Balanced")])

    _, proveedor, _ = trip_generator.generar_opciones(PREFERENCIAS)
    assert proveedor == "local"


def test_cae_al_generador_local_si_un_dia_no_trae_actividades(n8n):
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    opciones[0]["itinerario"][2]["actividades"] = []
    n8n["respuesta"] = RespuestaFalsa(opciones)

    _, proveedor, _ = trip_generator.generar_opciones(PREFERENCIAS)
    assert proveedor == "local"


def test_sin_webhook_configurado_usa_el_generador_local(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "")
    monkeypatch.setattr(trip_generator, "obtener_imagen_destino", lambda destino: None)

    opciones, proveedor, _ = trip_generator.generar_opciones(PREFERENCIAS)

    assert proveedor == "local"
    assert len(opciones) == 3
    # El generador local respeta los días reales (10 al 14 de marzo = 5).
    assert all(len(o["itinerario"]) == 5 for o in opciones)


# ─── Validación del contrato ─────────────────────────────────────────────────

def test_recorta_los_textos_a_los_limites_de_columna():
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    opciones[0]["itinerario"][0]["actividades"][0].update({
        "nombre": "N" * 300,
        "categoria": "C" * 200,
        "horario_sugerido": "H" * 90,
        "ubicacion": "U" * 400,
    })

    validadas = trip_generator.validar_opciones(opciones, PREFERENCIAS)
    actividad = validadas[0]["itinerario"][0]["actividades"][0]

    assert len(actividad["nombre"]) == 120
    assert len(actividad["categoria"]) == 80
    assert len(actividad["horario_sugerido"]) == 30
    assert len(actividad["ubicacion"]) == 150


def test_limpia_el_markdown_de_la_respuesta():
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    crudo = "```json\n" + json.dumps(opciones) + "\n```"

    validadas = trip_generator.validar_opciones(crudo, PREFERENCIAS)
    assert len(validadas) == 3


def test_las_fechas_y_destinos_los_impone_el_usuario():
    """La IA no puede cambiar a dónde ni cuándo viaja el usuario."""
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        opcion["destinos"] = ["Otra ciudad inventada"]
        opcion["fecha_inicio"] = "1999-01-01"

    validadas = trip_generator.validar_opciones(opciones, PREFERENCIAS)

    assert all(o["destinos"] == ["Kioto, Japón"] for o in validadas)
    assert all(o["fecha_inicio"] == "2030-03-10" for o in validadas)


def test_conserva_los_campos_extra_del_flujo():
    """`fuente_datos` (trazabilidad de precios) tiene que llegar al backend."""
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        opcion["fuente_datos"] = {
            "fuentes": {"vuelo": "amadeus", "alojamiento": "amadeus"},
            "vuelo": {"ruta": "COR - KIX - COR", "precio_grupo": 1840.0},
        }

    validadas = trip_generator.validar_opciones(opciones, PREFERENCIAS)

    assert all("fuente_datos" in o for o in validadas)
    assert validadas[0]["fuente_datos"]["vuelo"]["precio_grupo"] == 1840.0


def test_renumera_los_dias_de_forma_correlativa():
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for indice, dia in enumerate(opciones[0]["itinerario"]):
        dia["dia"] = 99 - indice  # la IA numeró cualquier cosa

    validadas = trip_generator.validar_opciones(opciones, PREFERENCIAS)
    assert [d["dia"] for d in validadas[0]["itinerario"]] == [1, 2, 3, 4, 5]


def test_recorta_si_la_ia_devuelve_mas_dias_de_los_pedidos():
    opciones = [_opcion(t, dias=12) for t in ("Economy", "Balanced", "Luxury")]

    validadas = trip_generator.validar_opciones(opciones, PREFERENCIAS)
    assert all(len(o["itinerario"]) == 5 for o in validadas)


@pytest.mark.parametrize("respuesta", [
    [],
    [1, 2, 3],
    {"sin": "nada útil"},
])
def test_rechaza_respuestas_que_no_cumplen_el_contrato(respuesta):
    with pytest.raises((ValueError, AttributeError, TypeError)):
        trip_generator.validar_opciones(respuesta, PREFERENCIAS)


def test_el_generador_local_respeta_las_actividades_preferidas():
    preferencias = dict(PREFERENCIAS, act_preferidas="adventure")
    opciones = trip_generator.generar_localmente(preferencias)

    categorias = {
        act["categoria"]
        for opcion in opciones
        for dia in opcion["itinerario"]
        for act in dia["actividades"]
    }
    assert "Aventura" in categorias


def test_el_generador_local_escala_con_el_presupuesto():
    baratas = trip_generator.generar_localmente(dict(PREFERENCIAS, costo_max=1000))
    caras = trip_generator.generar_localmente(dict(PREFERENCIAS, costo_max=8000))

    por_tipo = lambda ops: {o["tipo"]: o["costo_total_estimado"] for o in ops}

    assert por_tipo(caras)["Economy"] > por_tipo(baratas)["Economy"]
    # Dentro de una misma corrida, Economy < Balanced < Luxury.
    totales = por_tipo(caras)
    assert totales["Economy"] < totales["Balanced"] < totales["Luxury"]


def test_la_actividad_no_conserva_la_url_firmada_de_google(n8n):
    """Esa URL lleva la API key: se guarda la referencia, no la URL."""
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        opcion["itinerario"][0]["actividades"][0].update({
            "imagen": "https://places.googleapis.com/v1/places/P1/photos/AF9/media?key=SECRETA",
            "imagen_ref": "places/P1/photos/AF9",
            "rating": 4.7, "opiniones": 90000, "lat": 28.41, "lng": -81.58,
        })

    actividad = trip_generator.validar_opciones(opciones, PREFERENCIAS)[0]["itinerario"][0]["actividades"][0]

    assert actividad["imagen_ref"] == "places/P1/photos/AF9"
    assert "imagen" not in actividad
    assert actividad["rating"] == 4.7
    assert actividad["lat"] == 28.41


def test_sin_datos_de_google_el_rating_queda_en_nada(n8n):
    """Un lugar sin rating no tiene rating: 0 sería inventar 0 estrellas."""
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]

    actividad = trip_generator.validar_opciones(opciones, PREFERENCIAS)[0]["itinerario"][0]["actividades"][0]

    assert actividad["rating"] is None
    assert actividad["lat"] is None
    assert actividad["imagen_ref"] == ""


def test_el_link_del_vuelo_va_al_tramo_que_describe(n8n):
    """`fuente_datos.vuelo` describe el internacional, no cada traslado."""
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        opcion["itinerario"][0]["actividades"][0]["categoria"] = "Vuelo"
        opcion["itinerario"][1]["actividades"][0]["categoria"] = "Transporte"
        opcion["fuente_datos"] = {"vuelo": {
            "link": "https://www.aviasales.com/search/ROS0812MIA1",
            "nota": "Precio de otra fecha de la misma ruta.",
            "precio_sospechoso": True,
        }}

    dias = trip_generator.validar_opciones(opciones, PREFERENCIAS)[0]["itinerario"]

    primero = dias[0]["actividades"][0]
    segundo = dias[1]["actividades"][0]
    assert primero["link"].endswith("ROS0812MIA1")
    assert primero["precio_sospechoso"] is True
    # El tramo intermedio se cotiza aparte: copiarle la nota sería mentir.
    assert segundo["link"] == ""
    assert segundo["precio_sospechoso"] is False


def test_el_estado_del_presupuesto_se_lee_de_la_opcion_si_falta_arriba(n8n):
    """El flujo repite el aviso dentro de cada opción por si se pierde."""
    aviso = {"mensaje": "No alcanza.", "dias_que_entran": 4}
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    opciones[0]["fuente_datos"] = {"estado_presupuesto": "ajustado",
                                   "aviso_presupuesto": aviso}
    n8n["respuesta"] = RespuestaFalsa({"opciones": opciones})

    _, _, presupuesto = trip_generator.generar_opciones(PREFERENCIAS)

    assert presupuesto["estado"] == "ajustado"
    assert presupuesto["aviso"]["dias_que_entran"] == 4


def test_la_referencia_de_foto_entra_entera(n8n):
    """Medida contra el flujo real: llegan a 494 caracteres.

    El tope viejo de 300 le cortaba casi 200 a cada una, y una referencia
    cortada es un 404 seguro en Google. Ése era el motivo de que las tarjetas
    mostraran el degradé en vez de la foto.
    """
    referencia = "places/" + "C" * 27 + "/photos/" + "A" * 452
    assert len(referencia) == 494

    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        opcion["itinerario"][0]["actividades"][0]["imagen_ref"] = referencia

    guardada = trip_generator.validar_opciones(
        opciones, PREFERENCIAS)[0]["itinerario"][0]["actividades"][0]["imagen_ref"]

    assert guardada == referencia

    # Y el proxy tiene que aceptarla, que es donde se rompía antes.
    import app
    assert app.REFERENCIA_DE_FOTO.match(guardada)


def test_registra_cuantas_actividades_encontraron_ficha(n8n, caplog):
    """Si la cobertura se desploma, tiene que verse en el log y no de a una."""
    import logging

    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        opcion["itinerario"][0]["actividades"][0]["imagen_ref"] = (
            "places/" + "C" * 27 + "/photos/" + "A" * 452)
    n8n["respuesta"] = RespuestaFalsa(opciones)

    with caplog.at_level(logging.INFO, logger="trip_generator"):
        trip_generator.generar_opciones(PREFERENCIAS)

    lineas = [r.getMessage() for r in caplog.records]
    assert any("Google Places: 3 de 15 actividades con ficha (20%)" in l for l in lineas), lineas


def test_conserva_de_donde_salio_el_precio(n8n):
    """Un precio del `priceRange` de Google no es lo mismo que uno estimado."""
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        actividades = opcion["itinerario"][0]["actividades"]
        actividades[0].update({
            "precio_fuente": "google_price_range",
            "precio_rango": {"desde": 25, "hasta": 50, "moneda": "USD"},
        })

    dia = trip_generator.validar_opciones(opciones, PREFERENCIAS)[0]["itinerario"][0]
    actividad = dia["actividades"][0]

    assert actividad["precio_fuente"] == "google_price_range"
    assert actividad["precio_rango"] == {"desde": 25.0, "hasta": 50.0, "moneda": "USD"}


def test_sin_rango_no_se_inventa_uno(n8n):
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        opcion["itinerario"][0]["actividades"][0]["precio_fuente"] = "tasacion_ia"

    actividad = trip_generator.validar_opciones(
        opciones, PREFERENCIAS)[0]["itinerario"][0]["actividades"][0]

    assert actividad["precio_fuente"] == "tasacion_ia"
    assert actividad["precio_rango"] is None


def test_respeta_el_recorrido_que_arma_el_flujo(n8n):
    """El orden del array es la ruta optimizada, no un orden cualquiera.

    El flujo agrupa por zonas y resuelve la ruta desde el hotel. Reordenar por
    hora rompía eso en cuanto dos actividades compartían horario o una hora no
    parseaba.
    """
    def actividad(nombre, horario):
        return {"nombre": nombre, "descripcion": "", "precio_estimado": 10,
                "categoria": "Cultural", "horario_sugerido": horario,
                "ubicacion": "Kioto"}

    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        # Dos a la misma hora: ahí es donde ordenar por hora rompía la ruta.
        opcion["itinerario"][0]["actividades"] = [
            actividad("Zona norte A", "10:00 - 12:00"),
            actividad("Zona norte B", "10:00 - 12:00"),
            actividad("Zona norte C", "14:00 - 16:00"),
        ]

    dia = trip_generator.validar_opciones(opciones, PREFERENCIAS)[0]["itinerario"][0]
    nombres = [a["nombre"] for a in dia["actividades"]]

    assert nombres == ["Zona norte A", "Zona norte B", "Zona norte C"]


def test_ordena_igual_cuando_el_dia_viene_al_reves(n8n):
    """Un flujo viejo, o el generador local, no resuelven ninguna ruta."""
    def actividad(horario):
        return {"nombre": f"Actividad {horario}", "descripcion": "",
                "precio_estimado": 10, "categoria": "Cultural",
                "horario_sugerido": horario, "ubicacion": "Kioto"}

    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    for opcion in opciones:
        opcion["itinerario"][0]["actividades"] = [
            actividad("20:00 - 22:00"), actividad("09:00 - 11:00"),
            actividad("14:00 - 16:00"),
        ]

    dia = trip_generator.validar_opciones(opciones, PREFERENCIAS)[0]["itinerario"][0]
    horas = [a["horario_sugerido"] for a in dia["actividades"]]

    assert horas == ["09:00 - 11:00", "14:00 - 16:00", "20:00 - 22:00"]
