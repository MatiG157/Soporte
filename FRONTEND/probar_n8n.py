"""Prueba la conexion con el flujo de n8n sin levantar la web.

Manda un payload realista al webhook, mide cuanto tarda y valida la respuesta
contra el mismo contrato que usa la aplicacion. Sirve para saber si el flujo
esta listo antes de probarlo desde el navegador.

Uso:
    python probar_n8n.py
    python probar_n8n.py --destino "Roma, Italia" --dias 4
    python probar_n8n.py --url https://n8n.mi-vps.com/webhook/generate-trips
    python probar_n8n.py --json      # imprime la respuesta cruda y sale
    python probar_n8n.py --descubrir-header   # que header espera tu n8n
"""

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import trip_generator  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OK = "  [ok] "
MAL = "  [!]  "
INFO = "       "


def payload_de_prueba(destino, dias, personas, presupuesto, origen="Buenos Aires, Argentina"):
    inicio = date.today() + timedelta(days=30)
    fin = inicio + timedelta(days=dias - 1)

    return {
        "destinos": [d.strip() for d in destino.split("|") if d.strip()],
        "origen": origen,
        "fecha_inicio": inicio.isoformat(),
        "fecha_fin": fin.isoformat(),
        "costo_min": round(presupuesto * 0.5),
        "costo_max": presupuesto,
        "cantidad_personas": personas,
        "grupo": "friends",
        "edades_viajeros": "25, 27",
        "hospedaje": "hotel, airbnb",
        "tipo_transporte": "plane",
        "act_preferidas": "sightseeing, cultural",
        "otros": "Prueba automatica de conexion con n8n",
        "cantidad_dias": dias,
    }


def diagnosticar_error_http(respuesta):
    """Traduce los fallos tipicos de n8n a algo accionable."""
    codigo = respuesta.status_code

    if codigo == 404:
        lineas = [
            "El webhook no existe o el workflow no esta activo.",
            "- Verifica que el workflow este en Active.",
            "- Usa la URL de produccion (/webhook/...), no la de test",
            "  (/webhook-test/... solo responde con el editor escuchando).",
        ]
    elif codigo in (401, 403):
        lineas = [
            "n8n rechazo la peticion antes de ejecutar el flujo.",
            "Dos causas posibles, y dan el mismo error:",
            "",
            "1. La credencial: el Name o el Value no coinciden.",
            "   Para ver cual espera tu flujo:",
            "     python probar_n8n.py --descubrir-header",
            "",
            "2. La opcion 'Ignore Bots' del nodo Webhook, que rechaza",
            "   segun el User-Agent. Desactivala en Options.",
        ]
    elif codigo == 500:
        lineas = [
            "El flujo fallo durante la ejecucion.",
            "Ya paso la autenticacion: el problema esta en algun nodo.",
            "Mira la pestana Executions en n8n para ver cual.",
        ]
    elif codigo == 504:
        lineas = [
            "Timeout del lado de n8n.",
            "Subi EXECUTIONS_TIMEOUT en el VPS o acorta el prompt del modelo.",
        ]
    else:
        return f"n8n respondio con HTTP {codigo}."

    return ("" + chr(10) + INFO).join(lineas)


def revisar_respuesta_inmediata(datos):
    """Detecta el error mas comun: el webhook contesta sin esperar al flujo."""
    if not isinstance(datos, dict):
        return None

    mensaje = str(datos.get("message", "")).lower()
    if "workflow was started" in mensaje or "started" == mensaje:
        return ("El webhook contesto al instante sin esperar el resultado.\n"
                f"{INFO}En el nodo Webhook pone Respond = 'Using Respond to Webhook node'\n"
                f"{INFO}y agrega ese nodo al final del flujo. Con el default n8n\n"
                f"{INFO}devuelve {{'message': 'Workflow was started'}} y se va.")
    return None


