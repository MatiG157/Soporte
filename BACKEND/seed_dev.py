"""Datos de desarrollo para TravelPlanner.

Crea el catálogo de tipos de alojamiento, tres usuarios de prueba con sus
preferencias, un viaje guardado por usuario con itinerario, actividades y
costos, y opcionalmente un grupo de tres borradores para probar /compare.

Uso:
    python seed_dev.py                 # siembra lo que falte (idempotente)
    python seed_dev.py --con-drafts    # además genera 3 borradores por usuario
    python seed_dev.py --reset         # borra los datos sembrados y vuelve a empezar
"""

import argparse
from datetime import date, timedelta

from app import app
from src.models.accommodation_type import TipoAlojamiento
from src.models.init import db
from src.models.trip import Viaje
from src.models.user import Usuario
from src.models.user_preferences import PreferenciasUsuario
from src.services.trip_service import guardar_viajes_generados
from werkzeug.security import generate_password_hash

TIPOS_ALOJAMIENTO = ["Hotel", "Hostal", "Airbnb", "Resort", "Apartamento", "Camping"]

USUARIOS = [
    {
        "nombre": "Ana", "apellido": "Gomez",
        "email": "ana.gomez.dev@example.com",
        "contrasena": "DevPass123", "nacionalidad": "Argentina", "idioma": "es",
        "preferencias": {
            "origen": "Buenos Aires, Argentina",
            "destinos": ["Lisboa, Portugal"],
            "costo_min": 900, "costo_max": 1800,
            "cantidad_personas": 2, "grupo": "pareja",
            "hospedaje": "hotel, airbnb",
            "edades_viajeros": "29, 31",
            "tipo_transporte": "plane",
            "act_preferidas": "sightseeing, cultural",
            "otros": "Prefiere hotel céntrico y caminatas gastronómicas.",
        },
        "viaje": {
            "destinos": ["Lisboa, Portugal"],
            "dias": 6, "en": 30, "tipo": "Balanced",
            "imagen": "https://images.unsplash.com/photo-1585208798174-6cedd86e019a?w=800",
        },
    },
    {
        "nombre": "Lucas", "apellido": "Perez",
        "email": "lucas.perez.dev@example.com",
        "contrasena": "DevPass123", "nacionalidad": "Chile", "idioma": "es",
        "preferencias": {
            "origen": "Santiago, Chile",
            "destinos": ["Bariloche, Argentina"],
            "costo_min": 600, "costo_max": 1400,
            "cantidad_personas": 4, "grupo": "amigos",
            "hospedaje": "hostel",
            "edades_viajeros": "27, 28, 29, 30",
            "tipo_transporte": "car",
            "act_preferidas": "adventure",
            "otros": "Actividades de montaña y alojamiento con buena vista.",
        },
        "viaje": {
            "destinos": ["Bariloche, Argentina"],
            "dias": 5, "en": -20, "tipo": "Economy",
            "imagen": "https://images.unsplash.com/photo-1531761535209-180857e963b9?w=800",
        },
    },
    {
        "nombre": "Marta", "apellido": "Lopez",
        "email": "marta.lopez.dev@example.com",
        "contrasena": "DevPass123", "nacionalidad": "España", "idioma": "en",
        "preferencias": {
            "origen": "Madrid, España",
            "destinos": ["Tokio, Japón", "Kioto, Japón"],
            "costo_min": 2200, "costo_max": 4200,
            "cantidad_personas": 1, "grupo": "solo",
            "hospedaje": "hotel, resort",
            "edades_viajeros": "34",
            "tipo_transporte": "plane, train",
            "act_preferidas": "cultural, sightseeing",
            "otros": "Interés en cultura, tecnología y comida local.",
        },
        "viaje": {
            "destinos": ["Tokio, Japón", "Kioto, Japón"],
            "dias": 8, "en": 90, "tipo": "Luxury",
            "imagen": "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=800",
        },
    },
]

PLANTILLA_ACTIVIDADES = {
    "Economy": [
        ("Caminata por el casco histórico", "Recorrido a pie por el centro.", 0.0,
         "Sightseeing", "09:00 - 12:00"),
        ("Almuerzo en mercado local", "Comida típica a precio de barrio.", 12.0,
         "Gastronomía", "13:00 - 14:30"),
        ("Museo de entrada libre", "Visita al museo municipal.", 0.0,
         "Cultural", "16:00 - 18:00"),
    ],
    "Balanced": [
        ("Tour guiado en grupo reducido", "Guía local durante media jornada.", 35.0,
         "Sightseeing", "09:30 - 13:00"),
        ("Almuerzo en restaurante típico", "Menú regional de tres pasos.", 28.0,
         "Gastronomía", "13:30 - 15:00"),
        ("Excursión a las afueras", "Traslado y visita a un punto cercano.", 45.0,
         "Aventura", "16:00 - 19:30"),
    ],
    "Luxury": [
        ("Tour privado con chofer", "Recorrido exclusivo con guía personal.", 220.0,
         "Sightseeing", "09:00 - 13:00"),
        ("Almuerzo de autor", "Restaurante con estrella, menú degustación.", 180.0,
         "Gastronomía", "13:30 - 15:30"),
        ("Spa y experiencia premium", "Circuito de spa en hotel cinco estrellas.", 150.0,
         "Relax", "17:00 - 20:00"),
    ],
}

COSTO_POR_TIPO = {"Economy": 950.0, "Balanced": 2400.0, "Luxury": 5600.0}


