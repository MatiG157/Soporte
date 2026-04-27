from flask import Blueprint, request, jsonify
from src.services.user_preferences_service import crear_preferencia, eliminar_preferencia, actualizar_preferencia, obtener_preferencias_por_usuario
from marshmallow import ValidationError
from validators.user_preferences_validator import user_preferences_schema

user_preferences_bp = Blueprint('user_preferences_bp', __name__)

@user_preferences_bp.route('/usuario/<int:id_usuario>', methods=['GET'])
def get_preferencias_usuario(id_usuario):
    preferencias = obtener_preferencias_por_usuario(id_usuario)
    if not preferencias:
        return jsonify([]), 200
        
    resultado = user_preferences_schema.dump(preferencias, many=True)
    return jsonify(resultado), 200

@user_preferences_bp.route('/', methods=['POST'])
def alta_preferencia():
    datos = request.get_json()
    
    if not datos:
        return jsonify({"error": "No se enviaron datos para crear las preferencias"}), 400
        
    try:
        nueva_preferencia = crear_preferencia(datos)
        return jsonify({
            "mensaje": "Preferencias creadas con éxito", 
            "id": nueva_preferencia.id_preferencia
        }), 201
        
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@user_preferences_bp.route('/<int:id_preferencia>', methods=['DELETE'])
def baja_preferencia(id_preferencia):
    if eliminar_preferencia(id_preferencia):
        return jsonify({"mensaje": "Preferencias eliminadas exitosamente"}), 200
    return jsonify({"error": "Preferencias no encontradas"}), 404

@user_preferences_bp.route('/<int:id_preferencia>', methods=['PUT'])
def modificar_preferencia(id_preferencia):
    datos = request.get_json()
    
    if not datos:
        return jsonify({"error": "No se enviaron datos para actualizar"}), 400
        
    try:
        pref_actualizada = actualizar_preferencia(id_preferencia, datos)
        
        if not pref_actualizada:
            return jsonify({"error": "Preferencias no encontradas"}), 404
            
        return jsonify({
            "mensaje": f"Preferencias con ID {id_preferencia} actualizadas con éxito",
            "id": pref_actualizada.id_preferencia
        }), 200
        
    except ValidationError as err:
        return jsonify({"errores_validacion": err.messages}), 400
    except Exception as e:
        return jsonify({"error": f"Ocurrió un error interno: {str(e)}"}), 500