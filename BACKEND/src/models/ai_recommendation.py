from src.models.init import db
from datetime import datetime

class RecomendacionIA(db.Model):
    __tablename__ = "recomendaciones_ia"

    id_recomendacion = db.Column(db.Integer, primary_key=True)

    id_viaje = db.Column(
        db.Integer,
        db.ForeignKey("viajes.id_viaje"),
        nullable=False
    )

    texto_generado = db.Column(db.Text, nullable=False)
    fecha_generacion = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    tipo = db.Column(db.String(50))  # itinerario, ajuste, consejo

    viaje = db.relationship(
        "Viaje",
        back_populates="recomendaciones"
    )