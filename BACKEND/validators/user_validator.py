from marshmallow import Schema, fields, validate

class UsuariosSchema(Schema):
    # Campos obligatorios (required=True)
    nombre = fields.String(
        required=True, 
        validate=validate.Length(min=2, max=80),
        error_messages={"required": "El nombre es obligatorio."}
    )
    
    apellido = fields.String(
        required=True, 
        validate=validate.Length(min=2, max=80),
        error_messages={"required": "El apellido es obligatorio."}
    )
    
    email = fields.Email(
        required=True,
        validate=validate.Length(max=120),
        error_messages={
            "required": "El email es obligatorio.",
            "invalid": "El formato del email no es válido."
        }
    )
    
    contrasena = fields.String(
        required=True, 
        validate=[
            validate.Length(
                min=8, 
                max=16, 
                error="La contraseña debe tener entre 8 y 16 caracteres."
            ),
            validate.Regexp(
                regex=r'.*[A-Z].*', 
                error="La contraseña debe contener al menos una letra mayúscula."
            ),
            validate.Regexp(
                regex=r'.*[0-9].*', 
                error="La contraseña debe contener al menos un número."
            )
        ],
        error_messages={"required": "La contraseña es obligatoria."}
    )
    
    nacionalidad = fields.String(
        validate=validate.Length(max=80)
    )

# Instanciamos el validador
usuarios_schema = UsuariosSchema()