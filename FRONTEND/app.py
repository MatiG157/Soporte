from datetime import datetime, date
from datetime import timedelta
import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from dotenv import load_dotenv
import requests

load_dotenv()


app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')
# Sesion dura para siempre o mucho tiempo
app.permanent_session_lifetime = timedelta(days=365)

# URL base del backend
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:5000')


# ─── Rutas principales ────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Landing page / Home"""
    # Pasamos el user_id para que Jinja sepa si está logueado o no
    return render_template('index.html', user_id=session.get('user_id'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registro de usuario"""
    if request.method == 'POST':
        datos = {
            'nombre':       request.form.get('nombre'),
            'apellido':     request.form.get('apellido'),
            'email':        request.form.get('email'),
            'contrasena':   request.form.get('contrasena'),
            'nacionalidad': request.form.get('nacionalidad'),
        }
        try:
            resp = requests.post(f'{BACKEND_URL}/usuarios/', json=datos)
            if resp.status_code == 201:
                return redirect(url_for('login'))
            error = resp.json().get('error') or resp.json().get('errores_validacion')
            return render_template('register.html', error=error)
        except requests.exceptions.ConnectionError:
            return render_template('register.html', error='No se pudo conectar con el servidor.')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login de usuario"""
    if request.method == 'POST':
        # Soporte para fetch (JSON) o form subido normal
        data = request.get_json() if request.is_json else request.form
        email = data.get('email')
        contrasena = data.get('contrasena')
        try:
            resp = requests.post(
                f'{BACKEND_URL}/usuarios/login', json={'email': email, 'contrasena': contrasena})
            if resp.status_code == 200:
                user_data = resp.json()
                session.permanent = True  # Hace que la sesion sea permanente
                session['user_email'] = email
                session['user_id'] = user_data.get('id_usuario')
                if request.is_json:
                    return jsonify({"success": True})
                # dashboard or whatever main route
                return redirect(url_for('compare'))
            else:
                error = resp.json().get('error', 'Credenciales inválidas')
                if request.is_json:
                    return jsonify({"error": error}), 401
                return render_template('login.html', error=error)
        except requests.exceptions.ConnectionError:
            if request.is_json:
                return jsonify({"error": 'No se pudo conectar con el servidor.'}), 500
            return render_template('login.html', error='No se pudo conectar con el servidor.')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/settings')
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('settings.html')


@app.route('/mytrips')
def mytrips():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    viajes = []

    try:
        resp = requests.get(f'{BACKEND_URL}/viajes/usuario/{user_id}')
        if resp.status_code == 200:
            viajes_data = resp.json()
            # Filip status guardado
            viajes_guardados = [
                v for v in viajes_data if v.get('estado') == 'guardado']

            hoy = date.today()

            # Ordenar por fecha de inicio descendente (mayor a la izquierda)
            viajes_guardados.sort(key=lambda x: datetime.fromisoformat(x['fecha_inicio']).date() if x.get('fecha_inicio') else date.min, reverse=True)

            # Para identificar last trip y upcoming trip, encontramos los candidatos
            last_trip = None
            upcoming_trip = None
            
            # Buscar last trip: end date más cercano a hoy en el pasado (máxima f_fin < hoy)
            past_trips = [v for v in viajes_guardados if datetime.fromisoformat(v['fecha_fin']).date() < hoy]
            if past_trips:
                last_trip = max(past_trips, key=lambda x: datetime.fromisoformat(x['fecha_fin']).date())
                
            # Buscar upcoming trip: start date más cercano en el futuro (mínima f_inicio > hoy)
            future_trips = [v for v in viajes_guardados if datetime.fromisoformat(v['fecha_inicio']).date() > hoy]
            if future_trips:
                upcoming_trip = min(future_trips, key=lambda x: datetime.fromisoformat(x['fecha_inicio']).date())

            for v in viajes_guardados:
                f_inicio = datetime.fromisoformat(v['fecha_inicio']).date()
                f_fin = datetime.fromisoformat(v['fecha_fin']).date()

                es_last = (v == last_trip)
                es_upcoming = (v == upcoming_trip)
                es_current = (f_inicio <= hoy <= f_fin)

                # Definimos el flag fundamental de estado para el filtro
                if f_fin < hoy:
                    v['filter_class'] = 'past-trip'
                    v['is_past'] = True
                elif f_inicio > hoy:
                    v['filter_class'] = 'next-trip'
                    v['is_past'] = False
                else:
                    v['filter_class'] = 'current-trip'
                    v['is_past'] = False

                # Asignamos la etiqueta
                if es_current:
                    v['status_label'] = 'current trip'
                elif es_upcoming:
                    v['status_label'] = 'upcoming trip'
                elif es_last:
                    v['status_label'] = 'last trip'
                else:
                    v['status_label'] = ''

                v['fecha_inicio'] = f_inicio.strftime('%d/%m/%Y')
                v['fecha_fin'] = f_fin.strftime('%d/%m/%Y')

                # Formatear destinos para display
                v['destinos_display'] = ' → '.join(v.get('destinos', []))

            viajes = viajes_guardados

    except requests.exceptions.ConnectionError:
        pass

    return render_template('mytrips.html', viajes=viajes)


@app.route('/compare')
def compare():
    if 'user_id' not in session:
        # Prevent default 1 if not logged in
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    drafts = []
    try:
        resp = requests.get(f'{BACKEND_URL}/viajes/usuario/{user_id}/drafts')
        if resp.status_code == 200:
            drafts = resp.json()
    except requests.exceptions.ConnectionError:
        pass

    if not drafts:
        return redirect(url_for('index'))

    # Organizar drafts por tipo_viaje
    viajes_por_tipo = {
        'Economy': None,
        'Balanced': None,
        'Luxury': None
    }
    for draft in drafts:
        if draft.get('tipo_viaje') in viajes_por_tipo:
            viajes_por_tipo[draft.get('tipo_viaje')] = draft

    return render_template('compare.html', viajes_por_tipo=viajes_por_tipo)


@app.route('/generate_trips', methods=['GET'])
def generate_trips():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    # Obtener parámetros del query
    destino = request.args.get('destino')
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')

    # Crear 3 opciones genéricas
    opciones = [
        {
            "destinos": [destino] if destino else ["Destino Desconocido"],
            "fecha_inicio": fecha_inicio or "2024-01-01",
            "fecha_fin": fecha_fin or "2024-01-07",
            "tipo": "Economy",
            "costo_total_estimado": 1000.0,
            "itinerario": [
                {
                    "dia": 1,
                    "resumen": "Llegada y exploración económica",
                    "actividades": [
                        {"nombre": "Paseo por el centro", "descripcion": "Caminata por el centro de la ciudad", "precio_estimado": 0.0, "categoria": "Caminata", "horario_sugerido": "10:00 - 12:00", "ubicacion": "Centro"},
                        {"nombre": "Cena callejera", "descripcion": "Cena en un puesto callejero", "precio_estimado": 10.0, "categoria": "Gastronomía", "horario_sugerido": "20:00 - 21:00", "ubicacion": "Plaza Central"}
                    ]
                },
                {
                    "dia": 2,
                    "resumen": "Trekking y picnic",
                    "actividades": [
                        {"nombre": "Trekking al cerro", "descripcion": "Subida a la montaña cercana", "precio_estimado": 5.0, "categoria": "Deporte", "horario_sugerido": "08:00 - 14:00", "ubicacion": "Cerro local"},
                        {"nombre": "Picnic en el parque", "descripcion": "Comida al aire libre", "precio_estimado": 15.0, "categoria": "Gastronomía", "horario_sugerido": "14:30 - 16:00", "ubicacion": "Parque de la ciudad"}
                    ]
                },
                {
                    "dia": 3,
                    "resumen": "Día de museos y despedida",
                    "actividades": [
                        {"nombre": "Museo gratuito", "descripcion": "Visita al museo histórico", "precio_estimado": 0.0, "categoria": "Cultural", "horario_sugerido": "10:00 - 13:00", "ubicacion": "Museo"},
                        {"nombre": "Feria artesanal", "descripcion": "Compra de regalos económicos", "precio_estimado": 20.0, "categoria": "Compras", "horario_sugerido": "16:00 - 18:00", "ubicacion": "Feria central"}
                    ]
                }
            ]
        },
        {
            "destinos": [destino] if destino else ["Destino Desconocido"],
            "fecha_inicio": fecha_inicio or "2024-01-01",
            "fecha_fin": fecha_fin or "2024-01-07",
            "tipo": "Balanced",
            "costo_total_estimado": 2500.0,
            "itinerario": [
                {
                    "dia": 1,
                    "resumen": "Llegada y tour guiado",
                    "actividades": [
                        {"nombre": "Tour de la ciudad", "descripcion": "Tour guiado por los principales puntos", "precio_estimado": 25.0, "categoria": "Turismo", "horario_sugerido": "10:00 - 13:00", "ubicacion": "Centro"},
                        {"nombre": "Cena en restaurante", "descripcion": "Cena en restaurante local tradicional", "precio_estimado": 40.0, "categoria": "Gastronomía", "horario_sugerido": "20:00 - 22:00", "ubicacion": "Restaurante típico"}
                    ]
                },
                {
                    "dia": 2,
                    "resumen": "Aventura y relax",
                    "actividades": [
                        {"nombre": "Alquiler de bicicletas", "descripcion": "Recorrido en bici por la costa", "precio_estimado": 20.0, "categoria": "Deporte", "horario_sugerido": "09:00 - 12:00", "ubicacion": "Costanera"},
                        {"nombre": "Tarde en museo", "descripcion": "Visita al museo de arte moderno", "precio_estimado": 15.0, "categoria": "Cultural", "horario_sugerido": "15:00 - 18:00", "ubicacion": "Museo de Arte"}
                    ]
                },
                {
                    "dia": 3,
                    "resumen": "Excursión y compras",
                    "actividades": [
                        {"nombre": "Excursión grupal", "descripcion": "Salida a las afueras de la ciudad", "precio_estimado": 50.0, "categoria": "Aventura", "horario_sugerido": "08:00 - 14:00", "ubicacion": "Afueras"},
                        {"nombre": "Shopping", "descripcion": "Visita a centro comercial", "precio_estimado": 50.0, "categoria": "Compras", "horario_sugerido": "16:00 - 19:00", "ubicacion": "Shopping Mall"}
                    ]
                }
            ]
        },
        {
            "destinos": [destino] if destino else ["Destino Desconocido"],
            "fecha_inicio": fecha_inicio or "2024-01-01",
            "fecha_fin": fecha_fin or "2024-01-07",
            "tipo": "Luxury",
            "costo_total_estimado": 5000.0,
            "itinerario": [
                {
                    "dia": 1,
                    "resumen": "Recepción VIP y cena gourmet",
                    "actividades": [
                        {"nombre": "Recepción en el hotel", "descripcion": "Bienvenida y spa", "precio_estimado": 150.0, "categoria": "Relax", "horario_sugerido": "14:00 - 17:00", "ubicacion": "Hotel 5 estrellas"},
                        {"nombre": "Cena de autor", "descripcion": "Cena degustación en restaurante exclusivo", "precio_estimado": 200.0, "categoria": "Gastronomía", "horario_sugerido": "21:00 - 23:30", "ubicacion": "Restaurante Gourmet"}
                    ]
                },
                {
                    "dia": 2,
                    "resumen": "Tour privado y yate",
                    "actividades": [
                        {"nombre": "Tour privado con chofer", "descripcion": "Recorrido VIP por sitios históricos", "precio_estimado": 300.0, "categoria": "Turismo", "horario_sugerido": "10:00 - 14:00", "ubicacion": "La ciudad"},
                        {"nombre": "Paseo en Yate", "descripcion": "Atardecer en yate con champagne", "precio_estimado": 500.0, "categoria": "Exclusivo", "horario_sugerido": "16:00 - 19:00", "ubicacion": "Puerto"}
                    ]
                },
                {
                    "dia": 3,
                    "resumen": "Día de compras exclusivas",
                    "actividades": [
                        {"nombre": "Personal shopper", "descripcion": "Compras guiadas en boutiques", "precio_estimado": 1000.0, "categoria": "Compras", "horario_sugerido": "10:00 - 14:00", "ubicacion": "Avenida principal"},
                        {"nombre": "Cena despedida", "descripcion": "Cena en un lugar emblemático", "precio_estimado": 180.0, "categoria": "Gastronomía", "horario_sugerido": "20:30 - 23:00", "ubicacion": "Terraza Skyline"}
                    ]
                }
            ]
        }
    ]

    datos = {
        "id_usuario": user_id,
        "opciones": opciones
    }

    try:
        requests.post(f'{BACKEND_URL}/viajes/generate', json=datos)
    except requests.exceptions.ConnectionError:
        pass

    return redirect(url_for('compare'))


@app.route('/create_trip', methods=['POST'])
def create_trip():
    """Receives trip form data as JSON, saves preferences, generates trips, redirects to compare."""
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 401

    user_id = session.get('user_id')
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    destinos = data.get('destinos', [])
    if not destinos:
        return jsonify({"error": "At least one destination is required"}), 400

    # 1) Save user preferences
    preferencias = {
        'id_usuario': user_id,
        'destinos': destinos,
        'origen': data.get('origen'),
        'costo_min': data.get('costo_min'),
        'costo_max': data.get('costo_max'),
        'cantidad_personas': data.get('cantidad_personas'),
        'grupo': data.get('grupo'),
        'edades_viajeros': data.get('edades_viajeros'),
        'hospedaje': data.get('hospedaje'),
        'tipo_transporte': data.get('tipo_transporte'),
        'fecha_inicio': data.get('fecha_inicio'),
        'fecha_fin': data.get('fecha_fin'),
        'act_preferidas': data.get('act_preferidas'),
        'otros': data.get('otros'),
    }

    id_preferencia = None
    try:
        resp_pref = requests.post(f'{BACKEND_URL}/preferencias/', json=preferencias)
        if resp_pref.status_code == 201:
            id_preferencia = resp_pref.json().get('id')
    except requests.exceptions.ConnectionError:
        pass

    # 2) Generate 3 trip options
    fecha_inicio = data.get('fecha_inicio') or '2024-01-01'
    fecha_fin = data.get('fecha_fin') or '2024-01-07'
    destino_display = ', '.join(destinos)

    opciones = [
        {
            "destinos": destinos,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "tipo": "Economy",
            "costo_total_estimado": 1000.0,
            "itinerario": [
                {
                    "dia": 1,
                    "resumen": "Llegada y exploración económica",
                    "actividades": [
                        {"nombre": "Paseo por el centro", "descripcion": "Caminata por el centro de la ciudad", "precio_estimado": 0.0, "categoria": "Caminata", "horario_sugerido": "10:00 - 12:00", "ubicacion": "Centro"},
                        {"nombre": "Cena callejera", "descripcion": "Cena en un puesto callejero", "precio_estimado": 10.0, "categoria": "Gastronomía", "horario_sugerido": "20:00 - 21:00", "ubicacion": "Plaza Central"}
                    ]
                },
                {
                    "dia": 2,
                    "resumen": "Trekking y picnic",
                    "actividades": [
                        {"nombre": "Trekking al cerro", "descripcion": "Subida a la montaña cercana", "precio_estimado": 5.0, "categoria": "Deporte", "horario_sugerido": "08:00 - 14:00", "ubicacion": "Cerro local"},
                        {"nombre": "Picnic en el parque", "descripcion": "Comida al aire libre", "precio_estimado": 15.0, "categoria": "Gastronomía", "horario_sugerido": "14:30 - 16:00", "ubicacion": "Parque de la ciudad"}
                    ]
                },
                {
                    "dia": 3,
                    "resumen": "Día de museos y despedida",
                    "actividades": [
                        {"nombre": "Museo gratuito", "descripcion": "Visita al museo histórico", "precio_estimado": 0.0, "categoria": "Cultural", "horario_sugerido": "10:00 - 13:00", "ubicacion": "Museo"},
                        {"nombre": "Feria artesanal", "descripcion": "Compra de regalos económicos", "precio_estimado": 20.0, "categoria": "Compras", "horario_sugerido": "16:00 - 18:00", "ubicacion": "Feria central"}
                    ]
                }
            ]
        },
        {
            "destinos": destinos,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "tipo": "Balanced",
            "costo_total_estimado": 2500.0,
            "itinerario": [
                {
                    "dia": 1,
                    "resumen": "Llegada y tour guiado",
                    "actividades": [
                        {"nombre": "Tour de la ciudad", "descripcion": "Tour guiado por los principales puntos", "precio_estimado": 25.0, "categoria": "Turismo", "horario_sugerido": "10:00 - 13:00", "ubicacion": "Centro"},
                        {"nombre": "Cena en restaurante", "descripcion": "Cena en restaurante local tradicional", "precio_estimado": 40.0, "categoria": "Gastronomía", "horario_sugerido": "20:00 - 22:00", "ubicacion": "Restaurante típico"}
                    ]
                },
                {
                    "dia": 2,
                    "resumen": "Aventura y relax",
                    "actividades": [
                        {"nombre": "Alquiler de bicicletas", "descripcion": "Recorrido en bici por la costa", "precio_estimado": 20.0, "categoria": "Deporte", "horario_sugerido": "09:00 - 12:00", "ubicacion": "Costanera"},
                        {"nombre": "Tarde en museo", "descripcion": "Visita al museo de arte moderno", "precio_estimado": 15.0, "categoria": "Cultural", "horario_sugerido": "15:00 - 18:00", "ubicacion": "Museo de Arte"}
                    ]
                },
                {
                    "dia": 3,
                    "resumen": "Excursión y compras",
                    "actividades": [
                        {"nombre": "Excursión grupal", "descripcion": "Salida a las afueras de la ciudad", "precio_estimado": 50.0, "categoria": "Aventura", "horario_sugerido": "08:00 - 14:00", "ubicacion": "Afueras"},
                        {"nombre": "Shopping", "descripcion": "Visita a centro comercial", "precio_estimado": 50.0, "categoria": "Compras", "horario_sugerido": "16:00 - 19:00", "ubicacion": "Shopping Mall"}
                    ]
                }
            ]
        },
        {
            "destinos": destinos,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "tipo": "Luxury",
            "costo_total_estimado": 5000.0,
            "itinerario": [
                {
                    "dia": 1,
                    "resumen": "Recepción VIP y cena gourmet",
                    "actividades": [
                        {"nombre": "Recepción en el hotel", "descripcion": "Bienvenida y spa", "precio_estimado": 150.0, "categoria": "Relax", "horario_sugerido": "14:00 - 17:00", "ubicacion": "Hotel 5 estrellas"},
                        {"nombre": "Cena de autor", "descripcion": "Cena degustación en restaurante exclusivo", "precio_estimado": 200.0, "categoria": "Gastronomía", "horario_sugerido": "21:00 - 23:30", "ubicacion": "Restaurante Gourmet"}
                    ]
                },
                {
                    "dia": 2,
                    "resumen": "Tour privado y yate",
                    "actividades": [
                        {"nombre": "Tour privado con chofer", "descripcion": "Recorrido VIP por sitios históricos", "precio_estimado": 300.0, "categoria": "Turismo", "horario_sugerido": "10:00 - 14:00", "ubicacion": "La ciudad"},
                        {"nombre": "Paseo en Yate", "descripcion": "Atardecer en yate con champagne", "precio_estimado": 500.0, "categoria": "Exclusivo", "horario_sugerido": "16:00 - 19:00", "ubicacion": "Puerto"}
                    ]
                },
                {
                    "dia": 3,
                    "resumen": "Día de compras exclusivas",
                    "actividades": [
                        {"nombre": "Personal shopper", "descripcion": "Compras guiadas en boutiques", "precio_estimado": 1000.0, "categoria": "Compras", "horario_sugerido": "10:00 - 14:00", "ubicacion": "Avenida principal"},
                        {"nombre": "Cena despedida", "descripcion": "Cena en un lugar emblemático", "precio_estimado": 180.0, "categoria": "Gastronomía", "horario_sugerido": "20:30 - 23:00", "ubicacion": "Terraza Skyline"}
                    ]
                }
            ]
        }
    ]

    datos_viajes = {
        "id_usuario": user_id,
        "opciones": opciones,
        "id_user_preferences": id_preferencia
    }

    try:
        requests.post(f'{BACKEND_URL}/viajes/generate', json=datos_viajes)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to backend"}), 500

    return jsonify({"redirect": url_for('compare')})

@app.route('/select_trip/<int:id_viaje>', methods=['POST'])
def select_trip(id_viaje):
    try:
        resp = requests.post(f'{BACKEND_URL}/viajes/{id_viaje}/select')
        if resp.status_code == 200:
            return redirect(url_for('itinerary', id_viaje=id_viaje))
    except requests.exceptions.ConnectionError:
        pass
    return redirect(url_for('compare'))


@app.route('/itinerary/<int:id_viaje>')
def itinerary(id_viaje):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        resp = requests.get(f'{BACKEND_URL}/viajes/{id_viaje}')
        if resp.status_code == 200:
            viaje = resp.json()
            
            # Format dates for frontend
            if 'fecha_inicio' in viaje:
                dt_inicio = datetime.fromisoformat(viaje['fecha_inicio'])
                viaje['fecha_inicio_fmt'] = dt_inicio.strftime('%b %d')
            if 'fecha_fin' in viaje:
                dt_fin = datetime.fromisoformat(viaje['fecha_fin'])
                viaje['fecha_fin_fmt'] = dt_fin.strftime('%b %d')
                
            # Format destinos for display
            if 'destinos' in viaje:
                viaje['destinos_display'] = ' → '.join(viaje.get('destinos', []))
                
            # Calcular las fechas por día del itinerario
            if 'itinerarios' in viaje and 'fecha_inicio' in viaje:
                for idx, itin in enumerate(viaje['itinerarios']):
                    dt_dia = dt_inicio + timedelta(days=idx)
                    itin['fecha_fmt'] = dt_dia.strftime('%b %d')
                    
            # Si no hay imagen
            if 'imagen' not in viaje or not viaje['imagen']:
                viaje['imagen'] = "https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80"
                
            return render_template('itinerary.html', viaje=viaje)
        else:
            return f"Error: no se pudo cargar el viaje ({resp.status_code}). Verifica consola del backend.", 500
    except requests.exceptions.ConnectionError:
        return "Error: no se pudo conectar al Backend.", 500

@app.route('/planificar', methods=['GET', 'POST'])
def planificar():
    """Formulario para planificar un nuevo viaje con IA"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        preferencias = {
            'destino':           request.form.get('destino'),
            'fecha_inicio':      request.form.get('fecha_inicio'),
            'fecha_fin':         request.form.get('fecha_fin'),
            'costo_max':         float(request.form.get('costo_max', 0)),
            'cantidad_personas': int(request.form.get('cantidad_personas', 1)),
            'grupo':             request.form.get('grupo'),
            'clima':             request.form.get('clima'),
            'otros':             request.form.get('otros'),
        }
        try:
            resp = requests.post(
                f'{BACKEND_URL}/api/recommendations/generate',
                json=preferencias
            )
            if resp.status_code == 200:
                recomendaciones = resp.json().get('data', [])
                return render_template('resultados.html',
                                       recomendaciones=recomendaciones,
                                       preferencias=preferencias)
            error = resp.json().get('error', 'Error al generar recomendaciones.')
            return render_template('planificar.html', error=error)
        except requests.exceptions.ConnectionError:
            return render_template('planificar.html',
                                   error='No se pudo conectar con el servidor.')

    # Cargar tipos de alojamiento para el formulario
    tipos_alojamiento = []
    try:
        resp = requests.get(f'{BACKEND_URL}/tipos_alojamiento/')
        if resp.status_code == 200:
            tipos_alojamiento = resp.json()
    except requests.exceptions.ConnectionError:
        pass

    return render_template('planificar.html', tipos_alojamiento=tipos_alojamiento)


@app.route('/viaje/<int:id_viaje>')
def detalle_viaje(id_viaje):
    """Detalle de un viaje: itinerario, costos y actividades"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    viaje, costos, itinerarios = None, None, []
    try:
        r_viaje = requests.get(f'{BACKEND_URL}/viajes/{id_viaje}')
        if r_viaje.status_code == 200:
            viaje = r_viaje.json()

        r_costos = requests.get(f'{BACKEND_URL}/costos/viajes/{id_viaje}')
        if r_costos.status_code == 200:
            costos = r_costos.json()

        r_itin = requests.get(f'{BACKEND_URL}/itinerarios/viaje/{id_viaje}')
        if r_itin.status_code == 200:
            itinerarios = r_itin.json()
    except requests.exceptions.ConnectionError:
        pass

    return render_template('detalle_viaje.html',
                           viaje=viaje,
                           costos=costos,
                           itinerarios=itinerarios)


# ─── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, port=8080)
