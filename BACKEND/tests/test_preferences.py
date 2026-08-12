import unittest
from app import app
from src.models.init import db
from src.models.user_preferences import PreferenciasUsuario
from src.models.user import Usuario

class TestPreferencesAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True
        self.app_context = app.app_context()
        self.app_context.push()

        # Ensure we have a user to associate the preferences with (FK constraint)
        self.test_user = Usuario.query.filter_by(email='testpref@example.com').first()
        if not self.test_user:
            self.test_user = Usuario(
                nombre='Test',
                apellido='User',
                email='testpref@example.com',
                contrasena='hashedpass123'
            )
            db.session.add(self.test_user)
            db.session.commit()

    def tearDown(self):
        # Cleanup any preferences created during the test
        prefs = PreferenciasUsuario.query.filter_by(id_usuario=self.test_user.id_usuario).all()
        for pref in prefs:
            db.session.delete(pref)
        
        # Cleanup the test user
        if self.test_user:
            db.session.delete(self.test_user)
        
        db.session.commit()
        self.app_context.pop()

    def test_post_preferences_success_db(self):
        # The frontend will have filtered out any empty strings and nulls
        payload = {
            "id_usuario": self.test_user.id_usuario,
            "destinos": ["TestCity1", "TestCity2"],
            "origen": "Mendoza",
            "costo_min": 500,
            "costo_max": 2000,
            "cantidad_personas": 2,
            "grupo": "amigos",
            "fecha_inicio": "2026-10-10",
            "fecha_fin": "2026-10-20"
        }

        # Validate initial state
        initial_count = PreferenciasUsuario.query.filter_by(id_usuario=self.test_user.id_usuario).count()
        self.assertEqual(initial_count, 0)

        # Execute POST
        response = self.client.post('/preferencias/', json=payload)
        
        # Verify response
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("mensaje", data)
        
        pref_id = data["id"]
        self.assertIsNotNone(pref_id)

        # Check DB to verify it was actually saved
        pref_in_db = PreferenciasUsuario.query.get(pref_id)
        self.assertIsNotNone(pref_in_db)
        self.assertEqual(pref_in_db.origen, "Mendoza")
        self.assertEqual(pref_in_db.destinos, ["TestCity1", "TestCity2"])
        self.assertEqual(pref_in_db.costo_min, 500)
        self.assertEqual(pref_in_db.id_usuario, self.test_user.id_usuario)

    def test_post_preferences_missing_required_fields(self):
        # Missing id_usuario and destinos, which are required
        payload = {
            "origen": "Mendoza",
            "costo_max": 2000
        }

        response = self.client.post('/preferencias/', json=payload)
        
        # Should fail with 400 validation error
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("errores_validacion", data)
        self.assertIn("id_usuario", data["errores_validacion"])

if __name__ == '__main__':
    unittest.main()
