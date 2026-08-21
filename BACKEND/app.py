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


if __name__ == "__main__":
    if not os.getenv("API_KEY"):
        logger.warning(
            "API_KEY no está definida en el .env: la API va a rechazar todas las peticiones."
        )

    with app.app_context():
        db.create_all()

    app.run(
        debug=os.getenv("FLASK_DEBUG", "true").lower() == "true",
        port=int(os.getenv("PORT", 5000)),
    )
