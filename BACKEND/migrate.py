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


# La consola de Windows usa cp1252, que no sabe escribir '→' ni '✓'. Sin esto,
# imprimir el nombre de una migración pendiente lanzaba UnicodeEncodeError y el
# runner revertía todo: la migración fallaba por un cartel, no por el SQL.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


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


def m008_viajes_titulo(cursor):
    """Agrega la columna titulo a viajes y setea el titulo por defecto en inglés si no lo tiene."""
    _agregar_columna(cursor, "viajes", "titulo", "VARCHAR(255) NULL")
    
    # Si la columna no se pudo agregar (tabla inexistente en una base nueva),
    # no tiene sentido seguir: se saltea el relleno en vez de romper la migración.
    if not _existe_columna(cursor, "viajes", "titulo"):
        _log("    · 'viajes.titulo' no está disponible, se omite el relleno")
        return

    cursor.execute("SELECT id_viaje, tipo_viaje FROM viajes WHERE titulo IS NULL")
    viajes_sin_titulo = cursor.fetchall()

    hay_destinos = _existe_tabla(cursor, "viaje_destinos")

    for id_viaje, tipo_viaje in viajes_sin_titulo:
        destinos = []
        if hay_destinos:
            cursor.execute(
                "SELECT nombre FROM viaje_destinos WHERE id_viaje = %s ORDER BY fecha_llegada",
                (id_viaje,),
            )
            destinos = [fila[0] for fila in cursor.fetchall() if fila[0]]

        # `tipo_viaje` puede venir NULL en filas viejas: sin este guardo,
        # `.capitalize()` lanzaba y hacía fallar la migración completa.
        nivel = (tipo_viaje or "").strip().capitalize() or "Trip"
        titulo = f"{nivel} Trip To: {' --> '.join(destinos)}" if destinos else f"{nivel} Trip"

        cursor.execute("UPDATE viajes SET titulo = %s WHERE id_viaje = %s",
                       (titulo[:255], id_viaje))

    _log(f"    ✓ Títulos generados para {len(viajes_sin_titulo)} viajes existentes")

def m009_procedencia_de_actividades(cursor):
    """Guarda de dónde salió el precio de cada actividad.

    El flujo de n8n cotiza vuelos y hoteles contra APIs reales y devuelve, por
    actividad, el link de la oferta, una nota y un flag cuando el precio le
    parece raro. Sin estas columnas eso se perdía al guardar y el itinerario no
    podía distinguir un precio cotizado de uno inventado.
    """
    _agregar_columna(cursor, "actividades", "link", "VARCHAR(500) NULL")
    _agregar_columna(cursor, "actividades", "nota", "VARCHAR(300) NULL")
    _agregar_columna(cursor, "actividades", "precio_sospechoso", "BOOLEAN NOT NULL DEFAULT FALSE")


def m010_actividades_de_google_places(cursor):
    """Datos del lugar real que el flujo cruzó contra Google Places.

    La foto se guarda como referencia (`places/.../photos/...`), no como URL:
    la URL que manda el flujo lleva la API key de Google adentro y no puede
    llegar al navegador. La imagen se sirve por el proxy del frontend.
    """
    _agregar_columna(cursor, "actividades", "imagen_ref", "VARCHAR(300) NULL")
    _agregar_columna(cursor, "actividades", "rating", "FLOAT NULL")
    _agregar_columna(cursor, "actividades", "opiniones", "INT NULL")
    _agregar_columna(cursor, "actividades", "mapa", "VARCHAR(500) NULL")
    _agregar_columna(cursor, "actividades", "web", "VARCHAR(500) NULL")
    _agregar_columna(cursor, "actividades", "place_id", "VARCHAR(120) NULL")
    _agregar_columna(cursor, "actividades", "lat", "FLOAT NULL")
    _agregar_columna(cursor, "actividades", "lng", "FLOAT NULL")


