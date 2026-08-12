from src.models.init import db
from datetime import datetime


class Viaje(db.Model):
    __tablename__ = "viajes"

    id_viaje = db.Column(db.Integer, primary_key=True)

    id_usuario = db.Column(db.Integer, db.ForeignKey(
        "usuarios.id_usuario"), nullable=False)

    destinos = db.Column(db.JSON, nullable=False)  # Lista de destinos ["Buenos Aires", "Mendoza"]
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    tipo_viaje = db.Column(db.String(20), nullable=False)
    costo_total_estimado = db.Column(db.Float)

    # NUEVOS CAMPOS:
    estado = db.Column(db.String(20), default="draft", nullable=False)
    group_id = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # URL de la imagen generada
    imagen = db.Column(db.String(500), nullable=True)
    # FK a preferencias_usuario
    id_user_preferences = db.Column(db.Integer, db.ForeignKey("preferencias_usuario.id_preferencia"), nullable=True)

    # Relaciones...
    usuario = db.relationship("Usuario", back_populates="viajes")
    preferencias = db.relationship("PreferenciasUsuario", backref="viajes_generados")
    costo = db.relationship("Costo", back_populates="viaje",
                            uselist=False, cascade="all, delete-orphan")
    itinerarios = db.relationship(
        "Itinerario", back_populates="viaje", cascade="all, delete-orphan")
    recomendaciones = db.relationship(
        "RecomendacionIA", back_populates="viaje", cascade="all, delete-orphan")
