from src.models.init import db

class ViajeDestino(db.Model):
    __tablename__ = "viaje_destinos"

    id_viaje_destino = db.Column(db.Integer, primary_key=True)
    id_viaje = db.Column(db.Integer, db.ForeignKey("viajes.id_viaje"), nullable=False)
    
    nombre = db.Column(db.String(150), nullable=False)
    fecha_llegada = db.Column(db.Date, nullable=False)
    fecha_partida = db.Column(db.Date, nullable=False)

    viaje = db.relationship("Viaje", back_populates="viaje_destinos")
    actividades = db.relationship("Actividad", back_populates="destino_viaje")
