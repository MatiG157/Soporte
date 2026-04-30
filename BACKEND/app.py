import os
from flask import Flask
from dotenv import load_dotenv

# Importar 'db' desde src.models.init
from src.models.init import db

# Importar el blueprint de rutas de usuario
from src.routes.user_routes import user_bp
from src.routes.user_preferences_routes import user_preferences_bp
from src.routes.cost_routes import cost_bp

# Cargar las variables del archivo .env
load_dotenv()

app = Flask(__name__)

# Leer las variables de entorno
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD', '') # Cadena vacía por defecto si no hay pass
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')

# Configuramos la conexión a MySQL usando pymysql
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.register_blueprint(user_bp, url_prefix='/usuarios')
app.register_blueprint(user_preferences_bp, url_prefix='/preferencias')
app.register_blueprint(cost_bp, url_prefix='/costos')

# 2. Inicializar la extensión db con la aplicación
db.init_app(app)

@app.route("/")
def index():
    return {"mensaje": "¡Servidor Flask conectado a MySQL correctamente!"}

if __name__ == "__main__":
    # Importante: La base de datos (DB_NAME) ya debe existir en tu MySQL Server.
    # Estas líneas solo crean las tablas, no la base de datos en sí.
    with app.app_context():
        db.create_all() # Al ejecutar esto, se crearán las tablas de los modelos importados en src/models/init.py
    
    app.run(debug=True, port=5000)