from src.models.init import db

class Usuario(db.Model):
    __tablename__ = "usuarios"

    id_usuario = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False)
    apellido = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    contrasena = db.Column(db.String(255), nullable=False)
    nacionalidad = db.Column(db.String(80))

    preferencias = db.relationship(
        "PreferenciasUsuario",
        back_populates="usuario",
        cascade="all, delete-orphan"
    )

    viajes = db.relationship(
        "Viaje",
        back_populates="usuario", #Esto se refiere a la relación inversa en la clase Viaje, 
        #donde se define el atributo 'usuario' que apunta a esta clase Usuario.
        cascade="all, delete-orphan"
    )