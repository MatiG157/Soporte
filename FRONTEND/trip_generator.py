"""Capa de integración: generación de las 3 variantes de viaje.

El generador es **el flujo de n8n** (`N8N_WEBHOOK_URL`): es el único proveedor
de IA del sistema.

Si n8n no responde (no está configurado, se cayó, devolvió algo que no cumple
el contrato), se usa un generador local determinístico —sin IA— para que la web
siga funcionando. Respeta la cantidad real de días, el presupuesto y las
actividades preferidas, pero no reemplaza a n8n: es una red de seguridad.

Ambos devuelven exactamente el mismo contrato, documentado en PROMPT_N8N.md.
"""

import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

TIPOS = ("Economy", "Balanced", "Luxury")

# Proporción del presupuesto máximo que consume cada variante.
FACTOR_PRESUPUESTO = {"Economy": 0.65, "Balanced": 0.95, "Luxury": 1.60}

# Reparto del costo total entre las cuatro categorías de la regla de negocio.
REPARTO = {
    "costo_alojamiento": 0.35,
    "costo_transporte": 0.30,
    "costo_actividades": 0.20,
    "costo_comidas": 0.15,
}

# Presupuesto por persona y por día cuando el usuario no indica ninguno.
COSTO_DIARIO_POR_PERSONA = 120.0

LIMITES = {"nombre": 120, "categoria": 80, "horario_sugerido": 30, "ubicacion": 150,
           "link": 500, "nota": 300}

IMAGEN_POR_DEFECTO = (
    "https://images.unsplash.com/photo-1488646953014-85cb44e25828"
    "?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80"
)

# Catálogo de actividades del generador local, por interés y nivel de gasto.
CATALOGO = {
    "sightseeing": {
        "Economy": [("Caminata por el casco histórico de {destino}",
                     "Recorrido a pie autoguiado por los puntos más conocidos.",
                     0.0, "Sightseeing", "09:00 - 12:00")],
        "Balanced": [("Tour guiado por {destino}",
                      "Visita en grupo reducido con guía local certificado.",
                      35.0, "Sightseeing", "09:30 - 13:00")],
        "Luxury": [("Tour privado por {destino} con chofer",
                    "Recorrido exclusivo con guía personal y traslados privados.",
                    240.0, "Sightseeing", "09:00 - 13:00")],
    },
    "cultural": {
        "Economy": [("Museos de entrada libre en {destino}",
                     "Circuito por los museos municipales sin costo de entrada.",
                     0.0, "Cultural", "15:00 - 18:00")],
        "Balanced": [("Museo principal de {destino}",
                      "Entrada general con audioguía incluida.",
                      22.0, "Cultural", "15:00 - 18:00")],
        "Luxury": [("Visita privada fuera de horario en {destino}",
                    "Acceso exclusivo a la colección principal con curador.",
                    180.0, "Cultural", "18:00 - 20:30")],
    },
    "adventure": {
        "Economy": [("Trekking en los alrededores de {destino}",
                     "Sendero de dificultad media, sin guía.",
                     8.0, "Aventura", "08:00 - 13:00")],
        "Balanced": [("Excursión de día en {destino}",
                      "Salida guiada con traslado y equipamiento incluido.",
                      65.0, "Aventura", "08:00 - 15:00")],
        "Luxury": [("Excursión privada premium en {destino}",
                    "Salida exclusiva con guía propio, equipo y catering.",
                    380.0, "Aventura", "08:00 - 16:00")],
    },
    "relaxation": {
        "Economy": [("Tarde libre en los parques de {destino}",
                     "Descanso y picnic en los espacios verdes de la ciudad.",
                     6.0, "Relax", "16:00 - 19:00")],
        "Balanced": [("Circuito de spa en {destino}",
                      "Acceso a piletas termales y sauna por medio día.",
                      55.0, "Relax", "16:00 - 19:00")],
        "Luxury": [("Spa cinco estrellas en {destino}",
                    "Circuito completo con masaje y tratamiento personalizado.",
                    220.0, "Relax", "16:00 - 20:00")],
    },
}

