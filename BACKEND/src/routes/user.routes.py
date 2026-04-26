from flask import Blueprint, request, jsonify
from src.services.user_service import crear_usuario, eliminar_usuario

user_bp = Blueprint('user_bp', __name__)

@user_bp.route('/', methods=['POST'])
def alta_usuario():
    datos = request.get_json()
    try:
        nuevo_user = crear_usuario(datos)
        return jsonify({"mensaje": "Usuario creado con éxito", "id": nuevo_user.id_usuario}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@user_bp.route('/<int:id_usuario>', methods=['DELETE'])
def baja_usuario(id_usuario):
    if eliminar_usuario(id_usuario):
        return jsonify({"mensaje": "Usuario eliminado"}), 200
    return jsonify({"error": "Usuario no encontrado"}), 404


@user_bp.route('/<int:id_usuario>', methods=['PUT'])
def actualizar_usuario(id_usuario):
    # Aquí podrías implementar la lógica para actualizar un usuario por su ID
    return jsonify({"mensaje": f"Actualizar usuario con ID {id_usuario} - Funcionalidad no implementada"}), 200



