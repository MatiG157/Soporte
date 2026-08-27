"""Edición del itinerario recomendado y su efecto sobre el costo del viaje.

Lo que devuelve n8n es un punto de partida: el usuario puede borrar actividades,
corregirlas o agregar las suyas desde /itinerary. Cada uno de esos cambios tiene
que moverle el presupuesto al viaje.
"""

from tests.conftest import opcion_de_viaje


def _viaje_con_actividades(client, auth, usuario, total=1000.0, dias=3):
    """Crea un viaje con `dias` actividades de $25 y devuelve su detalle."""
    client.post("/viajes/generate", json={
        "id_usuario": usuario,
        "opciones": [opcion_de_viaje(dias=dias, total=total)],
    }, headers=auth)

    id_viaje = client.get(
        f"/viajes/usuario/{usuario}/drafts", headers=auth
    ).get_json()[0]["id_viaje"]
    return client.get(f"/viajes/{id_viaje}", headers=auth).get_json()


def _primera_actividad(viaje):
    return viaje["itinerarios"][0]["actividades"][0]


def test_borrar_una_actividad_baja_el_costo_del_viaje(client, auth, usuario):
    viaje = _viaje_con_actividades(client, auth, usuario)
    actividad = _primera_actividad(viaje)

    actividades_antes = viaje["costos"]["costo_actividades"]
    base_antes = viaje["costos"]["costo_total_base"]

    respuesta = client.delete(f"/actividades/{actividad['id_actividad']}", headers=auth)
    assert respuesta.status_code == 200

    costos = respuesta.get_json()["costos"]
    assert costos["costo_actividades"] == actividades_antes - actividad["precio_estimado"]
    assert costos["costo_total_base"] == base_antes - actividad["precio_estimado"]


def test_borrar_una_actividad_la_saca_del_itinerario(client, auth, usuario):
    viaje = _viaje_con_actividades(client, auth, usuario)
    actividad = _primera_actividad(viaje)

    client.delete(f"/actividades/{actividad['id_actividad']}", headers=auth)

    detalle = client.get(f"/viajes/{viaje['id_viaje']}", headers=auth).get_json()
    ids = [
        a["id_actividad"]
        for itin in detalle["itinerarios"]
        for a in itin["actividades"]
    ]
    assert actividad["id_actividad"] not in ids


def test_editar_el_precio_mueve_solo_la_diferencia(client, auth, usuario):
    viaje = _viaje_con_actividades(client, auth, usuario)
    actividad = _primera_actividad(viaje)
    base_antes = viaje["costos"]["costo_total_base"]

    nuevo_precio = actividad["precio_estimado"] + 40
    respuesta = client.patch(
        f"/actividades/{actividad['id_actividad']}",
        json={"precio_estimado": nuevo_precio},
        headers=auth,
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["costos"]["costo_total_base"] == base_antes + 40


def test_editar_sin_tocar_el_precio_no_mueve_el_costo(client, auth, usuario):
    viaje = _viaje_con_actividades(client, auth, usuario)
    actividad = _primera_actividad(viaje)
    base_antes = viaje["costos"]["costo_total_base"]

    respuesta = client.patch(
        f"/actividades/{actividad['id_actividad']}",
        json={
            "nombre": "Paseo por Gion",
            "ubicacion": "Gion, Kioto",
            "descripcion": "Caminata al atardecer",
            "horario_sugerido": "18:00 - 20:00",
        },
        headers=auth,
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json()["costos"]["costo_total_base"] == base_antes

    detalle = client.get(f"/actividades/{actividad['id_actividad']}", headers=auth).get_json()
    assert detalle["nombre"] == "Paseo por Gion"
    assert detalle["ubicacion"] == "Gion, Kioto"
    assert detalle["horario_sugerido"] == "18:00 - 20:00"


def test_agregar_una_actividad_sube_el_costo(client, auth, usuario):
    viaje = _viaje_con_actividades(client, auth, usuario)
    id_itinerario = viaje["itinerarios"][0]["id_itinerario"]
    base_antes = viaje["costos"]["costo_total_base"]

    respuesta = client.post("/actividades/", json={
        "id_itinerario": id_itinerario,
        "nombre": "Cena kaiseki",
        "precio_estimado": 120.0,
        "categoria": "Gastronomía",
        "horario_sugerido": "20:00 - 22:00",
        "ubicacion": "Pontocho",
        "descripcion": "Menú de temporada",
    }, headers=auth)

    assert respuesta.status_code == 201
    assert respuesta.get_json()["costos"]["costo_total_base"] == base_antes + 120


def test_el_ajuste_por_tipo_de_viaje_no_se_aplica_dos_veces(client, auth, usuario):
    """Borrar una actividad conserva la relación entre base y total ajustado.

    Con desglose de n8n el multiplicador no se aplica (ver README), así que el
    total ajustado tiene que seguir al base uno a uno en vez de multiplicarse
    otra vez por el 1.10 de Balanced.
    """
    viaje = _viaje_con_actividades(client, auth, usuario)
    actividad = _primera_actividad(viaje)

    factor_antes = viaje["costo_total_estimado"] / viaje["costos"]["costo_total_base"]

    client.delete(f"/actividades/{actividad['id_actividad']}", headers=auth)

    detalle = client.get(f"/viajes/{viaje['id_viaje']}", headers=auth).get_json()
    factor_despues = detalle["costo_total_estimado"] / detalle["costos"]["costo_total_base"]

    assert round(factor_despues, 4) == round(factor_antes, 4)


def test_otro_usuario_no_puede_borrar_mis_actividades(client, auth, usuario, otro_usuario):
    viaje = _viaje_con_actividades(client, auth, usuario)
    actividad = _primera_actividad(viaje)

    ajeno = {"X-API-KEY": auth["X-API-KEY"], "X-User-Id": str(otro_usuario)}
    respuesta = client.delete(f"/actividades/{actividad['id_actividad']}", headers=ajeno)
    assert respuesta.status_code == 403


def test_otro_usuario_no_puede_editar_mis_actividades(client, auth, usuario, otro_usuario):
    viaje = _viaje_con_actividades(client, auth, usuario)
    actividad = _primera_actividad(viaje)

    ajeno = {"X-API-KEY": auth["X-API-KEY"], "X-User-Id": str(otro_usuario)}
    respuesta = client.patch(
        f"/actividades/{actividad['id_actividad']}",
        json={"nombre": "Secuestrada"}, headers=ajeno,
    )
    assert respuesta.status_code == 403
