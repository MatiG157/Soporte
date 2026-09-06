from src.models.init import db

class Actividad(db.Model):
    __tablename__ = "actividades"

    id_actividad = db.Column(db.Integer, primary_key=True)

    id_itinerario = db.Column(
        db.Integer,
        db.ForeignKey("itinerarios.id_itinerario"),
        nullable=False
    )

    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text)
    precio_estimado = db.Column(db.Float, default=0)
    categoria = db.Column(db.String(80))
    horario_sugerido = db.Column(db.String(30))
    ubicacion = db.Column(db.String(150))

    # Procedencia del precio: el flujo de n8n cotiza vuelos y hoteles contra
    # APIs reales y manda el link de la oferta, una nota y un aviso cuando el
    # precio le resulta dudoso.
    link = db.Column(db.String(1000))
    nota = db.Column(db.String(300))
    precio_sospechoso = db.Column(db.Boolean, default=False, nullable=False)

    # El lugar real, cruzado contra Google Places. `imagen_ref` es la referencia
    # de la foto, no su URL: la URL firmada lleva la API key y no puede salir
    # al navegador (la sirve el proxy del frontend).
    imagen_ref = db.Column(db.String(1000))
    rating = db.Column(db.Float)
    opiniones = db.Column(db.Integer)
    mapa = db.Column(db.String(1000))
    web = db.Column(db.String(1000))
    place_id = db.Column(db.String(120))
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)

    # De dónde salió el precio. "google_price_range" es un monto consultado;
    # "tasacion_ia" es una estimación de un modelo. La tarjeta los muestra
    # distinto: hacerlos pasar por lo mismo sería presentar como dato lo que es
    # una aproximación.
    precio_fuente = db.Column(db.String(40))
    precio_desde = db.Column(db.Float)
    precio_hasta = db.Column(db.Float)
    precio_moneda = db.Column(db.String(8))

    id_viaje_destino = db.Column(
        db.Integer,
        db.ForeignKey("viaje_destinos.id_viaje_destino"),
        nullable=True
    )

    itinerario = db.relationship(
        "Itinerario",
        back_populates="actividades"
    )

    destino_viaje = db.relationship(
        "ViajeDestino",
        back_populates="actividades"
    )