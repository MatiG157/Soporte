"""Migrador de esquema idempotente.

Reemplaza al viejo `migrate_destinos.py`: se puede correr todas las veces que
haga falta, sobre una base vacía o sobre una ya poblada, y sólo aplica lo que
falta. Cada migración queda registrada en la tabla `schema_migrations`.

Uso:
    python migrate.py            # aplica lo pendiente
    python migrate.py --status   # sólo muestra el estado
"""

import argparse
import os
import sys

import pymysql
from dotenv import load_dotenv

load_dotenv()


# En modo silencioso (arranque de la app) las migraciones no imprimen nada:
# lo que interese lo loguea `app.py`.
_SILENCIOSO = False


def _log(mensaje):
    if not _SILENCIOSO:
        print(mensaje)


# ─── Helpers de introspección ────────────────────────────────────────────────

def _existe_tabla(cursor, tabla):
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        (tabla,),
    )
    return cursor.fetchone()[0] > 0


def _existe_columna(cursor, tabla, columna):
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        (tabla, columna),
    )
    return cursor.fetchone()[0] > 0


def _existe_constraint(cursor, tabla, nombre):
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.table_constraints "
        "WHERE table_schema = DATABASE() AND table_name = %s AND constraint_name = %s",
        (tabla, nombre),
    )
    return cursor.fetchone()[0] > 0


def _agregar_columna(cursor, tabla, columna, definicion):
    if not _existe_tabla(cursor, tabla):
        _log(f"    · tabla '{tabla}' todavía no existe, se omite")
        return
    if _existe_columna(cursor, tabla, columna):
        _log(f"    · '{tabla}.{columna}' ya existe")
        return
    cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
    _log(f"    ✓ agregada '{tabla}.{columna}'")


# ─── Migraciones ─────────────────────────────────────────────────────────────

def m001_destinos_como_json(cursor):
    """Pasa `destino` (VARCHAR) a `destinos` (JSON) en viajes y preferencias."""
    for tabla in ("preferencias_usuario", "viajes"):
        if not _existe_tabla(cursor, tabla):
            continue

        if not _existe_columna(cursor, tabla, "destinos"):
            cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN destinos JSON NULL")
            _log(f"    ✓ agregada '{tabla}.destinos'")

        if _existe_columna(cursor, tabla, "destino"):
            cursor.execute(
                f"UPDATE {tabla} SET destinos = JSON_ARRAY(destino) "
                f"WHERE destino IS NOT NULL AND destinos IS NULL"
            )
            _log(f"    ✓ migradas {cursor.rowcount} filas de '{tabla}.destino'")
            cursor.execute(f"ALTER TABLE {tabla} DROP COLUMN destino")
            _log(f"    ✓ eliminada '{tabla}.destino'")

        # Los viajes necesitan destinos sí o sí.
        if tabla == "viajes":
            cursor.execute("UPDATE viajes SET destinos = JSON_ARRAY() WHERE destinos IS NULL")


def m002_campos_de_usuario(cursor):
    """Foto de perfil, login con Google e idioma preferido."""
    _agregar_columna(cursor, "usuarios", "foto", "VARCHAR(500) NULL")
    _agregar_columna(cursor, "usuarios", "google_id", "VARCHAR(255) NULL")
    _agregar_columna(cursor, "usuarios", "auth_provider",
                     "VARCHAR(50) NOT NULL DEFAULT 'local'")
    _agregar_columna(cursor, "usuarios", "idioma", "VARCHAR(5) NOT NULL DEFAULT 'en'")

    if _existe_tabla(cursor, "usuarios") and not _existe_constraint(cursor, "usuarios", "uq_usuarios_google_id"):
        try:
            cursor.execute(
                "ALTER TABLE usuarios ADD CONSTRAINT uq_usuarios_google_id UNIQUE (google_id)"
            )
            _log("    ✓ índice único sobre 'usuarios.google_id'")
        except pymysql.err.OperationalError as exc:
            _log(f"    · no se pudo crear el índice único: {exc}")


def m003_estado_del_viaje(cursor):
    """Estado draft/guardado, agrupación de variantes e imagen del viaje."""
    _agregar_columna(cursor, "viajes", "estado", "VARCHAR(20) NOT NULL DEFAULT 'draft'")
    _agregar_columna(cursor, "viajes", "group_id", "VARCHAR(50) NULL")
    _agregar_columna(cursor, "viajes", "created_at", "DATETIME NULL")
    _agregar_columna(cursor, "viajes", "imagen", "VARCHAR(500) NULL")

    if _existe_tabla(cursor, "viajes"):
        cursor.execute("UPDATE viajes SET created_at = NOW() WHERE created_at IS NULL")


