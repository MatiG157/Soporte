"""Los dos fallos que reportaron al pullear: esquema viejo y API key desincronizada.

Ambos venían de pasos manuales que había que recordar. Estos tests fijan el
comportamiento para que no vuelvan a pasar en silencio.
"""

import importlib
import io
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROYECTO = os.path.dirname(RAIZ)
if PROYECTO not in sys.path:
    sys.path.insert(0, PROYECTO)

from tests.conftest import API_KEY


# ─── API key: el 401 de configuración no se confunde con el de credenciales ──

def test_api_key_invalida_trae_codigo_identificable(client):
    respuesta = client.get("/viajes/usuario/1", headers={"X-API-KEY": "clave-que-no-es"})

    assert respuesta.status_code == 401
    assert respuesta.get_json()["codigo"] == "api_key_invalida"


def test_login_con_password_mal_no_trae_ese_codigo(client, cabeceras, usuario):
    """Un 401 de credenciales tiene que ser distinguible del de configuración."""
    respuesta = client.post("/usuarios/login", json={
        "email": "test@example.com",
        "contrasena": "estaNoEs1",
    }, headers=cabeceras)

    assert respuesta.status_code == 401
    assert "codigo" not in respuesta.get_json()


def test_sin_api_key_configurada_avisa_del_setup(client, monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)

    respuesta = client.get("/viajes/usuario/1", headers={"X-API-KEY": API_KEY})

    assert respuesta.status_code == 500
    cuerpo = respuesta.get_json()
    assert cuerpo["codigo"] == "api_key_no_configurada"
    assert "setup.py" in cuerpo["error"]


# ─── Migraciones: se pueden aplicar desde código ─────────────────────────────

def test_el_migrador_expone_una_api_programatica():
    """`app.py` la usa al arrancar para que nadie tenga que correrlo a mano."""
    import migrate

    assert callable(migrate.aplicar_pendientes)
    # Sin base disponible devuelve None en vez de matar el proceso.
    assert migrate.aplicar_pendientes(silencioso=True) is None


def test_la_migracion_de_idioma_esta_registrada():
    """`usuarios.idioma` es la columna que rompía tras el pull."""
    import migrate

    nombres = [nombre for nombre, _ in migrate.MIGRACIONES]
    assert "002_campos_de_usuario" in nombres

    fuente = io.open(
        os.path.join(RAIZ, "migrate.py"), encoding="utf-8"
    ).read()
    assert '"usuarios", "idioma"' in fuente


def test_el_backend_migra_al_arrancar():
    """Regresión: el arranque tiene que aplicar lo pendiente, no sólo create_all."""
    fuente = io.open(os.path.join(RAIZ, "app.py"), encoding="utf-8").read()

    assert "def preparar_base" in fuente
    assert "aplicar_pendientes" in fuente
    assert "preparar_base()" in fuente


# ─── setup.py: sincroniza las claves entre los dos .env ──────────────────────

@pytest.fixture
def entorno_falso(tmp_path, monkeypatch):
    """Un proyecto de mentira con sus .env.example, aislado del real."""
    backend = tmp_path / "BACKEND"
    frontend = tmp_path / "FRONTEND"
    backend.mkdir()
    frontend.mkdir()

    (backend / ".env.example").write_text(
        "DB_USER=root\nDB_NAME=travelplannerbd\n"
        "API_KEY=cambiar_por_una_clave_larga_y_aleatoria\n",
        encoding="utf-8",
    )
    (frontend / ".env.example").write_text(
        "SECRET_KEY=cambiar_por_una_clave_larga_y_aleatoria\n"
        "BACKEND_API_KEY=cambiar_por_una_clave_larga_y_aleatoria\n",
        encoding="utf-8",
    )

    import setup as modulo
    importlib.reload(modulo)
    monkeypatch.setattr(modulo, "BACKEND_ENV", str(backend / ".env"))
    monkeypatch.setattr(modulo, "FRONTEND_ENV", str(frontend / ".env"))
    return modulo


def test_setup_crea_los_env_y_sincroniza_la_clave(entorno_falso):
    setup = entorno_falso
    cambios = []

    setup.asegurar_archivos(cambios, solo_chequear=False)
    setup.sincronizar_api_key(cambios, solo_chequear=False, rotar=False)
    setup.asegurar_secret_key(cambios, solo_chequear=False, rotar=False)

    backend = setup.leer(setup.BACKEND_ENV)
    frontend = setup.leer(setup.FRONTEND_ENV)

    assert backend["API_KEY"]
    assert backend["API_KEY"] == frontend["BACKEND_API_KEY"]
    assert len(frontend["SECRET_KEY"]) > 20


def test_setup_es_idempotente(entorno_falso):
    setup = entorno_falso

    for _ in range(2):
        cambios = []
        setup.asegurar_archivos(cambios, False)
        setup.sincronizar_api_key(cambios, False, False)
        setup.asegurar_secret_key(cambios, False, False)

    primera = setup.leer(setup.BACKEND_ENV)["API_KEY"]

    cambios = []
    setup.sincronizar_api_key(cambios, False, False)
    assert setup.leer(setup.BACKEND_ENV)["API_KEY"] == primera
    assert cambios == []


def test_setup_repara_una_clave_desincronizada(entorno_falso):
    """El caso real: cada uno tenía su propia clave y el login daba 401."""
    setup = entorno_falso

    setup.asegurar_archivos([], False)
    setup.escribir_clave(setup.BACKEND_ENV, "API_KEY", "clave-del-backend")
    setup.escribir_clave(setup.FRONTEND_ENV, "BACKEND_API_KEY", "otra-distinta")

    setup.sincronizar_api_key([], solo_chequear=False, rotar=False)

    backend = setup.leer(setup.BACKEND_ENV)
    frontend = setup.leer(setup.FRONTEND_ENV)
    assert backend["API_KEY"] == "clave-del-backend"      # no la pisa
    assert frontend["BACKEND_API_KEY"] == "clave-del-backend"  # alinea el frontend


def test_setup_no_pisa_la_configuracion_existente(entorno_falso):
    setup = entorno_falso

    setup.asegurar_archivos([], False)
    setup.escribir_clave(setup.BACKEND_ENV, "DB_PASSWORD", "mi-password-real")
    setup.sincronizar_api_key([], False, False)
    setup.asegurar_secret_key([], False, False)

    assert setup.leer(setup.BACKEND_ENV)["DB_PASSWORD"] == "mi-password-real"


def test_setup_detecta_placeholders():
    import setup

    assert setup.es_placeholder("") is True
    assert setup.es_placeholder("cambiar_por_una_clave_larga_y_aleatoria") is True
    assert setup.es_placeholder("tu_password") is True
    assert setup.es_placeholder("K7xQ2mNp8vR4wZ1aB6cD") is False


def test_setup_lee_valores_entrecomillados(entorno_falso):
    """dotenv saca las comillas; el lector de setup tiene que hacer lo mismo."""
    setup = entorno_falso

    io.open(setup.BACKEND_ENV, "w", encoding="utf-8").write(
        "DB_USER = 'root'\nDB_NAME = \"travelplannerbd\"\n"
    )
    valores = setup.leer(setup.BACKEND_ENV)

    assert valores["DB_USER"] == "root"
    assert valores["DB_NAME"] == "travelplannerbd"
