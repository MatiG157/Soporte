"""La API sólo responde con la API key correcta, y nadie puede tocar datos ajenos."""

from tests.conftest import API_KEY, opcion_de_viaje


def test_sin_api_key_rechaza(client):
    assert client.get("/viajes/usuario/1").status_code == 401


def test_con_api_key_incorrecta_rechaza(client):
    respuesta = client.get("/viajes/usuario/1", headers={"X-API-KEY": "no-es-la-clave"})
    assert respuesta.status_code == 401


def test_health_y_raiz_no_exigen_api_key(app, client):
    # `/` no está registrada en la app de test, pero sí está exenta:
    # comprobamos que el rechazo sea 404 (no existe) y no 401 (no autorizado).
    assert client.get("/").status_code == 404


def test_sin_user_id_rechaza(client, cabeceras):
    respuesta = client.get("/viajes/usuario/1", headers=cabeceras)
    assert respuesta.status_code == 401
    assert "usuario" in respuesta.get_json()["error"].lower()


def test_no_puedo_ver_viajes_de_otro(client, auth, otro_usuario):
    respuesta = client.get(f"/viajes/usuario/{otro_usuario}", headers=auth)
    assert respuesta.status_code == 403


def test_no_puedo_borrar_viaje_de_otro(client, auth, cabeceras, usuario, otro_usuario):
    cabeceras_otro = {"X-API-KEY": API_KEY, "X-User-Id": str(otro_usuario)}

    creado = client.post("/viajes/generate", json={
        "id_usuario": otro_usuario,
        "opciones": [opcion_de_viaje()],
    }, headers=cabeceras_otro)
    assert creado.status_code == 200

    listado = client.get(f"/viajes/usuario/{otro_usuario}/drafts", headers=cabeceras_otro)
    id_viaje = listado.get_json()[0]["id_viaje"]

    # El primer usuario no debería poder ni verlo ni borrarlo.
    assert client.get(f"/viajes/{id_viaje}", headers=auth).status_code == 403
    assert client.delete(f"/viajes/{id_viaje}", headers=auth).status_code == 403


def test_no_puedo_generar_viajes_para_otro(client, auth, otro_usuario):
    respuesta = client.post("/viajes/generate", json={
        "id_usuario": otro_usuario,
        "opciones": [opcion_de_viaje()],
    }, headers=auth)
    assert respuesta.status_code == 403


def test_login_correcto_e_incorrecto(client, cabeceras, usuario):
    ok = client.post("/usuarios/login", json={
        "email": "test@example.com", "contrasena": "DevPass123",
    }, headers=cabeceras)
    assert ok.status_code == 200
    assert ok.get_json()["id_usuario"] == usuario

    mal = client.post("/usuarios/login", json={
        "email": "test@example.com", "contrasena": "otraClave1",
    }, headers=cabeceras)
    assert mal.status_code == 401


def test_email_duplicado_devuelve_409(client, cabeceras, usuario):
    respuesta = client.post("/usuarios/", json={
        "nombre": "Test", "apellido": "Duplicado",
        "email": "test@example.com", "contrasena": "DevPass123",
    }, headers=cabeceras)
    assert respuesta.status_code == 409


def test_catalogo_requiere_admin_para_escribir(client, auth):
    sin_admin = client.post("/tipos_alojamiento/", json={"tipo": "Cabaña"}, headers=auth)
    assert sin_admin.status_code == 403

    con_admin = client.post(
        "/tipos_alojamiento/",
        json={"tipo": "Cabaña"},
        headers={**auth, "X-ADMIN-KEY": "admin-de-test"},
    )
    assert con_admin.status_code == 201