def m004_preferencias_del_viaje(cursor):
    """FK de viajes hacia las preferencias que lo originaron."""
    _agregar_columna(cursor, "viajes", "id_user_preferences", "INT NULL")

    if (_existe_tabla(cursor, "viajes")
            and _existe_tabla(cursor, "preferencias_usuario")
            and not _existe_constraint(cursor, "viajes", "fk_viajes_user_preferences")):
        try:
            cursor.execute(
                "ALTER TABLE viajes ADD CONSTRAINT fk_viajes_user_preferences "
                "FOREIGN KEY (id_user_preferences) "
                "REFERENCES preferencias_usuario(id_preferencia)"
            )
            _log("    ✓ FK 'fk_viajes_user_preferences'")
        except pymysql.err.OperationalError as exc:
            _log(f"    · no se pudo crear la FK: {exc}")


def m005_campos_de_preferencias(cursor):
    """Campos del formulario que se agregaron después del modelo original."""
    _agregar_columna(cursor, "preferencias_usuario", "origen", "VARCHAR(120) NULL")
    _agregar_columna(cursor, "preferencias_usuario", "hospedaje", "VARCHAR(100) NULL")
    _agregar_columna(cursor, "preferencias_usuario", "edades_viajeros", "VARCHAR(100) NULL")
    _agregar_columna(cursor, "preferencias_usuario", "tipo_transporte", "VARCHAR(100) NULL")
    _agregar_columna(cursor, "preferencias_usuario", "fecha_inicio", "DATE NULL")
    _agregar_columna(cursor, "preferencias_usuario", "fecha_fin", "DATE NULL")
    _agregar_columna(cursor, "preferencias_usuario", "act_preferidas", "VARCHAR(100) NULL")

    # `clima` fue reemplazada por `otros` y ya no se usa.
    if (_existe_tabla(cursor, "preferencias_usuario")
            and _existe_columna(cursor, "preferencias_usuario", "clima")):
        cursor.execute(
            "UPDATE preferencias_usuario "
            "SET otros = TRIM(CONCAT(COALESCE(otros, ''), ' Clima: ', clima)) "
            "WHERE clima IS NOT NULL AND clima <> ''"
        )
        cursor.execute("ALTER TABLE preferencias_usuario DROP COLUMN clima")
        _log("    ✓ 'clima' migrada a 'otros' y eliminada")


def m006_normalizar_grupos(cursor):
    """Unifica los valores de `grupo` al vocabulario del dominio (español)."""
    if not _existe_tabla(cursor, "preferencias_usuario"):
        return

    mapa = {
        "family": "familiar",
        "friends": "amigos",
        "educational": "educativo",
        "couple": "pareja",
    }
    for origen, destino in mapa.items():
        cursor.execute(
            "UPDATE preferencias_usuario SET grupo = %s WHERE LOWER(grupo) = %s",
            (destino, origen),
        )
        if cursor.rowcount:
            _log(f"    ✓ {cursor.rowcount} filas: '{origen}' → '{destino}'")


def m007_destinos_relacionales(cursor):
    """Crea la tabla viaje_destinos, migra JSON de viajes, y añade id_viaje_destino a actividades."""
    if not _existe_tabla(cursor, "viaje_destinos"):
        cursor.execute(
            """
            CREATE TABLE viaje_destinos (
                id_viaje_destino INT AUTO_INCREMENT PRIMARY KEY,
                id_viaje INT NOT NULL,
                nombre VARCHAR(150) NOT NULL,
                fecha_llegada DATE NOT NULL,
                fecha_partida DATE NOT NULL,
                CONSTRAINT fk_viajedestinos_viaje FOREIGN KEY (id_viaje) REFERENCES viajes(id_viaje) ON DELETE CASCADE
            )
            """
        )
        _log("    ✓ Tabla 'viaje_destinos' creada")
        
    _agregar_columna(cursor, "actividades", "id_viaje_destino", "INT NULL")

    if (_existe_tabla(cursor, "actividades")
            and _existe_tabla(cursor, "viaje_destinos")
            and not _existe_constraint(cursor, "actividades", "fk_actividades_viajedestinos")):
        try:
            cursor.execute(
                "ALTER TABLE actividades ADD CONSTRAINT fk_actividades_viajedestinos "
                "FOREIGN KEY (id_viaje_destino) REFERENCES viaje_destinos(id_viaje_destino) ON DELETE SET NULL"
            )
            _log("    ✓ FK 'fk_actividades_viajedestinos'")
        except pymysql.err.OperationalError as exc:
            _log(f"    · no se pudo crear la FK: {exc}")

    # Migrar los destinos viejos
    if _existe_columna(cursor, "viajes", "destinos"):
        cursor.execute("SELECT id_viaje, destinos, fecha_inicio, fecha_fin FROM viajes WHERE destinos IS NOT NULL")
        viajes_viejos = cursor.fetchall()
        import json
        for id_viaje, destinos_json, fecha_inicio, fecha_fin in viajes_viejos:
            if not destinos_json: continue
            try:
                destinos = json.loads(destinos_json) if isinstance(destinos_json, str) else destinos_json
            except:
                continue
            
            if not isinstance(destinos, list): continue
            
            for dest in destinos:
                # Asumimos fecha_inicio y fecha_fin para los destinos viejos
                nombre = dest if isinstance(dest, str) else dest.get("nombre", "Sin destino")
                # Insert if not already inserted
                cursor.execute(
                    "SELECT 1 FROM viaje_destinos WHERE id_viaje = %s AND nombre = %s",
                    (id_viaje, nombre)
                )
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO viaje_destinos (id_viaje, nombre, fecha_llegada, fecha_partida) VALUES (%s, %s, %s, %s)",
                        (id_viaje, nombre, fecha_inicio, fecha_fin)
                    )
        
        # Eliminar la columna JSON vieja
        cursor.execute("ALTER TABLE viajes DROP COLUMN destinos")
        _log("    ✓ Columna 'destinos' eliminada de 'viajes'")


