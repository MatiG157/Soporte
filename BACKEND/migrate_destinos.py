import os
import pymysql
from dotenv import load_dotenv

def main():
    load_dotenv()
    
    host = os.getenv("DB_HOST", "localhost")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    database = os.getenv("DB_NAME", "travelplannerbd")
    port = int(os.getenv("DB_PORT", 3306))
    
    print(f"Conectando a DB: {database} en {host}:{port}...")
    
    try:
        connection = pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port
        )
    except Exception as e:
        print(f"Error conectando a la base de datos: {e}")
        return

    try:
        with connection.cursor() as cursor:
            print("Agregando columna 'foto' a 'usuarios'...")
            try:
                cursor.execute("ALTER TABLE usuarios ADD COLUMN foto VARCHAR(500) NULL")
                print("Columna 'foto' agregada.")
            except Exception as e:
                print(f"Nota: {e}")

            print("Agregando columna 'destinos' a 'preferencias_usuario'...")
            try:
                cursor.execute("ALTER TABLE preferencias_usuario ADD COLUMN destinos JSON NULL")
                print("Columna 'destinos' agregada a 'preferencias_usuario'.")
            except Exception as e:
                print(f"Nota: {e}")

            print("Migrando datos de 'destino' a 'destinos' en 'preferencias_usuario'...")
            try:
                cursor.execute("UPDATE preferencias_usuario SET destinos = JSON_ARRAY(destino) WHERE destino IS NOT NULL AND destinos IS NULL")
                print(f"Filas actualizadas en 'preferencias_usuario': {cursor.rowcount}")
            except Exception as e:
                print(f"Error migrando datos en preferencias_usuario: {e}")

            print("Eliminando columna 'destino' de 'preferencias_usuario'...")
            try:
                cursor.execute("ALTER TABLE preferencias_usuario DROP COLUMN destino")
                print("Columna 'destino' eliminada de 'preferencias_usuario'.")
            except Exception as e:
                print(f"Nota: {e}")

            print("Agregando columna 'destinos' a 'viajes'...")
            try:
                cursor.execute("ALTER TABLE viajes ADD COLUMN destinos JSON NOT NULL DEFAULT (JSON_ARRAY())")
                print("Columna 'destinos' agregada a 'viajes'.")
            except Exception as e:
                print(f"Nota: {e}")

            print("Migrando datos de 'destino' a 'destinos' en 'viajes'...")
            try:
                cursor.execute("UPDATE viajes SET destinos = JSON_ARRAY(destino) WHERE destino IS NOT NULL AND destinos IS NULL")
                print(f"Filas actualizadas en 'viajes': {cursor.rowcount}")
            except Exception as e:
                print(f"Error migrando datos en viajes: {e}")

            print("Eliminando columna 'destino' de 'viajes'...")
            try:
                cursor.execute("ALTER TABLE viajes DROP COLUMN destino")
                print("Columna 'destino' eliminada de 'viajes'.")
            except Exception as e:
                print(f"Nota: {e}")

            print("Agregando columna 'id_user_preferences' a 'viajes'...")
            try:
                cursor.execute("ALTER TABLE viajes ADD COLUMN id_user_preferences INT NULL")
                print("Columna 'id_user_preferences' agregada a 'viajes'.")
            except Exception as e:
                print(f"Nota: {e}")

            print("Agregando foreign key 'id_user_preferences' en 'viajes'...")
            try:
                cursor.execute("""
                    ALTER TABLE viajes
                    ADD CONSTRAINT fk_viajes_user_preferences
                    FOREIGN KEY (id_user_preferences) REFERENCES preferencias_usuario(id_preferencia)
                """)
                print("Foreign key agregada a 'viajes'.")
            except Exception as e:
                print(f"Nota: {e}")

        connection.commit()
        print("Migración completada con éxito.")

    except Exception as e:
        print(f"Error durante la migración: {e}")
        connection.rollback()
    finally:
        connection.close()

if __name__ == '__main__':
    main()
