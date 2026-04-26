from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Importar modelos para registrar relaciones
from src.models.user import Usuario
from src.models.user_preferences import PreferenciasUsuario
from src.models.accommodation_type import TipoAlojamiento
from src.models.trip import Viaje
from src.models.cost import Costo
from src.models.itinerary import Itinerario
from src.models.activity import Actividad
from src.models.ai_recommendation import RecomendacionIA