MIGRACIONES = [
    ("001_destinos_como_json", m001_destinos_como_json),
    ("002_campos_de_usuario", m002_campos_de_usuario),
    ("003_estado_del_viaje", m003_estado_del_viaje),
    ("004_preferencias_del_viaje", m004_preferencias_del_viaje),
    ("005_campos_de_preferencias", m005_campos_de_preferencias),
    ("006_normalizar_grupos", m006_normalizar_grupos),
    ("007_destinos_relacionales", m007_destinos_relacionales),
]


# ─── Runner ──────────────────────────────────────────────────────────────────

def conectar(silencioso=False):
    """Abre la conexión. Con `silencioso=True` devuelve None en vez de cortar."""
    try:
        return pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "travelplannerbd"),
            port=int(os.getenv("DB_PORT", 3306)),
        )
    except Exception as exc:
        if silencioso:
            return None
        print(f"No se pudo conectar a la base de datos: {exc}")
        sys.exit(1)


def asegurar_tabla_de_control(cursor):
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  nombre VARCHAR(100) PRIMARY KEY,"
        "  aplicada_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
        ")"
    )


def aplicadas(cursor):
    cursor.execute("SELECT nombre FROM schema_migrations")
    return {fila[0] for fila in cursor.fetchall()}


def aplicar_pendientes(silencioso=False):
    """Aplica las migraciones que falten. Devuelve la lista de las aplicadas.

    Pensada para llamarse desde `app.py` al arrancar, así nadie tiene que
    acordarse de correr el migrador a mano después de un `git pull`.
    Con `silencioso=True` no imprime nada y devuelve None si no hay base.
    """
    global _SILENCIOSO

    conexion = conectar(silencioso=silencioso)
    if conexion is None:
        return None

    anterior, _SILENCIOSO = _SILENCIOSO, silencioso
    aplicadas_ahora = []
    try:
        with conexion.cursor() as cursor:
            asegurar_tabla_de_control(cursor)
            ya_aplicadas = aplicadas(cursor)

            for nombre, funcion in MIGRACIONES:
                if nombre in ya_aplicadas:
                    continue
                if not silencioso:
                    print(f"→ {nombre}")
                funcion(cursor)
                cursor.execute(
                    "INSERT INTO schema_migrations (nombre) VALUES (%s)", (nombre,)
                )
                aplicadas_ahora.append(nombre)

        conexion.commit()
        return aplicadas_ahora
    except Exception:
        conexion.rollback()
        raise
    finally:
        _SILENCIOSO = anterior
        conexion.close()


def main():
    parser = argparse.ArgumentParser(description="Migrador de esquema de TravelPlanner")
    parser.add_argument("--status", action="store_true",
                        help="sólo muestra qué migraciones están pendientes")
    args = parser.parse_args()

    conexion = conectar()
    print(f"Conectado a '{os.getenv('DB_NAME', 'travelplannerbd')}'\n")

    try:
        with conexion.cursor() as cursor:
            asegurar_tabla_de_control(cursor)
            ya_aplicadas = aplicadas(cursor)

            if args.status:
                for nombre, _ in MIGRACIONES:
                    estado = "aplicada" if nombre in ya_aplicadas else "PENDIENTE"
                    print(f"  [{estado}] {nombre}")
                return

            pendientes = [m for m in MIGRACIONES if m[0] not in ya_aplicadas]
            if not pendientes:
                print("La base ya está al día. Nada que hacer.")
                return

            for nombre, funcion in pendientes:
                print(f"→ {nombre}")
                funcion(cursor)
                cursor.execute(
                    "INSERT INTO schema_migrations (nombre) VALUES (%s)", (nombre,)
                )
                print()

        conexion.commit()
        print("Migración completada con éxito.")

    except Exception as exc:
        conexion.rollback()
        print(f"Error durante la migración, se revirtió todo: {exc}")
        sys.exit(1)
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
