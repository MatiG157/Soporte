from src.models.init import db

class TipoAlojamiento(db.Model):
    __tablename__ = "tipos_alojamiento"

    id_tipo = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(50), unique=True, nullable=False)

    preferencias = db.relationship(
        "PreferenciasUsuario",
        secondary="preferencia_tipo_alojamiento",
        back_populates="tipos_alojamiento"
    )