"""CSRF, sesión y validaciones del formulario de creación de viajes."""


def _payload(**extra):
    base = {
        "destinos": ["Kioto, Japón"],
        "origen": "Córdoba, Argentina",
        "fecha_inicio": "2030-03-10",
        "fecha_fin": "2030-03-14",
        "cantidad_personas": 2,
        "costo_min": 1000,
        "costo_max": 3000,
        "grupo": "family",
        "act_preferidas": "cultural",
    }
    base.update(extra)
    return base


def test_post_sin_token_csrf_es_rechazado(logueado):
    respuesta = logueado.post("/create_trip", json=_payload())
    assert respuesta.status_code == 400


def test_post_con_token_invalido_es_rechazado(logueado):
    respuesta = logueado.post("/create_trip", json=_payload(),
                              headers={"X-CSRF-Token": "token-equivocado"})
    assert respuesta.status_code == 400


def test_create_trip_sin_sesion_devuelve_401(client):
    respuesta = client.post("/create_trip", json=_payload(),
                            headers={"X-CSRF-Token": "cualquiera"})
    assert respuesta.status_code in (400, 401)


def test_create_trip_completo(logueado, csrf, backend):
    respuesta = logueado.post("/create_trip", json=_payload(), headers=csrf)
    assert respuesta.status_code == 200, respuesta.get_json()

    datos = respuesta.get_json()
    assert datos["redirect"].endswith("/compare")
    # Sin N8N_WEBHOOK_URL configurada, cae al generador local.
    assert datos["proveedor"] == "local"

    generadas = [c for c in backend.llamadas if c[1] == "/viajes/generate"]
    assert len(generadas) == 1

    opciones = generadas[0][2]["opciones"]
    assert len(opciones) == 3
    assert {o["tipo"] for o in opciones} == {"Economy", "Balanced", "Luxury"}
    # 10 al 14 de marzo son 5 días.
    assert all(len(o["itinerario"]) == 5 for o in opciones)


def test_create_trip_valida_destinos(logueado, csrf):
    respuesta = logueado.post("/create_trip", json=_payload(destinos=[]), headers=csrf)
    assert respuesta.status_code == 400


def test_create_trip_valida_orden_de_fechas(logueado, csrf):
    respuesta = logueado.post(
        "/create_trip",
        json=_payload(fecha_inicio="2030-03-20", fecha_fin="2030-03-10"),
        headers=csrf,
    )
    assert respuesta.status_code == 400


def test_create_trip_valida_presupuesto(logueado, csrf):
    respuesta = logueado.post("/create_trip", json=_payload(costo_min=5000, costo_max=1000),
                              headers=csrf)
    assert respuesta.status_code == 400


def test_un_formulario_multipart_recibe_json_no_html(logueado, csrf, backend, monkeypatch):
    """Regresión: el registro por FormData devolvía HTML y tapaba el error real.

    `request.is_json` es False en multipart, así que los handlers respondían
    con una plantilla. El navegador hacía `resp.json()`, fallaba, y mostraba
    "no se pudo conectar" en vez del error de validación del backend.
    """
    import api_client

    def falla_validacion(ruta, **kwargs):
        raise api_client.BackendError(
            "apellido: El apellido debe tener entre 2 y 80 caracteres.", status=400)

    monkeypatch.setattr(api_client, "post", falla_validacion)

    respuesta = logueado.post("/register", content_type="multipart/form-data",
                              headers=csrf,
                              data={"nombre": "Prueba", "apellido": "P",
                                    "email": "x@y.com", "contrasena": "Prueba123",
                                    "csrf_token": "token-de-test"})

    assert respuesta.status_code == 400
    assert respuesta.headers["Content-Type"].startswith("application/json")
    assert "apellido" in respuesta.get_json()["error"]


def test_el_error_de_validacion_nombra_el_campo():
    """Un 'Length must be between 2 and 80' suelto no le sirve a nadie."""
    import api_client

    class RespuestaFalsa:
        status_code = 400
        def json(self):
            return {"errores_validacion": {"apellido": ["Debe tener entre 2 y 80 caracteres."]}}

    mensaje, _ = api_client._mensaje_de_error(RespuestaFalsa())
    assert mensaje.startswith("apellido:")


def test_login_no_redirige_a_sitios_externos(client, backend):
    with client.session_transaction() as sesion:
        sesion["_csrf_token"] = "token-de-test"

    respuesta = client.post("/login", json={
        "email": "test@example.com",
        "contrasena": "DevPass123",
        "next": "https://sitio-malicioso.example/robar",
    }, headers={"X-CSRF-Token": "token-de-test"})

    assert respuesta.status_code == 200
    assert respuesta.get_json()["redirect"] == "/mytrips"


def test_logout_limpia_la_sesion(logueado, csrf):
    respuesta = logueado.post("/logout", headers=csrf)
    assert respuesta.status_code == 302

    with logueado.session_transaction() as sesion:
        assert "user_id" not in sesion


def test_borrar_viaje_requiere_csrf(logueado):
    assert logueado.delete("/trips/1").status_code == 400


def test_borrar_viaje_con_csrf(logueado, csrf, backend):
    respuesta = logueado.delete("/trips/1", headers=csrf)
    assert respuesta.status_code == 200
    assert ("DELETE", "/viajes/1", None) in backend.llamadas


def test_cambiar_idioma_persiste_en_la_sesion(logueado, csrf):
    respuesta = logueado.post("/settings/language", json={"idioma": "ja"}, headers=csrf)
    assert respuesta.status_code == 200

    with logueado.session_transaction() as sesion:
        assert sesion["user_lang"] == "ja"


def test_idioma_no_soportado_es_rechazado(logueado, csrf):
    respuesta = logueado.post("/settings/language", json={"idioma": "xx"}, headers=csrf)
    assert respuesta.status_code == 400
