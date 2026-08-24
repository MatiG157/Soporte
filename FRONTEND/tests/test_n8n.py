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

    opciones, proveedor = trip_generator.generar_opciones(PREFERENCIAS)

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

    _, proveedor = trip_generator.generar_opciones(PREFERENCIAS)

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


def test_acepta_la_respuesta_envuelta_en_un_objeto(n8n):
    n8n["respuesta"] = RespuestaFalsa(
        {"data": [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]}
    )

    _, proveedor = trip_generator.generar_opciones(PREFERENCIAS)
    assert proveedor == "n8n"


def test_cae_al_generador_local_si_n8n_devuelve_error(n8n):
    n8n["respuesta"] = RespuestaFalsa({"error": "algo explotó"}, status=502)

    opciones, proveedor = trip_generator.generar_opciones(PREFERENCIAS)

    assert proveedor == "local"
    assert len(opciones) == 3


def test_cae_al_generador_local_si_faltan_tipos(n8n):
    n8n["respuesta"] = RespuestaFalsa([_opcion("Economy"), _opcion("Balanced")])

    _, proveedor = trip_generator.generar_opciones(PREFERENCIAS)
    assert proveedor == "local"


def test_cae_al_generador_local_si_un_dia_no_trae_actividades(n8n):
    opciones = [_opcion(t) for t in ("Economy", "Balanced", "Luxury")]
    opciones[0]["itinerario"][2]["actividades"] = []
    n8n["respuesta"] = RespuestaFalsa(opciones)

    _, proveedor = trip_generator.generar_opciones(PREFERENCIAS)
    assert proveedor == "local"


def test_sin_webhook_configurado_usa_el_generador_local(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_URL", "")
    monkeypatch.setattr(trip_generator, "obtener_imagen_destino", lambda destino: None)

    opciones, proveedor = trip_generator.generar_opciones(PREFERENCIAS)

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
