"""Configuración común de los tests.

La app de test corre sobre SQLite en memoria: los tests no tocan MySQL ni
dependen de que la base de desarrollo exista.
"""

import os
import sys

import pytest
from flask import Flask

# Permite importar `src.*` ejecutando pytest desde BACKEND/ o desde la raíz.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

API_KEY = "clave-de-test"
os.environ["API_KEY"] = API_KEY
os.environ["ADMIN_KEY"] = "admin-de-test"

from src.auth import verificar_api_key  # noqa: E402
from src.models.init import db  # noqa: E402
from src.routes.accommodation_types_routes import accommodation_types_bp  # noqa: E402
from src.routes.activity_routes import activity_bp  # noqa: E402
from src.routes.cost_routes import cost_bp  # noqa: E402
from src.routes.itinerary_routes import itinerary_bp  # noqa: E402
from src.routes.trip_routes import trip_bp  # noqa: E402
from src.routes.user_preferences_routes import user_preferences_bp  # noqa: E402
from src.routes.user_routes import user_bp  # noqa: E402


@pytest.fixture
def app():
    aplicacion = Flask(__name__)
    aplicacion.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    aplicacion.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    aplicacion.config["TESTING"] = True

    aplicacion.before_request(verificar_api_key)

    aplicacion.register_blueprint(user_bp, url_prefix="/usuarios")
    aplicacion.register_blueprint(user_preferences_bp, url_prefix="/preferencias")
    aplicacion.register_blueprint(cost_bp, url_prefix="/costos")
    aplicacion.register_blueprint(activity_bp, url_prefix="/actividades")
    aplicacion.register_blueprint(accommodation_types_bp, url_prefix="/tipos_alojamiento")
    aplicacion.register_blueprint(trip_bp, url_prefix="/viajes")
    aplicacion.register_blueprint(itinerary_bp, url_prefix="/itinerarios")

    db.init_app(aplicacion)

    with aplicacion.app_context():
        db.create_all()
        yield aplicacion
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def cabeceras():
    """Sólo API key: sirve para endpoints públicos como login o alta."""
    return {"X-API-KEY": API_KEY}


@pytest.fixture
def usuario(client, cabeceras):
    """Crea un usuario y devuelve su id."""
    respuesta = client.post("/usuarios/", json={
        "nombre": "Test",
        "apellido": "User",
        "email": "test@example.com",
        "contrasena": "DevPass123",
        "nacionalidad": "Argentina",
    }, headers=cabeceras)
    assert respuesta.status_code == 201, respuesta.get_json()
    return respuesta.get_json()["id"]


@pytest.fixture
def auth(usuario):
    """Cabeceras de un usuario autenticado."""
    return {"X-API-KEY": API_KEY, "X-User-Id": str(usuario)}


@pytest.fixture
def otro_usuario(client, cabeceras):
    respuesta = client.post("/usuarios/", json={
        "nombre": "Otro",
        "apellido": "Usuario",
        "email": "otro@example.com",
        "contrasena": "DevPass123",
    }, headers=cabeceras)
    assert respuesta.status_code == 201
    return respuesta.get_json()["id"]


def opcion_de_viaje(tipo="Balanced", dias=3, total=1000.0):
    """Construye una opción con el mismo contrato que devuelve n8n."""
    return {
        "destinos": ["Kioto, Japón"],
        "fecha_inicio": "2030-03-10",
        "fecha_fin": f"2030-03-{9 + dias:02d}",
        "tipo": tipo,
        "costo_total_estimado": total,
        "imagen": "https://example.com/kioto.jpg",
        "desglose_costos": {
            "costo_alojamiento": total * 0.35,
            "costo_transporte": total * 0.30,
            "costo_actividades": total * 0.20,
            "costo_comidas": total * 0.15,
        },
        "itinerario": [
            {
                "dia": dia,
                "resumen": f"Día {dia} en Kioto",
                "actividades": [
                    {
                        "nombre": f"Actividad {dia}",
                        "descripcion": "Descripción de prueba",
                        "precio_estimado": 25.0,
                        "categoria": "Cultural",
                        "horario_sugerido": "10:00 - 12:00",
                        "ubicacion": "Kioto",
                    }
                ],
            } for dia in range(1, dias + 1)
        ],
    }