def m011_referencias_de_foto_largas(cursor):
    """`imagen_ref` no entra en 300 caracteres.

    Un id de foto de Google Places mide unos 258 caracteres, y con el prefijo
    `places/<id del lugar>/photos/` el total queda en 300 justos: al borde. Un
    id apenas más largo se guardaba cortado, y una referencia cortada no sirve
    para nada. Se agranda la columna y se descartan las que ya quedaron rotas.
    """
    if not _existe_columna(cursor, "actividades", "imagen_ref"):
        _log("    · 'actividades.imagen_ref' todavía no existe, se omite")
        return

    cursor.execute("ALTER TABLE actividades MODIFY COLUMN imagen_ref VARCHAR(1000) NULL")
    _log("    ✓ 'actividades.imagen_ref' ampliada a 1000")

    for columna in ("mapa", "web", "link"):
        if _existe_columna(cursor, "actividades", columna):
            cursor.execute(f"ALTER TABLE actividades MODIFY COLUMN {columna} VARCHAR(1000) NULL")
    _log("    ✓ 'mapa', 'web' y 'link' ampliadas a 1000")

    # Una referencia sin '/photos/' quedó cortada antes de esa parte: pedirla
    # es un 404 seguro, así que se limpia para que la tarjeta use el fondo de
    # categoría sin hacer el viaje de ida.
    cursor.execute(
        "UPDATE actividades SET imagen_ref = NULL "
        "WHERE imagen_ref IS NOT NULL AND imagen_ref NOT LIKE '%%/photos/%%'")
    _log(f"    ✓ {cursor.rowcount} referencias rotas descartadas")


def m012_descartar_referencias_cortadas(cursor):
    """Las referencias de exactamente 300 caracteres están cortadas.

    La 011 amplió la columna, pero el frontend seguía recortando a 300 antes de
    mandarlas, así que las que ya estaban guardadas quedaron cortas igual.
    Pedirle a Google una referencia cortada es un 404 seguro: se descartan para
    que la tarjeta use el fondo de categoría sin hacer el viaje de ida.
    """
    if not _existe_columna(cursor, "actividades", "imagen_ref"):
        return

    cursor.execute("UPDATE actividades SET imagen_ref = NULL "
                   "WHERE imagen_ref IS NOT NULL AND CHAR_LENGTH(imagen_ref) = 300")
    _log(f"    ✓ {cursor.rowcount} referencias cortadas descartadas")


def m013_vacios_de_google_como_null(cursor):
    """Los campos sin ficha de Google quedaron en "" en vez de NULL.

    Google no encuentra todos los lugares. Guardar la cadena vacía hace que
    `imagen_ref IS NOT NULL` cuente filas que no tienen foto, y eso despista a
    cualquiera que mire la base para entender qué falta.
    """
    for columna in ("imagen_ref", "mapa", "web", "place_id", "link", "nota"):
        if _existe_columna(cursor, "actividades", columna):
            cursor.execute(f"UPDATE actividades SET {columna} = NULL WHERE {columna} = ''")
    _log("    ✓ campos vacíos normalizados a NULL")


def m014_procedencia_del_precio(cursor):
    """De dónde salió el precio de cada actividad.

    El flujo distingue dos cosas que hasta ahora se veían igual en la tarjeta:
    un precio consultado (el `priceRange` de Google, con montos reales) y uno
    que estimó un modelo de memoria. Mostrarlos sin diferencia hace pasar por
    dato lo que es una aproximación, y eso es justamente lo que hay que poder
    defender.
    """
    _agregar_columna(cursor, "actividades", "precio_fuente", "VARCHAR(40) NULL")
    _agregar_columna(cursor, "actividades", "precio_desde", "FLOAT NULL")
    _agregar_columna(cursor, "actividades", "precio_hasta", "FLOAT NULL")
    _agregar_columna(cursor, "actividades", "precio_moneda", "VARCHAR(8) NULL")


MIGRACIONES = [
    ("001_destinos_como_json", m001_destinos_como_json),
    ("002_campos_de_usuario", m002_campos_de_usuario),
    ("003_estado_del_viaje", m003_estado_del_viaje),
    ("004_preferencias_del_viaje", m004_preferencias_del_viaje),
    ("005_campos_de_preferencias", m005_campos_de_preferencias),
    ("006_normalizar_grupos", m006_normalizar_grupos),
    ("007_destinos_relacionales", m007_destinos_relacionales),
    ("008_viajes_titulo", m008_viajes_titulo),
    ("009_procedencia_de_actividades", m009_procedencia_de_actividades),
    ("010_actividades_de_google_places", m010_actividades_de_google_places),
    ("011_referencias_de_foto_largas", m011_referencias_de_foto_largas),
    ("012_descartar_referencias_cortadas", m012_descartar_referencias_cortadas),
    ("013_vacios_de_google_como_null", m013_vacios_de_google_como_null),
    ("014_procedencia_del_precio", m014_procedencia_del_precio),
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