def construir_opcion(destinos, fecha_inicio, dias, tipo, imagen=None):
    """Arma una opción con el mismo contrato que devuelve el flujo de n8n."""
    fecha_fin = fecha_inicio + timedelta(days=dias - 1)
    plantilla = PLANTILLA_ACTIVIDADES[tipo]

    itinerario = []
    for dia in range(1, dias + 1):
        destino = destinos[(dia - 1) % len(destinos)]
        itinerario.append({
            "dia": dia,
            "resumen": f"Día {dia} en {destino}",
            "actividades": [
                {
                    "nombre": nombre,
                    "descripcion": descripcion,
                    "precio_estimado": precio,
                    "categoria": categoria,
                    "horario_sugerido": horario,
                    "ubicacion": destino,
                }
                for nombre, descripcion, precio, categoria, horario in plantilla
            ],
        })

    total = COSTO_POR_TIPO[tipo]
    return {
        "destinos": destinos,
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "tipo": tipo,
        "costo_total_estimado": total,
        "imagen": imagen,
        "desglose_costos": {
            "costo_alojamiento": round(total * 0.35, 2),
            "costo_transporte": round(total * 0.30, 2),
            "costo_actividades": round(total * 0.20, 2),
            "costo_comidas": round(total * 0.15, 2),
        },
        "itinerario": itinerario,
    }


def sembrar_tipos_alojamiento():
    creados = 0
    for nombre in TIPOS_ALOJAMIENTO:
        if TipoAlojamiento.query.filter_by(tipo=nombre).first() is None:
            db.session.add(TipoAlojamiento(tipo=nombre))
            creados += 1
    db.session.commit()
    return creados


def sembrar_usuario(spec):
    usuario = Usuario.query.filter_by(email=spec["email"]).first()
    if usuario is None:
        usuario = Usuario(
            nombre=spec["nombre"],
            apellido=spec["apellido"],
            email=spec["email"],
            contrasena=generate_password_hash(spec["contrasena"]),
            nacionalidad=spec["nacionalidad"],
            idioma=spec["idioma"],
        )
        db.session.add(usuario)
        db.session.flush()
    return usuario


def sembrar_preferencia(usuario, spec):
    existente = PreferenciasUsuario.query.filter_by(id_usuario=usuario.id_usuario).first()
    if existente is not None:
        return existente

    catalogo = {t.tipo.lower(): t for t in TipoAlojamiento.query.all()}
    alias = {"hostel": "hostal", "departamento": "apartamento"}

    preferencia = PreferenciasUsuario(id_usuario=usuario.id_usuario, **spec)
    for crudo in str(spec.get("hospedaje", "")).split(","):
        clave = crudo.strip().lower()
        clave = alias.get(clave, clave)
        if clave in catalogo:
            preferencia.tipos_alojamiento.append(catalogo[clave])

    db.session.add(preferencia)
    db.session.flush()
    return preferencia


def sembrar_viaje_guardado(usuario, preferencia, spec):
    if Viaje.query.filter_by(id_usuario=usuario.id_usuario, estado="guardado").first():
        return False

    fecha_inicio = date.today() + timedelta(days=spec["en"])
    opcion = construir_opcion(
        spec["destinos"], fecha_inicio, spec["dias"], spec["tipo"], spec.get("imagen")
    )

    guardar_viajes_generados(usuario.id_usuario, [opcion], preferencia.id_preferencia)

    viaje = (
        Viaje.query
        .filter_by(id_usuario=usuario.id_usuario, estado="draft")
        .order_by(Viaje.id_viaje.desc())
        .first()
    )
    viaje.estado = "guardado"
    db.session.commit()
    return True


def sembrar_drafts(usuario, preferencia, spec):
    fecha_inicio = date.today() + timedelta(days=45)
    opciones = [
        construir_opcion(spec["destinos"], fecha_inicio, spec["dias"], tipo, spec.get("imagen"))
        for tipo in ("Economy", "Balanced", "Luxury")
    ]
    guardar_viajes_generados(usuario.id_usuario, opciones, preferencia.id_preferencia)


def resetear():
    emails = [u["email"] for u in USUARIOS]
    borrados = 0
    for usuario in Usuario.query.filter(Usuario.email.in_(emails)).all():
        db.session.delete(usuario)  # el cascade se lleva viajes y preferencias
        borrados += 1
    db.session.commit()
    return borrados


def main():
    parser = argparse.ArgumentParser(description="Siembra datos de desarrollo")
    parser.add_argument("--con-drafts", action="store_true",
                        help="genera además 3 borradores por usuario para probar /compare")
    parser.add_argument("--reset", action="store_true",
                        help="borra los usuarios de prueba antes de sembrar")
    args = parser.parse_args()

    with app.app_context():
        db.create_all()

        if args.reset:
            print(f"Usuarios de prueba eliminados: {resetear()}")

        print(f"Tipos de alojamiento creados: {sembrar_tipos_alojamiento()}")

        for spec in USUARIOS:
            usuario = sembrar_usuario(spec)
            preferencia = sembrar_preferencia(usuario, spec["preferencias"])
            db.session.commit()

            creado = sembrar_viaje_guardado(usuario, preferencia, spec["viaje"])
            print(f"  {spec['email']}: viaje guardado {'creado' if creado else 'ya existía'}")

            if args.con_drafts:
                sembrar_drafts(usuario, preferencia, spec["viaje"])
                print(f"  {spec['email']}: 3 borradores generados")

        print("\nListo. Podés entrar con cualquiera de estos usuarios y la contraseña DevPass123:")
        for spec in USUARIOS:
            print(f"  - {spec['email']}")


if __name__ == "__main__":
    main()
