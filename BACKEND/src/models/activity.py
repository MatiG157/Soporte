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

    itinerario = db.relationship(
        "Itinerario",
        back_populates="actividades"
    )