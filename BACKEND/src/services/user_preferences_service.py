from src.models.init import db
from src.models.user_preferences import PreferenciasUsuario
from validators.user_preferences_validator import user_preferences_schema
from src.models.accommodation_type import TipoAlojamiento

def crear_preferencia(datos):
    datos_validados = user_preferences_schema.load(datos)

    # Extraemos la lista de IDs (si no viene, queda como lista vacía)
    ids_alojamientos = datos_validados.get('tipos_alojamiento', [])

    
    nueva_preferencia = PreferenciasUsuario(
        id_usuario=datos_validados['id_usuario'],
        destino=datos_validados.get('destino'),
        costo_min=datos_validados.get('costo_min'),
        costo_max=datos_validados.get('costo_max'),
        cantidad_personas=datos_validados.get('cantidad_personas'),
        grupo=datos_validados.get('grupo'),
        clima=datos_validados.get('clima'),
        edades_viajeros=datos_validados.get('edades_viajeros'),
        tipo_transporte=datos_validados.get('tipo_transporte'),
        fecha_inicio=datos_validados.get('fecha_inicio'),
        fecha_fin=datos_validados.get('fecha_fin'),
        otros=datos_validados.get('otros')
    )

    # Buscamos los alojamientos en la base de datos y los asociamos
    if ids_alojamientos:
        alojamientos_encontrados = TipoAlojamiento.query.filter(TipoAlojamiento.id_tipo.in_(ids_alojamientos)).all()
        nueva_preferencia.tipos_alojamiento = alojamientos_encontrados

    db.session.add(nueva_preferencia)
    db.session.commit()
    return nueva_preferencia

def eliminar_preferencia(id_preferencia):
    preferencia = PreferenciasUsuario.query.get(id_preferencia)
    if preferencia:
        db.session.delete(preferencia)
        db.session.commit()
        return True
    return False

def actualizar_preferencia(id_preferencia, datos):
    # partial=True para soportar actualizaciones parciales en PUT/PATCH
    datos_validados = user_preferences_schema.load(datos, partial=True)
    preferencia = PreferenciasUsuario.query.get(id_preferencia)
    
    if not preferencia:
        return None 
        
    preferencia.destino = datos_validados.get('destino', preferencia.destino)
    preferencia.costo_min = datos_validados.get('costo_min', preferencia.costo_min)
    preferencia.costo_max = datos_validados.get('costo_max', preferencia.costo_max)
    preferencia.cantidad_personas = datos_validados.get('cantidad_personas', preferencia.cantidad_personas)
    preferencia.grupo = datos_validados.get('grupo', preferencia.grupo)
    preferencia.clima = datos_validados.get('clima', preferencia.clima)
    preferencia.edades_viajeros = datos_validados.get('edades_viajeros', preferencia.edades_viajeros)
    preferencia.tipo_transporte = datos_validados.get('tipo_transporte', preferencia.tipo_transporte)
    preferencia.fecha_inicio = datos_validados.get('fecha_inicio', preferencia.fecha_inicio)
    preferencia.fecha_fin = datos_validados.get('fecha_fin', preferencia.fecha_fin)
    preferencia.otros = datos_validados.get('otros', preferencia.otros)

     # Si viene el arreglo en la petición, actualizamos la relación
    if 'tipos_alojamiento' in datos_validados:
        ids_alojamientos = datos_validados['tipos_alojamiento']
        if ids_alojamientos:
            nuevos_alojamientos = TipoAlojamiento.query.filter(TipoAlojamiento.id_tipo.in_(ids_alojamientos)).all()
            preferencia.tipos_alojamiento = nuevos_alojamientos
        else:
            # Si mandan una lista vacía [], le borramos los alojamientos asociados
            preferencia.tipos_alojamiento = []
    
    db.session.commit()
    return preferencia

def obtener_preferencias_por_usuario(id_usuario):
    return PreferenciasUsuario.query.filter_by(id_usuario=id_usuario).all()