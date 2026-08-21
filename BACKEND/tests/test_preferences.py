"""Preferencias del usuario: normalización del grupo y validaciones."""

import pytest

from src.validators.user_preferences_validator import normalizar_grupo


@pytest.mark.parametrize("entrada, esperado", [
    ("family", "familiar"),
    ("friends", "amigos"),
    ("educational", "educativo"),
    ("couple", "pareja"),
    ("solo", "solo"),
    ("FAMILY", "familiar"),
    ("  amigos  ", "amigos"),
    ("cualquiera", None),
    (None, None),
])
def test_normalizacion_del_grupo(entrada, esperado):
    assert normalizar_grupo(entrada) == esperado


def test_el_grupo_del_formulario_se_acepta_y_se_guarda_traducido(client, auth, usuario):
    """Éste era el bug: el form manda 'family' y el dominio guarda 'familiar'."""
    respuesta = client.post("/preferencias/", json={
        "id_usuario": usuario,
        "destinos": ["Kioto, Japón"],
        "origen": "Córdoba, Argentina",
        "grupo": "family",
        "costo_min": 1000,
        "costo_max": 3000,
        "cantidad_personas": 3,
        "fecha_inicio": "2030-03-10",
        "fecha_fin": "2030-03-17",
    }, headers=auth)

    assert respuesta.status_code == 201, respuesta.get_json()

    guardadas = client.get(f"/preferencias/usuario/{usuario}", headers=auth).get_json()
    assert guardadas[0]["grupo"] == "familiar"


def test_grupo_invalido_devuelve_400(client, auth, usuario):
    respuesta = client.post("/preferencias/", json={
        "id_usuario": usuario,
        "destinos": ["Roma"],
        "grupo": "empresarial",
    }, headers=auth)

    assert respuesta.status_code == 400
    assert "grupo" in respuesta.get_json()["errores_validacion"]


def test_presupuesto_igual_es_valido(client, auth, usuario):
    """Antes `costo_min == costo_max` fallaba; un presupuesto cerrado es legítimo."""
    respuesta = client.post("/preferencias/", json={
        "id_usuario": usuario,
        "destinos": ["Lisboa"],
        "costo_min": 2000,
        "costo_max": 2000,
    }, headers=auth)
    assert respuesta.status_code == 201


def test_presupuesto_invertido_devuelve_400(client, auth, usuario):
    respuesta = client.post("/preferencias/", json={
        "id_usuario": usuario,
        "destinos": ["Lisboa"],
        "costo_min": 3000,
        "costo_max": 1000,
    }, headers=auth)
    assert respuesta.status_code == 400


def test_fechas_iguales_son_validas(client, auth, usuario):
    """Un viaje de un solo día es válido."""
    respuesta = client.post("/preferencias/", json={
        "id_usuario": usuario,
        "destinos": ["Rosario"],
        "fecha_inicio": "2030-05-01",
        "fecha_fin": "2030-05-01",
    }, headers=auth)
    assert respuesta.status_code == 201


def test_el_hospedaje_se_asocia_al_catalogo(client, auth, usuario):
    respuesta = client.post("/preferencias/", json={
        "id_usuario": usuario,
        "destinos": ["Tokio"],
        "hospedaje": "hotel, airbnb",
    }, headers=auth)
    assert respuesta.status_code == 201

    catalogo = client.get("/tipos_alojamiento/", headers=auth).get_json()
    tipos = {t["tipo"] for t in catalogo}
    assert {"Hotel", "Airbnb"}.issubset(tipos)


def test_no_puedo_crear_preferencias_para_otro(client, auth, otro_usuario):
    respuesta = client.post("/preferencias/", json={
        "id_usuario": otro_usuario,
        "destinos": ["Madrid"],
    }, headers=auth)
    assert respuesta.status_code == 403