def parece_bloqueo_por_bot(url, timeout):
    """Detecta la opcion 'Ignore Bots' del nodo Webhook.

    Con esa opcion activada n8n rechaza segun el User-Agent, antes de mirar las
    credenciales, y devuelve el mismo 403 que una auth incorrecta. Se distingue
    mandando la misma peticion con dos User-Agent distintos: si el de navegador
    pasa y el de bot no, el problema es ese.
    """
    def golpear(user_agent):
        try:
            return requests.post(
                url, json={"ping": 1}, timeout=timeout,
                headers={"User-Agent": user_agent},
            ).status_code
        except requests.exceptions.RequestException:
            return None

    como_bot = golpear("python-requests/2.32.5")
    como_navegador = golpear("Mozilla/5.0")

    return como_bot == 403 and como_navegador != 403


# Nombres de header que suele usar la credencial Header Auth de n8n.
HEADERS_COMUNES = [
    "X-N8N-TOKEN",
    "Authorization",
    "X-API-KEY",
    "apikey",
    "token",
    "X-Auth-Token",
    "X-Webhook-Token",
]


def descubrir_header(url, token, timeout):
    """Prueba los nombres de header habituales para ver cual acepta el flujo.

    Sirve cuando n8n contesta 'Authorization data is wrong!': la credencial
    existe pero su campo `Name` no es el que estamos mandando.
    """
    print(f"\n{INFO}Probando nombres de header contra el webhook...")
    print(f"{INFO}(si alguno acierta, el flujo se va a ejecutar de verdad)\n")

    if parece_bloqueo_por_bot(url, timeout):
        print(f"{MAL}El nodo Webhook tiene 'Ignore Bots' activado.")
        print(f"{INFO}Rechaza por User-Agent antes de mirar las credenciales.")
        print(f"{INFO}Desactivalo en el nodo Webhook > Options > Ignore Bots.")
        return False

    cuerpo = payload_de_prueba("Osaka, Japan", 3, 2, 3000)
    aciertos = []

    for nombre in HEADERS_COMUNES:
        variantes = [token]
        if nombre.lower() == "authorization":
            variantes = [f"Bearer {token}", token]

        for valor in variantes:
            etiqueta = nombre if valor == token else nombre + " (Bearer)"
            try:
                respuesta = requests.post(
                    url, json=cuerpo,
                    headers={"Content-Type": "application/json", nombre: valor},
                    timeout=timeout,
                )
            except requests.exceptions.RequestException as exc:
                print(f"{MAL}{etiqueta:<26} error de conexion: {exc}")
                continue

            if respuesta.status_code == 403:
                print(f"{INFO}{etiqueta:<26} 403 rechazado")
            elif respuesta.status_code < 400:
                print(f"{OK}{etiqueta:<26} {respuesta.status_code} ACEPTADO")
                aciertos.append((nombre, valor != token))
            else:
                print(f"{INFO}{etiqueta:<26} HTTP {respuesta.status_code}")

    print()
    if not aciertos:
        print(f"{MAL}Ningun nombre funciono: entonces lo que no coincide es el VALOR.")
        print(f"{INFO}Abri la credencial Header Auth en n8n y pega este token exacto")
        print(f"{INFO}en el campo Value:")
        print(f"{INFO}  {token}")
        return False

    nombre, con_bearer = aciertos[0]
    print(f"{OK}Tu n8n espera el header: {nombre}")
    if con_bearer:
        print(f"{INFO}con el formato 'Bearer <token>'.")
        print(f"{INFO}Cambia la credencial a Header Auth simple, o adapta el flujo.")
    else:
        print(f"{INFO}Pone esto en FRONTEND/.env:")
        print(f"{INFO}  N8N_HEADER={nombre}")
    return True


def resumir_procedencia(opciones):
    """Muestra que datos son reales y cuales estimados.

    El flujo declara el origen de cada costo en `fuente_datos.fuentes`. Saberlo
    importa: un total calculado con precios de API no vale lo mismo que uno
    estimado por el modelo, y hay que poder distinguirlos.
    """
    fuentes = (opciones[0].get("fuente_datos") or {}).get("fuentes")
    if not fuentes:
        return

    print(f"\n{INFO}Procedencia de los datos:")
    for clave, valor in fuentes.items():
        estimado = "ESTIMADO" in str(valor).upper()
        print(f"{MAL if estimado else OK}{clave:14} {valor}")


