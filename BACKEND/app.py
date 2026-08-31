import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

from src.auth import verificar_api_key
from src.models.init import db
from src.routes.accommodation_types_routes import accommodation_types_bp
from src.routes.activity_routes import activity_bp
from src.routes.ai_recommendation_routes import ai_recommendation_bp
from src.routes.cost_routes import cost_bp
from src.routes.itinerary_routes import itinerary_bp
from src.routes.trip_routes import trip_bp
from src.routes.user_preferences_routes import user_preferences_bp
from src.routes.user_routes import user_bp

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def crear_app():
    app = Flask(__name__)

    # Sólo el frontend puede llamar a esta API desde el navegador.
    origenes = os.getenv("CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080")
    CORS(app, origins=[o.strip() for o in origenes.split(",") if o.strip()])

    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD", "")
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME")
    db_port = os.getenv("DB_PORT", "3306")

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Toda la API queda detrás de la API key compartida con el frontend.
    app.before_request(verificar_api_key)

    app.register_blueprint(user_bp, url_prefix="/usuarios")
    app.register_blueprint(user_preferences_bp, url_prefix="/preferencias")
    app.register_blueprint(cost_bp, url_prefix="/costos")
    app.register_blueprint(activity_bp, url_prefix="/actividades")
    app.register_blueprint(accommodation_types_bp, url_prefix="/tipos_alojamiento")
    app.register_blueprint(trip_bp, url_prefix="/viajes")
    app.register_blueprint(itinerary_bp, url_prefix="/itinerarios")
    app.register_blueprint(ai_recommendation_bp, url_prefix="/api/recommendations")

    db.init_app(app)

    @app.route("/")
    def index():
        return jsonify({"mensaje": "TravelPlanner API operativa"})

    @app.route("/health")
    def health():
        try:
            db.session.execute(db.text("SELECT 1"))
            return jsonify({"estado": "ok", "base_de_datos": "ok"}), 200
        except Exception as exc:
            logger.error("Health check falló: %s", exc)
            return jsonify({"estado": "degradado", "base_de_datos": str(exc)}), 503

    @app.errorhandler(404)
    def no_encontrado(_e):
        return jsonify({"error": "Recurso no encontrado"}), 404

    @app.errorhandler(405)
    def metodo_no_permitido(_e):
        return jsonify({"error": "Método no permitido"}), 405

    @app.errorhandler(500)
    def error_interno(e):
        logger.exception("Error interno no controlado: %s", e)
        return jsonify({"error": "Error interno del servidor"}), 500

    return app


app = crear_app()


def preparar_base():
    """Crea las tablas que falten y aplica las migraciones pendientes.

    Se hace al arrancar a propósito: después de un `git pull` nadie tiene que
    acordarse de correr `migrate.py` a mano. Las migraciones son idempotentes,
    así que en un arranque normal no hacen nada.
    """
    try:
        with app.app_context():
            db.create_all()
    except Exception as exc:
        # Sin base el servidor igual arranca: /health reporta el problema y el
        # mensaje dice qué revisar, en vez de morir con un stacktrace de pymysql.
        logger.error(
            "No se pudo conectar a la base de datos: %s. "
            "Revisá que MySQL esté levantado y que DB_USER/DB_PASSWORD/DB_NAME "
            "de BACKEND/.env sean correctos. La API va a responder 503 en /health.",
            exc,
        )
        return

    if os.getenv("AUTO_MIGRATE", "true").lower() != "true":
        logger.info("AUTO_MIGRATE=false: las migraciones no se aplican solas.")
        return

    try:
        from migrate import aplicar_pendientes
        aplicadas = aplicar_pendientes(silencioso=True)
    except Exception as exc:
        logger.error(
            "FALLARON LAS MIGRACIONES: %s. La base quedó con el esquema viejo y "
            "las consultas van a fallar. Corré 'python migrate.py' para ver el detalle.",
            exc,
        )
        return

    if aplicadas is None:
        logger.warning("No hay conexión a la base: no se pudo verificar el esquema.")
        return
    if aplicadas:
        logger.info("Migraciones aplicadas: %s", ", ".join(aplicadas))
    else:
        logger.info("El esquema de la base está al día.")

    verificar_esquema()


def verificar_esquema():
    """Avisa si algún modelo tiene columnas que la base no tiene.

    Sin esto, una migración que falta o que falló se manifiesta recién al primer
    request, como un "Unknown column 'viajes.titulo'" que no dice qué hacer.
    """
    from sqlalchemy import inspect

    try:
        with app.app_context():
            inspector = inspect(db.engine)
            tablas_en_la_base = set(inspector.get_table_names())

            faltantes = []
            for tabla in db.metadata.sorted_tables:
                if tabla.name not in tablas_en_la_base:
                    faltantes.append(f"{tabla.name} (la tabla entera)")
                    continue
                columnas = {c["name"] for c in inspector.get_columns(tabla.name)}
                for col in tabla.columns:
                    if col.name not in columnas:
                        faltantes.append(f"{tabla.name}.{col.name}")
    except Exception as exc:
        logger.warning("No se pudo verificar el esquema: %s", exc)
        return

    if not faltantes:
        return

    logger.error(
        "LA BASE NO COINCIDE CON LOS MODELOS. Falta en la base: %s. "
        "Las consultas van a fallar con 'Unknown column'. "
        "Corré 'python migrate.py' y mirá qué migración falla.",
        ", ".join(faltantes),
    )


if __name__ == "__main__":
    if not os.getenv("API_KEY"):
        logger.error(
            "API_KEY no está definida en BACKEND/.env: la API va a rechazar TODAS "
            "las peticiones y no vas a poder ni registrarte ni loguearte. "
            "Corré 'python setup.py' desde la raíz del proyecto para generarla."
        )

    preparar_base()

    app.run(
        debug=os.getenv("FLASK_DEBUG", "true").lower() == "true",
        port=int(os.getenv("PORT", 5000)),
    )
