from src.models.init import db

class Viaje(db.Model):
    __tablename__ = "viajes"

    id_viaje = db.Column(db.Integer, primary_key=True)

    id_usuario = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id_usuario"),
        nullable=False
    )

    destino = db.Column(db.String(120), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)

    tipo_viaje = db.Column(db.String(20), nullable=False)
    costo_total_estimado = db.Column(db.Float)

    usuario = db.relationship("Usuario", back_populates="viajes")

    costo = db.relationship(
        "Costo",
        back_populates="viaje",
        uselist=False,
        cascade="all, delete-orphan"
    )

    itinerarios = db.relationship(
        "Itinerario",
        back_populates="viaje",
        cascade="all, delete-orphan"
    )

    recomendaciones = db.relationship(
        "RecomendacionIA",
        back_populates="viaje",
        cascade="all, delete-orphan"
    )