def resumir_opciones(opciones):
    print(f"\n{INFO}Opciones recibidas:")
    for opcion in opciones:
        dias = len(opcion["itinerario"])
        actividades = sum(len(d["actividades"]) for d in opcion["itinerario"])
        print(f"{INFO}  {opcion['tipo']:<9} ${opcion['costo_total_estimado']:>10,.0f}"
              f"   {dias} dias, {actividades} actividades")

    primera = opciones[0]
    print(f"\n{INFO}Muestra ({primera['tipo']}, dia 1):")
    for actividad in primera["itinerario"][0]["actividades"][:3]:
        print(f"{INFO}  {actividad['horario_sugerido']:<15} {actividad['nombre']}")
        print(f"{INFO}  {'':<15} {actividad['categoria']} - ${actividad['precio_estimado']:.0f}")


def main():
    parser = argparse.ArgumentParser(description="Prueba el flujo de n8n")
    parser.add_argument("--url", help="webhook a probar (por defecto, N8N_WEBHOOK_URL del .env)")
    parser.add_argument("--token", help="token a mandar (por defecto, N8N_TOKEN del .env)")
    parser.add_argument("--destino", default="Osaka, Japan",
                        help="destino; separa varios con | para un viaje multi-ciudad. "
                             "Usa el nombre en ingles: Amadeus resuelve el codigo IATA "
                             "por keyword y no matchea grafias locales (Kioto vs Kyoto)")
    parser.add_argument("--origen", default="Buenos Aires, Argentina",
                        help="ciudad de salida; un hub grande da mejor cobertura en las APIs")
    parser.add_argument("--dias", type=int, default=5, help="duracion del viaje")
    parser.add_argument("--personas", type=int, default=2, help="cantidad de viajeros")
    parser.add_argument("--presupuesto", type=float, default=3000, help="costo_max en USD")
    parser.add_argument("--timeout", type=float, help="segundos de espera")
    parser.add_argument("--json", action="store_true",
                        help="imprime la respuesta cruda y termina")
    parser.add_argument("--header",
                        help="nombre del header del token (por defecto, N8N_HEADER del .env)")
    parser.add_argument("--descubrir-header", action="store_true",
                        help="prueba los nombres de header habituales para ver cual acepta n8n")
    args = parser.parse_args()

    url = args.url or os.getenv("N8N_WEBHOOK_URL", "").strip()
    token = args.token if args.token is not None else os.getenv("N8N_TOKEN", "").strip()
    timeout = args.timeout or float(os.getenv("N8N_TIMEOUT", "120"))
    header = args.header or os.getenv("N8N_HEADER", "X-N8N-TOKEN").strip()
    usuario_basic = os.getenv("N8N_BASIC_USER", "").strip()

    print("\nTravelPlanner - prueba del flujo de n8n")
    print("=" * 52)

    if not url:
        print(f"\n{MAL}N8N_WEBHOOK_URL no esta configurada.")
        print(f"{INFO}Ponela en FRONTEND/.env o pasala con --url")
        print(f"{INFO}Sin ella la web usa el generador local (sin IA).\n")
        sys.exit(1)

    if "/webhook-test/" in url:
        print(f"\n{MAL}Estas usando la URL de TEST.")
        print(f"{INFO}Solo responde mientras el editor de n8n escucha.")
        print(f"{INFO}Para uso real cambiala por /webhook/...\n")

    print(f"\n{INFO}URL     : {url}")
    if usuario_basic:
        print(f"{INFO}Auth    : Basic, usuario '{usuario_basic}'")
    elif token:
        print(f"{INFO}Auth    : Header {header} = {token[:6]}...{token[-4:]} (len {len(token)})")
    else:
        print(f"{INFO}Auth    : sin credenciales")
    print(f"{INFO}Timeout : {timeout:.0f}s")

    if args.descubrir_header:
        if not token:
            print(f"\n{MAL}Necesito un token para probar los headers.\n")
            sys.exit(1)
        sys.exit(0 if descubrir_header(url, token, timeout) else 1)

    cuerpo = payload_de_prueba(args.destino, args.dias, args.personas,
                               args.presupuesto, args.origen)
    print(f"{INFO}Desde   : {cuerpo['origen']}")
    print(f"{INFO}Pidiendo: {' + '.join(cuerpo['destinos'])}, "
          f"{args.dias} dias, {args.personas} personas, max ${args.presupuesto:,.0f}")

    # Igual que la app: sin User-Agent propio, 'Ignore Bots' nos rechaza.
    cabeceras = {"Content-Type": "application/json", "User-Agent": "TravelPlanner/1.0"}
    auth = None
    if usuario_basic:
        auth = (usuario_basic, os.getenv("N8N_BASIC_PASSWORD", ""))
    elif token:
        cabeceras[header] = token

    print(f"\n{INFO}Enviando...")
    comienzo = time.time()

    try:
        respuesta = requests.post(url, json=cuerpo, headers=cabeceras,
                                  auth=auth, timeout=timeout)
    except requests.exceptions.Timeout:
        print(f"{MAL}Sin respuesta despues de {timeout:.0f}s.")
        print(f"{INFO}El flujo tarda mas que el timeout. Subi N8N_TIMEOUT en el .env")
        print(f"{INFO}o revisa si el modelo se queda colgado.\n")
        sys.exit(1)
    except requests.exceptions.SSLError as exc:
        print(f"{MAL}Error de certificado HTTPS: {exc}")
        print(f"{INFO}El certificado del VPS no es valido o esta vencido.\n")
        sys.exit(1)
    except requests.exceptions.ConnectionError as exc:
        print(f"{MAL}No se pudo conectar: {exc}")
        print(f"{INFO}Revisa que el dominio resuelva y que n8n este levantado.\n")
        sys.exit(1)

    tardanza = time.time() - comienzo
    print(f"{OK}Respondio en {tardanza:.1f}s con HTTP {respuesta.status_code}")

    if args.json:
        print()
        try:
            print(json.dumps(respuesta.json(), ensure_ascii=False, indent=2))
        except ValueError:
            print(respuesta.text)
        return

    if respuesta.status_code >= 400:
        print(f"{MAL}{diagnosticar_error_http(respuesta)}")
        print(f"\n{INFO}Cuerpo: {respuesta.text[:400]}\n")
        sys.exit(1)

    try:
        datos = respuesta.json()
    except ValueError:
        print(f"{MAL}La respuesta no es JSON valido.")
        print(f"{INFO}Primeros 400 caracteres: {respuesta.text[:400]}\n")
        sys.exit(1)

    aviso = revisar_respuesta_inmediata(datos)
    if aviso:
        print(f"{MAL}{aviso}\n")
        sys.exit(1)

    # Se valida con la misma funcion que usa la app: si pasa aca, pasa en la web.
    print(f"{INFO}Validando contra el contrato...")
    try:
        opciones = trip_generator.validar_opciones(datos, cuerpo)
    except Exception as exc:
        print(f"{MAL}La respuesta no cumple el contrato: {exc}")
        print(f"{INFO}La web la rechazaria y usaria el generador local.")
        print(f"{INFO}Corre con --json para ver que devolvio el flujo.")
        print(f"{INFO}El contrato completo esta en PROMPT_N8N.md\n")
        sys.exit(1)

    print(f"{OK}Contrato correcto: 3 opciones, dias y actividades completos")

    faltan_imagen = [o["tipo"] for o in opciones if not o.get("imagen")]
    if faltan_imagen:
        print(f"{INFO}Sin imagen: {', '.join(faltan_imagen)} (la web busca una en Wikipedia)")

    faltan_costos = [o["tipo"] for o in opciones if not o.get("desglose_costos")]
    if faltan_costos:
        print(f"{INFO}Sin desglose_costos: {', '.join(faltan_costos)} "
              f"(el backend reparte 35/30/20/15)")

    resumir_procedencia(opciones)
    resumir_opciones(opciones)

    print(f"\n{'=' * 52}")
    print("El flujo esta listo. La web ya lo va a usar.\n")


if __name__ == "__main__":
    main()
