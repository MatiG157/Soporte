"""Tests del frontend: se ejecuta la app real con el backend simulado."""

import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

os.environ.setdefault("SECRET_KEY", "clave-de-test")
os.environ.setdefault("BACKEND_API_KEY", "clave-de-test")
os.environ.setdefault("N8N_WEBHOOK_URL", "")  # sin n8n: cae al generador local

VIAJE_GUARDADO = {
    "id_viaje": 1,
    "id_usuario": 7,
    "destinos": ["Kioto, Japón"],
    "fecha_inicio": "2030-03-10",
    "fecha_fin": "2030-03-12",
    "tipo_viaje": "Balanced",
    "costo_total_estimado": 1100.0,
    "estado": "guardado",
    "group_id": "grupo-1",
    "created_at": "2030-01-01T00:00:00",
    "imagen": "https://example.com/kioto.jpg",
    "costos": {
        "costo_alojamiento": 350.0,
        "costo_transporte": 300.0,
        "costo_actividades": 200.0,
        "costo_comidas": 150.0,
        "costo_total_base": 1000.0,
        "costo_total_ajustado": 1100.0,
        "tipo_viaje_aplicado": "Balanced",
    },
    "itinerarios": [
        {
            "id_itinerario": dia,
            "dia": dia,
            "resumen": f"Día {dia} en Kioto",
            "actividades": [
                {
                    "id_actividad": dia,
                    "nombre": f"Actividad {dia}",
                    "descripcion": "Descripción",
                    "precio_estimado": 25.0,
                    "categoria": "Cultural",
                    "horario_sugerido": "10:00 - 12:00",
                    "ubicacion": "Kioto",
                }
            ],
        } for dia in (1, 2, 3)
    ],
}


class BackendSimulado:
    """Responde como el backend real, sin red."""

    def __init__(self):
        self.llamadas = []
        self.drafts = []

    def responder(self, metodo, ruta, **kwargs):
        self.llamadas.append((metodo, ruta, kwargs.get("json")))

        if ruta.endswith("/drafts"):
            return list(self.drafts)
        if ruta.startswith("/viajes/usuario/"):
            return [VIAJE_GUARDADO]
        if ruta.startswith("/viajes/") and metodo == "GET":
            return dict(VIAJE_GUARDADO)
        if ruta == "/viajes/generate":
            return {"group_id": "grupo-nuevo"}
        if ruta == "/preferencias/":
            return {"id": 42}
        if ruta.startswith("/usuarios/") and metodo == "GET":
            return {"id_usuario": 7, "nombre": "Test", "apellido": "User",
                    "email": "test@example.com", "nacionalidad": "Argentina",
                    "foto": None, "idioma": "es"}
        if ruta == "/usuarios/login":
            return {"id_usuario": 7, "nombre": "Test", "apellido": "User",
                    "email": "test@example.com", "foto": None, "idioma": "es"}
        return {}


@pytest.fixture
def backend(monkeypatch):
    import api_client
    import trip_generator

    simulado = BackendSimulado()

    def falso_request(metodo, ruta, **kwargs):
        return simulado.responder(metodo, ruta, **kwargs)

    monkeypatch.setattr(api_client, "request", falso_request)
    monkeypatch.setattr(api_client, "get", lambda ruta, **kw: falso_request("GET", ruta, **kw))
    monkeypatch.setattr(api_client, "post", lambda ruta, **kw: falso_request("POST", ruta, **kw))
    monkeypatch.setattr(api_client, "put", lambda ruta, **kw: falso_request("PUT", ruta, **kw))
    monkeypatch.setattr(api_client, "delete", lambda ruta, **kw: falso_request("DELETE", ruta, **kw))
    monkeypatch.setattr(api_client, "get_o_defecto",
                        lambda ruta, defecto=None, **kw: falso_request("GET", ruta, **kw) or defecto)

    # Sin red: la búsqueda de imágenes del destino queda anulada.
    monkeypatch.setattr(trip_generator, "obtener_imagen_destino", lambda destino: None)

    return simulado


@pytest.fixture
def app(backend):
    import app as modulo
    modulo.app.config["TESTING"] = True
    return modulo.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logueado(client):
    """Cliente con sesión iniciada y el token CSRF a mano."""
    with client.session_transaction() as sesion:
        sesion["user_id"] = 7
        sesion["user_email"] = "test@example.com"
        sesion["user_nombre"] = "Test"
        sesion["user_apellido"] = "User"
        sesion["user_lang"] = "es"
        sesion["_csrf_token"] = "token-de-test"
    return client


@pytest.fixture
def csrf():
    return {"X-CSRF-Token": "token-de-test"}
