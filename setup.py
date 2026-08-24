"""Prepara el entorno local del proyecto.

Los archivos `.env` no están en el repo (llevan claves), así que después de un
`git clone` o un `git pull` cada uno tiene que armar los suyos. Este script lo
hace solo y, sobre todo, **deja la misma clave en los dos lados**: si
`BACKEND/.env → API_KEY` y `FRONTEND/.env → BACKEND_API_KEY` no coinciden, el
backend rechaza todo con 401 y no se puede ni registrar ni loguear.

Es idempotente: no pisa lo que ya está configurado.

Uso:
    python setup.py            # crea/completa lo que falte
    python setup.py --check    # sólo revisa y reporta, no escribe nada
    python setup.py --rotar    # genera claves nuevas (te desloguea a todos)
"""

import argparse
import os
import re
import secrets
import sys

# La consola de Windows suele venir en cp1252: intentamos pasarla a UTF-8 y,
# si no se puede, el resto del script igual imprime sólo ASCII.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError, ValueError):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

RAIZ = os.path.dirname(os.path.abspath(__file__))
BACKEND_ENV = os.path.join(RAIZ, "BACKEND", ".env")
FRONTEND_ENV = os.path.join(RAIZ, "FRONTEND", ".env")

OK = "  [ok]"
NUEVO = "  [+] "
AVISO = "  [!] "


# ─── Lectura y escritura de .env ─────────────────────────────────────────────

def leer(ruta):
    """Devuelve {clave: valor} de un .env. Vacío si no existe."""
    if not os.path.exists(ruta):
        return {}

    valores = {}
    with open(ruta, encoding="utf-8") as archivo:
        for linea in archivo:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            valor = valor.strip()
            # dotenv quita las comillas envolventes: replicamos ese comportamiento.
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            valores[clave.strip()] = valor
    return valores


def escribir_clave(ruta, clave, valor):
    """Agrega o reemplaza una clave respetando el resto del archivo."""
    contenido = ""
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as archivo:
            contenido = archivo.read()

    patron = re.compile(rf"^\s*{re.escape(clave)}\s*=.*$", re.MULTILINE)

    if patron.search(contenido):
        contenido = patron.sub(f"{clave}={valor}", contenido)
    else:
        if contenido and not contenido.endswith("\n"):
            contenido += "\n"
        contenido += f"{clave}={valor}\n"

    with open(ruta, "w", encoding="utf-8") as archivo:
        archivo.write(contenido)


def crear_desde_ejemplo(ruta):
    ejemplo = ruta + ".example"
    if not os.path.exists(ejemplo):
        return False

    with open(ejemplo, encoding="utf-8") as origen:
        contenido = origen.read()

    # Los placeholders se vacían: los completa este mismo script.
    contenido = contenido.replace(
        "cambiar_por_una_clave_larga_y_aleatoria", ""
    )

    with open(ruta, "w", encoding="utf-8") as destino:
        destino.write(contenido)
    return True


def es_placeholder(valor):
    if not valor:
        return True
    sospechosos = ("cambiar", "tu_", "aqui", "aquí", "<", "xxx")
    return any(s in valor.lower() for s in sospechosos)


# ─── Pasos ───────────────────────────────────────────────────────────────────

def asegurar_archivos(cambios, solo_chequear):
    for ruta, nombre in ((BACKEND_ENV, "BACKEND/.env"), (FRONTEND_ENV, "FRONTEND/.env")):
        if os.path.exists(ruta):
            print(f"{OK} {nombre} existe")
            continue

        if solo_chequear:
            print(f"{AVISO}{nombre} NO existe")
            cambios.append(nombre)
            continue

        if crear_desde_ejemplo(ruta):
            print(f"{NUEVO}{nombre} creado desde .env.example")
            cambios.append(nombre)
        else:
            print(f"{AVISO}falta {nombre}.example, no puedo crear {nombre}")


def sincronizar_api_key(cambios, solo_chequear, rotar):
    backend = leer(BACKEND_ENV)
    frontend = leer(FRONTEND_ENV)

    api_key = backend.get("API_KEY", "")

    if rotar or es_placeholder(api_key):
        if solo_chequear:
            print(f"{AVISO}API_KEY sin definir en BACKEND/.env")
            cambios.append("API_KEY")
            return
        api_key = secrets.token_urlsafe(32)
        escribir_clave(BACKEND_ENV, "API_KEY", api_key)
        print(f"{NUEVO}API_KEY generada en BACKEND/.env")
        cambios.append("API_KEY")
    else:
        print(f"{OK} API_KEY definida en BACKEND/.env")

    # Lo importante: que el frontend use exactamente la misma.
    if frontend.get("BACKEND_API_KEY", "") == api_key:
        print(f"{OK} BACKEND_API_KEY coincide con la del backend")
        return

    if solo_chequear:
        print(f"{AVISO}BACKEND_API_KEY NO coincide con API_KEY del backend")
        print(f"       -> por esto el login y el registro devuelven 401")
        cambios.append("BACKEND_API_KEY")
        return

    escribir_clave(FRONTEND_ENV, "BACKEND_API_KEY", api_key)
    print(f"{NUEVO}BACKEND_API_KEY sincronizada en FRONTEND/.env")
    cambios.append("BACKEND_API_KEY")


