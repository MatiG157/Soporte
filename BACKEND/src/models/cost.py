from src.models.init import db

class Costo(db.Model):
    __tablename__ = "costos"

    id_costo = db.Column(db.Integer, primary_key=True)

    id_viaje = db.Column(
        db.Integer,
        db.ForeignKey("viajes.id_viaje"),
        unique=True,
        nullable=False
    )

    costo_alojamiento = db.Column(db.Float, default=0)
    costo_transporte = db.Column(db.Float, default=0)
    costo_actividades = db.Column(db.Float, default=0)
    costo_comidas = db.Column(db.Float, default=0)
    costo_total_base = db.Column(db.Float, default=0)

    viaje = db.relationship("Viaje", back_populates="costo")