# Comidas: siempre hay una por día, escalada por el nivel de la variante.
COMIDAS = {
    "Economy": ("Almuerzo en mercado local de {destino}",
                "Comida típica en un puesto de barrio.", 12.0,
                "Gastronomía", "13:00 - 14:30"),
    "Balanced": ("Almuerzo en restaurante típico de {destino}",
                 "Menú regional de tres pasos con bebida.", 32.0,
                 "Gastronomía", "13:00 - 14:30"),
    "Luxury": ("Almuerzo de autor en {destino}",
               "Menú degustación en restaurante de alta cocina.", 190.0,
               "Gastronomía", "13:00 - 15:00"),
}

# Cache en proceso para no pegarle a Wikipedia por cada request.
_cache_imagenes = {}


# ─── Utilidades ──────────────────────────────────────────────────────────────

def _a_fecha(valor, por_defecto=None):
    try:
        return datetime.strptime(str(valor), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return por_defecto


def cantidad_de_dias(fecha_inicio, fecha_fin):
    inicio = _a_fecha(fecha_inicio)
    fin = _a_fecha(fecha_fin)
    if not inicio or not fin:
        return 3
    return max((fin - inicio).days + 1, 1)


def _recortar(texto, limite):
    texto = str(texto).strip()
    return texto[:limite] if len(texto) > limite else texto


def _hora_de_inicio(actividad):
    """Minutos desde medianoche del horario de una actividad, para ordenarlas.

    `horario_sugerido` viene como "HH:MM - HH:MM". Lo que no parsea va al final
    en vez de romper el orden del resto.
    """
    coincidencia = re.match(r"\s*(\d{1,2})[:.](\d{2})", str(actividad.get("horario_sugerido") or ""))
    if not coincidencia:
        return 24 * 60
    return int(coincidencia.group(1)) * 60 + int(coincidencia.group(2))


def _lista_desde_csv(valor):
    if not valor:
        return []
    return [p.strip().lower() for p in str(valor).split(",") if p.strip()]


def _ciudad(destino):
    """'Kyoto, Japón' → 'Kyoto'."""
    return str(destino).split(",")[0].strip()


def obtener_imagen_destino(destino):
    """Busca una foto del destino en Wikipedia. Devuelve None si no encuentra."""
    if not destino:
        return None

    ciudad = _ciudad(destino)
    if ciudad in _cache_imagenes:
        return _cache_imagenes[ciudad]

    titulo = unicodedata.normalize("NFC", ciudad).replace(" ", "_")
    imagen = None

    for idioma in ("es", "en"):
        try:
            respuesta = requests.get(
                f"https://{idioma}.wikipedia.org/api/rest_v1/page/summary/{titulo}",
                timeout=4,
                headers={"User-Agent": "TravelPlanner/1.0 (proyecto académico)"},
            )
            if respuesta.status_code == 200:
                datos = respuesta.json()
                imagen = (
                    (datos.get("originalimage") or {}).get("source")
                    or (datos.get("thumbnail") or {}).get("source")
                )
                if imagen:
                    break
        except requests.exceptions.RequestException:
            continue

    if imagen and len(imagen) > 500:
        imagen = None

    _cache_imagenes[ciudad] = imagen
    return imagen


# ─── Generador local (último recurso) ────────────────────────────────────────

def _presupuesto_base(preferencias, dias):
    costo_max = preferencias.get("costo_max")
    costo_min = preferencias.get("costo_min")

    if costo_max:
        return float(costo_max)
    if costo_min:
        return float(costo_min) * 1.3

    personas = int(preferencias.get("cantidad_personas") or 1)
    return COSTO_DIARIO_POR_PERSONA * personas * dias


def _intereses(preferencias):
    elegidos = [i for i in _lista_desde_csv(preferencias.get("act_preferidas"))
                if i in CATALOGO]
    return elegidos or ["sightseeing", "cultural"]


def _actividades_del_dia(destino, tipo, intereses, indice_dia):
    """Arma entre 2 y 3 actividades rotando los intereses elegidos."""
    actividades = []

    for desplazamiento in range(2):
        interes = intereses[(indice_dia + desplazamiento) % len(intereses)]
        plantillas = CATALOGO[interes][tipo]
        nombre, descripcion, precio, categoria, horario = plantillas[0]
        actividades.append({
            "nombre": _recortar(nombre.format(destino=_ciudad(destino)), LIMITES["nombre"]),
            "descripcion": descripcion,
            "precio_estimado": precio,
            "categoria": _recortar(categoria, LIMITES["categoria"]),
            "horario_sugerido": _recortar(horario, LIMITES["horario_sugerido"]),
            "ubicacion": _recortar(destino, LIMITES["ubicacion"]),
        })

    nombre, descripcion, precio, categoria, horario = COMIDAS[tipo]
    actividades.append({
        "nombre": _recortar(nombre.format(destino=_ciudad(destino)), LIMITES["nombre"]),
        "descripcion": descripcion,
        "precio_estimado": precio,
        "categoria": _recortar(categoria, LIMITES["categoria"]),
        "horario_sugerido": _recortar(horario, LIMITES["horario_sugerido"]),
        "ubicacion": _recortar(destino, LIMITES["ubicacion"]),
    })

    # Ordenadas por hora de inicio para que el timeline quede coherente.
    return sorted(actividades, key=lambda a: a["horario_sugerido"])


def generar_localmente(preferencias):
    """Genera 3 variantes sin IA, respetando fechas, presupuesto e intereses."""
    destinos = [d for d in (preferencias.get("destinos") or []) if d]
    if not destinos:
        raise ValueError("Se necesita al menos un destino")

    fecha_inicio = _a_fecha(preferencias.get("fecha_inicio"), datetime.today().date())
    dias = cantidad_de_dias(preferencias.get("fecha_inicio"), preferencias.get("fecha_fin"))
    fecha_fin = _a_fecha(preferencias.get("fecha_fin"), fecha_inicio + timedelta(days=dias - 1))

    base = _presupuesto_base(preferencias, dias)
    intereses = _intereses(preferencias)
    imagen = obtener_imagen_destino(destinos[0]) or IMAGEN_POR_DEFECTO

    opciones = []
    for tipo in TIPOS:
        itinerario = []
        for numero_dia in range(1, dias + 1):
            # Los destinos se reparten en tramos consecutivos.
            indice_destino = min((numero_dia - 1) * len(destinos) // dias, len(destinos) - 1)
            destino = destinos[indice_destino]

            itinerario.append({
                "dia": numero_dia,
                "resumen": f"Día {numero_dia} en {_ciudad(destino)}",
                "actividades": _actividades_del_dia(destino, tipo, intereses, numero_dia - 1),
            })

        total = round(base * FACTOR_PRESUPUESTO[tipo], 2)
        opciones.append({
            "destinos": destinos,
            "fecha_inicio": fecha_inicio.isoformat(),
            "fecha_fin": fecha_fin.isoformat(),
            "tipo": tipo,
            "costo_total_estimado": total,
            "imagen": imagen,
            "desglose_costos": {
                clave: round(total * proporcion, 2) for clave, proporcion in REPARTO.items()
            },
            "itinerario": itinerario,
        })

    return opciones


# ─── Validación del contrato ─────────────────────────────────────────────────

def _limpiar_json(texto):
    limpio = re.sub(r"^\s*```(?:json)?", "", str(texto).strip())
    return re.sub(r"```\s*$", "", limpio).strip()


# Estados que devuelve el flujo comparando el presupuesto pedido contra la
# opción más barata.
ESTADOS_PRESUPUESTO = ("ok", "ajustado", "presupuesto_insuficiente")


def leer_sobre(respuesta):
    """Separa las opciones del estado del presupuesto.

    El flujo pasó de devolver un array pelado a un objeto
    `{estado, opciones, aviso_presupuesto}`. Se aceptan las dos formas: la
    vieja simplemente no trae aviso.
    """
    if isinstance(respuesta, str):
        import json
        respuesta = json.loads(_limpiar_json(respuesta))

    if not isinstance(respuesta, dict):
        return respuesta, {"estado": "ok", "aviso": None}

    for clave in ("opciones", "data", "viajes", "result"):
        if isinstance(respuesta.get(clave), list):
            estado = respuesta.get("estado")
            return respuesta[clave], {
                "estado": estado if estado in ESTADOS_PRESUPUESTO else "ok",
                "aviso": respuesta.get("aviso_presupuesto"),
            }

    return respuesta, {"estado": "ok", "aviso": None}


def validar_opciones(opciones, preferencias):
    """Verifica el contrato y normaliza lo que venga de la IA.

    Lanza ValueError si la respuesta no sirve, para que el caller pase al
    siguiente proveedor.
    """
    opciones, _ = leer_sobre(opciones)

    if not isinstance(opciones, list) or len(opciones) != 3:
        raise ValueError("Se esperaban exactamente 3 opciones de viaje")

    tipos = {str(o.get("tipo") or o.get("tipo_viaje")) for o in opciones}
    if tipos != set(TIPOS):
        raise ValueError(f"Tipos inválidos: {sorted(tipos)}. Se esperaban {list(TIPOS)}")

    destinos = [d for d in (preferencias.get("destinos") or []) if d]
    dias_esperados = cantidad_de_dias(
        preferencias.get("fecha_inicio"), preferencias.get("fecha_fin")
    )

    normalizadas = []
    for opcion in opciones:
        itinerario = opcion.get("itinerario")
        if not isinstance(itinerario, list) or not itinerario:
            raise ValueError("Una de las opciones no trae itinerario")

        dias_normalizados = []
        for indice, dia in enumerate(itinerario[:dias_esperados], start=1):
            actividades = dia.get("actividades")
            if not isinstance(actividades, list) or not actividades:
                raise ValueError(f"El día {indice} no trae actividades")

            normalizadas_del_dia = [
                {
                    "nombre": _recortar(a.get("nombre") or "Actividad", LIMITES["nombre"]),
                    "descripcion": str(a.get("descripcion") or ""),
                    "precio_estimado": float(a.get("precio_estimado") or 0),
                    "categoria": _recortar(a.get("categoria") or "", LIMITES["categoria"]),
                    "horario_sugerido": _recortar(
                        a.get("horario_sugerido") or "", LIMITES["horario_sugerido"]),
                    "ubicacion": _recortar(a.get("ubicacion") or "", LIMITES["ubicacion"]),
                    # Procedencia del precio: el link de la oferta cotizada, la
                    # nota del flujo y su aviso de precio dudoso. Se descartaban
                    # acá, así que el itinerario no podía mostrar de dónde salía
                    # cada número.
                    "link": _recortar(a.get("link") or "", LIMITES["link"]),
                    "nota": _recortar(a.get("nota") or "", LIMITES["nota"]),
                    "precio_sospechoso": bool(a.get("precio_sospechoso")),
                } for a in actividades
            ]

            dia_normalizado = {
                "dia": indice,
                "resumen": str(dia.get("resumen") or f"Día {indice}"),
                # El modelo no siempre devuelve las actividades en orden horario,
                # y el timeline del itinerario las muestra tal cual vienen.
                "actividades": sorted(normalizadas_del_dia, key=_hora_de_inicio),
            }

            # `destino_indice` dice a qué ciudad pertenece el día. Sin esto el
            # backend tenía que adivinar y colgaba todo del primer destino, así
            # que el segundo aparecía sin ningún día.
            for clave, valor in dia.items():
                if clave not in dia_normalizado:
                    dia_normalizado[clave] = valor

            dias_normalizados.append(dia_normalizado)

        # El destino y las fechas los manda el usuario, no la IA.
        normalizada = {
            "destinos": destinos or opcion.get("destinos") or [],
            "fecha_inicio": preferencias.get("fecha_inicio") or opcion.get("fecha_inicio"),
            "fecha_fin": preferencias.get("fecha_fin") or opcion.get("fecha_fin"),
            "tipo": str(opcion.get("tipo") or opcion.get("tipo_viaje")),
            "costo_total_estimado": float(opcion.get("costo_total_estimado") or 0),
            "imagen": opcion.get("imagen"),
            "desglose_costos": opcion.get("desglose_costos"),
            "itinerario": dias_normalizados,
        }

        # Lo que el flujo agregue de más (por ejemplo `fuente_datos`: de dónde
        # salió cada precio) se conserva tal cual. El backend lo guarda en
        # `recomendaciones_ia` y sirve para justificar los números en la defensa.
        for clave, valor in opcion.items():
            if clave not in normalizada and clave != "tipo_viaje":
                normalizada[clave] = valor

        normalizadas.append(normalizada)

    return normalizadas


# ─── Proveedores ─────────────────────────────────────────────────────────────

def _generar_con_n8n(preferencias, idioma="en"):
    url = os.getenv("N8N_WEBHOOK_URL", "").strip()
    if not url:
        return None   # sin webhook no hay nada que pedir: decide el caller

    # Sin User-Agent propio, requests manda "python-requests/x.y" y la opcion
    # "Ignore Bots" del nodo Webhook lo rechaza con 403.
    cabeceras = {
        "Content-Type": "application/json",
        "User-Agent": "TravelPlanner/1.0",
    }

    # El nodo Webhook de n8n admite dos tipos de credencial y hay que hablarle
    # en el mismo idioma que tenga configurado:
    #   - Basic Auth  -> usuario y contrasena (N8N_BASIC_USER / N8N_BASIC_PASSWORD)
    #   - Header Auth -> un token en un header (N8N_TOKEN / N8N_HEADER)
    auth = None
    usuario = os.getenv("N8N_BASIC_USER", "").strip()
    if usuario:
        auth = (usuario, os.getenv("N8N_BASIC_PASSWORD", ""))
    else:
        token = os.getenv("N8N_TOKEN", "").strip()
        if token:
            cabeceras[os.getenv("N8N_HEADER", "X-N8N-TOKEN").strip()] = token

    cuerpo = dict(preferencias)
    cuerpo["cantidad_dias"] = cantidad_de_dias(
        preferencias.get("fecha_inicio"), preferencias.get("fecha_fin")
    )
    # El flujo de n8n usa esto en el prompt para redactar los textos del
    # itinerario (nombres de actividades, descripciones, notas) en este idioma.
    cuerpo["idioma"] = idioma or "en"

    respuesta = requests.post(
        url,
        json=cuerpo,
        headers=cabeceras,
        auth=auth,
        timeout=float(os.getenv("N8N_TIMEOUT", "120")),
    )
    respuesta.raise_for_status()

    crudo, sobre = leer_sobre(respuesta.json())
    return validar_opciones(crudo, preferencias), sobre


def generar_opciones(preferencias, idioma="en"):
    """Devuelve `(opciones, proveedor_usado, sobre)`.

    `idioma` viaja a n8n para que redacte el itinerario en el idioma del usuario.
    Nunca lanza: si n8n no responde o devuelve algo que no cumple el contrato,
    cae al generador local para que el usuario igual reciba sus tres opciones.
    """
    try:
        resultado = _generar_con_n8n(preferencias, idioma)
        if resultado:
            opciones, sobre = resultado
            logger.info("Viajes generados con n8n (presupuesto: %s)", sobre["estado"])
            return _completar_imagenes(opciones, preferencias), "n8n", sobre
        logger.info("N8N_WEBHOOK_URL no está configurada: se usa el generador local")
    except Exception as exc:
        logger.warning("El flujo de n8n falló (%s): se usa el generador local", exc)

    # El generador local dimensiona las opciones sobre el presupuesto pedido,
    # así que por construcción no hay nada que avisar.
    return generar_localmente(preferencias), "local", {"estado": "ok", "aviso": None}


def _completar_imagenes(opciones, preferencias):
    """Si la IA no devolvió imagen, busca una del destino principal."""
    if all(o.get("imagen") for o in opciones):
        return opciones

    destinos = [d for d in (preferencias.get("destinos") or []) if d]
    respaldo = (obtener_imagen_destino(destinos[0]) if destinos else None) or IMAGEN_POR_DEFECTO

    for opcion in opciones:
        if not opcion.get("imagen"):
            opcion["imagen"] = respaldo

    return opciones
