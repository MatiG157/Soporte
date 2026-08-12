import unittest
from unittest.mock import patch
from app import app

class TestPreferencesAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    @patch('src.routes.user_preferences_routes.crear_preferencia')
    def test_post_preferences_success(self, mock_crear_preferencia):
        # Configuramos el mock para devolver un objeto simulado
        class MockPref:
            id_preferencia = 999
            
        mock_crear_preferencia.return_value = MockPref()

        payload = {
            "id_usuario": 1,
            "destinos": ["Buenos Aires", "Cordoba"],
            "origen": "Mendoza",
            "costo_min": 500,
            "costo_max": 2000,
            "cantidad_personas": 2,
            "grupo": "amigos",
            "fecha_inicio": "2026-10-10",
            "fecha_fin": "2026-10-20"
        }

        response = self.client.post('/preferencias/', json=payload)
        
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("mensaje", data)
        self.assertEqual(data["id"], 999)
        mock_crear_preferencia.assert_called_once()

    @patch('src.routes.user_preferences_routes.crear_preferencia')
    def test_post_preferences_missing_required_fields(self, mock_crear_preferencia):
        from marshmallow import ValidationError
        mock_crear_preferencia.side_effect = ValidationError({"id_usuario": ["Falta id_usuario"]})
        # Missing id_usuario and destinos, which are required
        payload = {
            "origen": "Mendoza",
            "costo_max": 2000
        }

        response = self.client.post('/preferencias/', json=payload)
        
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("errores_validacion", data)

if __name__ == '__main__':
    unittest.main()
