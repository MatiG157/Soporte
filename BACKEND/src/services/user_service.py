from src.models.init import db
from src.models.user import Usuario
from src.validators.user_validator import usuarios_schema
from werkzeug.security import generate_password_hash, check_password_hash

def verificar_login(email, contrasena_plana):
    usuario = Usuario.query.filter_by(email=email).first()
    if usuario and usuario.contrasena and check_password_hash(usuario.contrasena, contrasena_plana):
        return usuario
    return None

def crear_usuario(datos):
    datos_validados = usuarios_schema.load(datos)

    contrasena_hasheada = None
    if 'contrasena' in datos_validados:
        contrasena_hasheada = generate_password_hash(datos_validados['contrasena'])

    nuevo_usuario = Usuario(
        nombre=datos_validados['nombre'],
        apellido=datos_validados['apellido'],
        email=datos_validados['email'],
        contrasena=contrasena_hasheada,
        nacionalidad=datos_validados.get('nacionalidad'),
        foto=datos_validados.get('foto')
    )
    db.session.add(nuevo_usuario)
    db.session.commit()
    return nuevo_usuario

def eliminar_usuario(id_usuario):
    usuario = Usuario.query.get(id_usuario)
    if usuario:
        db.session.delete(usuario)
        db.session.commit()
        return True
    return False

def actualizar_usuario(id_usuario, datos):
    datos_validados = usuarios_schema.load(datos, partial=True)
    usuario = Usuario.query.get(id_usuario)
    if not usuario:
        return None
    usuario.nombre = datos_validados.get('nombre', usuario.nombre)
    usuario.apellido = datos_validados.get('apellido', usuario.apellido)
    usuario.email = datos_validados.get('email', usuario.email)

    if 'contrasena' in datos_validados:
        usuario.contrasena = generate_password_hash(datos_validados['contrasena'])
    usuario.nacionalidad = datos_validados.get('nacionalidad', usuario.nacionalidad)
    usuario.foto = datos_validados.get('foto', usuario.foto)
    db.session.commit()
    return usuario

def obtener_o_crear_usuario_google(userinfo):
    email = userinfo.get('email')
    google_id = userinfo.get('sub')
    usuario = Usuario.query.filter_by(email=email).first()
    if usuario:
        if not usuario.google_id:
            usuario.google_id = google_id
            usuario.auth_provider = 'google'
            db.session.commit()
        return usuario

    nuevo_usuario = Usuario(
        nombre=userinfo.get('given_name', ''),
        apellido=userinfo.get('family_name', ''),
        email=email,
        google_id=google_id,
        auth_provider='google',
        foto=userinfo.get('picture')
    )
    db.session.add(nuevo_usuario)
    db.session.commit()
    return nuevo_usuario
