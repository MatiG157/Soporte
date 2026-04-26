from flask import Blueprint, request, jsonify
from src.services.user_service import crear_usuario, eliminar_usuario, actualizar_usuario
from marshmallow import ValidationError

user_bp = Blueprint('user_bp', __name__)

@user_bp.route('/', methods=['POST'])
def alta_usuario():
    datos = request.get_json()
    
    if not datos:
        return jsonify({"error": "No se enviaron datos para crear el usuario"}), 400
        
    try:
        nuevo_user = crear_usuario(datos)
        return jsonify({"mensaje": "Usuario creado con éxito", "id": nuevo_user.id_usuario}), 201
        
    except ValidationError as err:
        # Capturamos los errores de faltantes de campos obligatorios 
        # o formatos incorrectos atrapados por Marshmallow
        return jsonify({"errores_validacion": err.messages}), 400
        
    except Exception as e:
        # Cualquier otro tipo de error inesperado
        return jsonify({"error": str(e)}), 400

@user_bp.route('/<int:id_usuario>', methods=['DELETE'])
def baja_usuario(id_usuario):
    if eliminar_usuario(id_usuario):
        return jsonify({"mensaje": "Usuario eliminado"}), 200
    return jsonify({"error": "Usuario no encontrado"}), 404


@user_bp.route('/<int:id_usuario>', methods=['PUT'])
def modificar_usuario(id_usuario):
    datos = request.get_json()
    
    if not datos:
        return jsonify({"error": "No se enviaron datos para actualizar"}), 400
        
    try:
        usuario_actualizado = actualizar_usuario(id_usuario, datos)
        
        if not usuario_actualizado:
            return jsonify({"error": "Usuario no encontrado"}), 404
            
        return jsonify(
            {
                "mensaje": f"Usuario con ID {id_usuario} actualizado con éxito",
                "id": usuario_actualizado.id_usuario
            }
        ), 200
        
    except ValidationError as err:
        # Marshmallow arroja este error si envían un campo con formato incorrecto
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        return jsonify({"error": f"Ocurrió un error interno: {str(e)}"}), 500