def asegurar_secret_key(cambios, solo_chequear, rotar):
    frontend = leer(FRONTEND_ENV)
    actual = frontend.get("SECRET_KEY", "")

    if not rotar and not es_placeholder(actual):
        print(f"{OK} SECRET_KEY definida en FRONTEND/.env")
        return

    if solo_chequear:
        print(f"{AVISO}SECRET_KEY sin definir en FRONTEND/.env")
        cambios.append("SECRET_KEY")
        return

    escribir_clave(FRONTEND_ENV, "SECRET_KEY", secrets.token_urlsafe(32))
    print(f"{NUEVO}SECRET_KEY generada en FRONTEND/.env")
    cambios.append("SECRET_KEY")


def revisar_url_del_backend(cambios, solo_chequear):
    """Avisa si BACKEND_URL usa 'localhost' en vez de 127.0.0.1.

    En Windows 'localhost' resuelve primero a ::1 y el servidor de Flask solo
    escucha en IPv4: cada peticion al backend pierde ~2 segundos esperando que
    falle el intento por IPv6.
    """
    frontend = leer(FRONTEND_ENV)
    url = frontend.get("BACKEND_URL", "")

    if "localhost" not in url:
        print(f"{OK} BACKEND_URL: {url or '127.0.0.1:5000 (por defecto)'}")
        return

    if solo_chequear:
        print(f"{AVISO}BACKEND_URL usa 'localhost': suma ~2s por peticion en Windows")
        cambios.append("BACKEND_URL")
        return

    escribir_clave(FRONTEND_ENV, "BACKEND_URL", url.replace("localhost", "127.0.0.1"))
    print(f"{NUEVO}BACKEND_URL cambiada a 127.0.0.1 (evita el retardo de IPv6)")
    cambios.append("BACKEND_URL")


def revisar_base_de_datos():
    backend = leer(BACKEND_ENV)
    faltan = [c for c in ("DB_USER", "DB_NAME") if es_placeholder(backend.get(c, ""))]

    # Una contrasena vacia es legitima; el placeholder del ejemplo no lo es.
    password = backend.get("DB_PASSWORD", "")
    if password and es_placeholder(password):
        faltan.append("DB_PASSWORD")

    if faltan:
        print(f"{AVISO}completa a mano en BACKEND/.env: {', '.join(faltan)}")
        print(f"       (y DB_PASSWORD si tu MySQL tiene password)")
        return False

    print(f"{OK} conexion a la base configurada "
          f"({backend.get('DB_USER')}@{backend.get('DB_HOST', 'localhost')}"
          f"/{backend.get('DB_NAME')})")
    return True


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Prepara los .env del proyecto")
    parser.add_argument("--check", action="store_true",
                        help="sólo revisa y reporta, no escribe nada")
    parser.add_argument("--rotar", action="store_true",
                        help="genera claves nuevas (cierra todas las sesiones abiertas)")
    args = parser.parse_args()

    print("\nTravelPlanner - preparacion del entorno")
    print("=" * 44)

    cambios = []

    print("\nArchivos de configuración")
    asegurar_archivos(cambios, args.check)

    print("\nClave compartida backend ↔ frontend")
    sincronizar_api_key(cambios, args.check, args.rotar)

    print("\nClave de sesión del frontend")
    asegurar_secret_key(cambios, args.check, args.rotar)

    print("\nConexion con el backend")
    revisar_url_del_backend(cambios, args.check)

    print("\nBase de datos")
    base_ok = revisar_base_de_datos()

    print("\n" + "=" * 44)

    if args.check:
        if cambios:
            print("Faltan cosas por configurar. Ejecuta:  python setup.py")
            sys.exit(1)
        print("Todo en orden.")
        return

    if cambios:
        print("Entorno actualizado:", ", ".join(dict.fromkeys(cambios)))
    else:
        print("Ya estaba todo configurado, no hice nada.")

    if base_ok:
        print("\nSiguiente paso:")
        print("  cd BACKEND && python migrate.py     (o arranca el backend: migra solo)")
    print()


if __name__ == "__main__":
    main()
