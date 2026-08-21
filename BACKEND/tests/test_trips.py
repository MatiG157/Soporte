"""Ciclo de vida de los viajes generados: borradores, selección y persistencia."""

from tests.conftest import opcion_de_viaje


def _generar(client, auth, usuario, tipos=("Economy", "Balanced", "Luxury"), dias=3):
    opciones = [
        opcion_de_viaje(tipo=tipo, dias=dias, total=1000.0 * (indice + 1))
        for indice, tipo in enumerate(tipos)
    ]
    respuesta = client.post("/viajes/generate", json={
        "id_usuario": usuario,
        "opciones": opciones,
    }, headers=auth)
    assert respuesta.status_code == 200, respuesta.get_json()
    return respuesta.get_json()["group_id"]


def test_generar_crea_tres_borradores(client, auth, usuario):
    _generar(client, auth, usuario)

    drafts = client.get(f"/viajes/usuario/{usuario}/drafts", headers=auth).get_json()
    assert len(drafts) == 3
    assert {d["tipo_viaje"] for d in drafts} == {"Economy", "Balanced", "Luxury"}
    assert all(d["estado"] == "draft" for d in drafts)
    assert len({d["group_id"] for d in drafts}) == 1


def test_generar_reemplaza_los_borradores_previos(client, auth, usuario):
    primero = _generar(client, auth, usuario)
    segundo = _generar(client, auth, usuario)

    drafts = client.get(f"/viajes/usuario/{usuario}/drafts", headers=auth).get_json()
    assert len(drafts) == 3
    assert drafts[0]["group_id"] == segundo != primero


def test_el_itinerario_respeta_la_cantidad_de_dias(client, auth, usuario):
    _generar(client, auth, usuario, tipos=("Balanced",), dias=8)

    id_viaje = client.get(f"/viajes/usuario/{usuario}/drafts", headers=auth).get_json()[0]["id_viaje"]
    viaje = client.get(f"/viajes/{id_viaje}", headers=auth).get_json()

    assert len(viaje["itinerarios"]) == 8
    assert [i["dia"] for i in viaje["itinerarios"]] == list(range(1, 9))
    assert all(i["actividades"] for i in viaje["itinerarios"])


def test_seleccionar_confirma_uno_y_descarta_el_resto(client, auth, usuario):
    _generar(client, auth, usuario)

    drafts = client.get(f"/viajes/usuario/{usuario}/drafts", headers=auth).get_json()
    elegido = drafts[1]["id_viaje"]

    assert client.post(f"/viajes/{elegido}/select", headers=auth).status_code == 200

    viajes = client.get(f"/viajes/usuario/{usuario}", headers=auth).get_json()
    assert len(viajes) == 1
    assert viajes[0]["id_viaje"] == elegido
    assert viajes[0]["estado"] == "guardado"


def test_no_se_puede_seleccionar_dos_veces(client, auth, usuario):
    _generar(client, auth, usuario)
    elegido = client.get(f"/viajes/usuario/{usuario}/drafts", headers=auth).get_json()[0]["id_viaje"]

    assert client.post(f"/viajes/{elegido}/select", headers=auth).status_code == 200
    assert client.post(f"/viajes/{elegido}/select", headers=auth).status_code == 409


def test_se_guardan_imagen_costos_y_recomendacion(client, auth, usuario):
    _generar(client, auth, usuario, tipos=("Balanced",))

    id_viaje = client.get(f"/viajes/usuario/{usuario}/drafts", headers=auth).get_json()[0]["id_viaje"]
    viaje = client.get(f"/viajes/{id_viaje}", headers=auth).get_json()

    assert viaje["imagen"] == "https://example.com/kioto.jpg"

    costos = viaje["costos"]
    assert costos is not None
    assert costos["costo_alojamiento"] == 350.0
    assert costos["costo_total_base"] == 1000.0
    # Balanced multiplica por 1.10.
    assert costos["costo_total_ajustado"] == 1100.0
    assert viaje["costo_total_estimado"] == 1100.0


def test_los_textos_largos_se_recortan_a_la_columna(client, auth, usuario):
    opcion = opcion_de_viaje(tipo="Economy", dias=1)
    opcion["itinerario"][0]["actividades"][0].update({
        "nombre": "N" * 300,
        "categoria": "C" * 200,
        "horario_sugerido": "H" * 80,
        "ubicacion": "U" * 400,
    })

    client.post("/viajes/generate", json={
        "id_usuario": usuario, "opciones": [opcion],
    }, headers=auth)

    id_viaje = client.get(f"/viajes/usuario/{usuario}/drafts", headers=auth).get_json()[0]["id_viaje"]
    actividad = client.get(f"/viajes/{id_viaje}", headers=auth).get_json()["itinerarios"][0]["actividades"][0]

    assert len(actividad["nombre"]) == 120
    assert len(actividad["categoria"]) == 80
    assert len(actividad["horario_sugerido"]) == 30
    assert len(actividad["ubicacion"]) == 150


def test_opciones_vacias_devuelve_400(client, auth, usuario):
    respuesta = client.post("/viajes/generate", json={
        "id_usuario": usuario, "opciones": [],
    }, headers=auth)
    assert respuesta.status_code == 400


def test_borrar_viaje_arrastra_itinerarios(client, auth, usuario):
    _generar(client, auth, usuario, tipos=("Balanced",))
    id_viaje = client.get(f"/viajes/usuario/{usuario}/drafts", headers=auth).get_json()[0]["id_viaje"]

    assert client.delete(f"/viajes/{id_viaje}", headers=auth).status_code == 200
    assert client.get(f"/viajes/{id_viaje}", headers=auth).status_code == 404
    assert client.get(f"/itinerarios/viaje/{id_viaje}", headers=auth).status_code == 404
