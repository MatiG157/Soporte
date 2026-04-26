from src.models.init import db

class Itinerario(db.Model):
    __tablename__ = "itinerarios"

    id_itinerario = db.Column(db.Integer, primary_key=True)

    id_viaje = db.Column(
        db.Integer,
        db.ForeignKey("viajes.id_viaje"),
        nullable=False
    )

    dia = db.Column(db.Integer, nullable=False)
    resumen = db.Column(db.Text)

    viaje = db.relationship("Viaje", back_populates="itinerarios")

    actividades = db.relationship(
        "Actividad",
        back_populates="itinerario",
        cascade="all, delete-orphan"
    )