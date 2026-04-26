from src.models.init import db

# tabla intermedia many-to-many
preferencia_tipo_alojamiento = db.Table(
    "preferencia_tipo_alojamiento",
    db.Column("id_preferencia", db.Integer,
              db.ForeignKey("preferencias_usuario.id_preferencia"),
              primary_key=True),
    db.Column("id_tipo", db.Integer,
              db.ForeignKey("tipos_alojamiento.id_tipo"),
              primary_key=True)
)

class PreferenciasUsuario(db.Model):
    __tablename__ = "preferencias_usuario"

    id_preferencia = db.Column(db.Integer, primary_key=True)

    id_usuario = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id_usuario"),
        nullable=False
    )

    destino = db.Column(db.String(120))
    costo_min = db.Column(db.Float)
    costo_max = db.Column(db.Float)
    cantidad_personas = db.Column(db.Integer)
    grupo = db.Column(db.String(30))  # familiar, amigos, educativo
    clima = db.Column(db.String(50))
    otros = db.Column(db.Text)

    usuario = db.relationship("Usuario", back_populates="preferencias")

    tipos_alojamiento = db.relationship(
        "TipoAlojamiento",
        secondary=preferencia_tipo_alojamiento,
        back_populates="preferencias"
    )