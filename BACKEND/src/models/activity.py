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
    link = db.Column(db.String(500))
    nota = db.Column(db.String(300))
    precio_sospechoso = db.Column(db.Boolean, default=False, nullable=False)

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