import logging
import os
import re
import secrets
from datetime import date, datetime, timedelta
from functools import wraps

from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

load_dotenv()

import api_client  # noqa: E402  (necesita las variables de entorno ya cargadas)
import security  # noqa: E402
import trip_generator  # noqa: E402
from api_client import BackendError  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_secret = os.getenv("SECRET_KEY")
if not _secret:
    # Sin SECRET_KEY las sesiones no sobreviven a un reinicio: avisamos fuerte.
    _secret = secrets.token_urlsafe(32)
    logger.warning(
        "SECRET_KEY no está definida en el .env. Se generó una temporal: "
        "las sesiones se van a invalidar en cada reinicio."
    )
app.secret_key = _secret

app.permanent_session_lifetime = timedelta(days=30)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
)

security.registrar(app)

IDIOMAS = ["en", "es", "fr", "it", "de", "ru", "zh", "ja", "pt"]

IMAGEN_POR_DEFECTO = trip_generator.IMAGEN_POR_DEFECTO

# Dashboard de presupuesto: corre aparte (streamlit_budget.py) y se embebe
# como iframe en /budget. Ver README para cómo levantarlo.
STREAMLIT_URL = os.getenv("STREAMLIT_URL", "http://127.0.0.1:8501").rstrip("/")

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def login_requerido(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if quiere_json():
                return jsonify({"error": "Tenés que iniciar sesión."}), 401
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def quiere_json():
    """¿El cliente espera una respuesta JSON?

    `request.is_json` sólo mira el Content-Type de la petición, así que un
    formulario enviado por fetch como multipart daba False y recibía HTML.
    El navegador hacía `resp.json()`, explotaba, y el catch mostraba un error
    de conexión que tapaba el error real de validación.
    """
    if request.is_json:
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    # Nuestros formularios mandan este header en cada POST por fetch.
    if request.headers.get("X-CSRF-Token"):
        return True
    aceptado = request.accept_mimetypes
    return aceptado["application/json"] > aceptado["text/html"]


EXTENSIONES_DE_IMAGEN = ("png", "jpg", "jpeg", "webp", "gif")


def _guardar_foto_subida(archivo):
    """Guarda una imagen subida en static/uploads y devuelve su URL.

    Devuelve None si no hay archivo o si la extensión no es de imagen: así el
    llamador conserva la foto que ya tenía en vez de borrarla.
    """
    if not archivo or not archivo.filename:
        return None

    extension = archivo.filename.rsplit(".", 1)[-1].lower()
    if extension not in EXTENSIONES_DE_IMAGEN:
        return None

    destino = os.path.join(app.root_path, "static", "uploads")
    os.makedirs(destino, exist_ok=True)

    nombre = f"{secrets.token_hex(8)}.{extension}"
    archivo.save(os.path.join(destino, nombre))
    return url_for("static", filename=f"uploads/{nombre}")


def _guardar_sesion(datos_usuario, recordar=True):
    session.permanent = bool(recordar)
    session["user_id"] = datos_usuario.get("id_usuario")
    session["user_email"] = datos_usuario.get("email")
    session["user_nombre"] = datos_usuario.get("nombre")
    session["user_apellido"] = datos_usuario.get("apellido")
    session["user_foto"] = datos_usuario.get("foto") or ""
    session["user_lang"] = datos_usuario.get("idioma") or "en"


def _sidebar(viaje=None, drafts=None):
    """Resuelve a dónde apunta cada link de la navegación lateral.

    Se calcula en la vista y no en la plantilla porque depende de datos que la
    plantilla no tiene: si hay borradores activos y cuál es el viaje en foco.
    """
    if drafts is None:
        drafts = api_client.get_o_defecto(
            f"/viajes/usuario/{session['user_id']}/drafts", defecto=[]) or []

    # El viaje en foco: el que se está viendo, o el primer borrador, o el
    # último guardado. Sin ninguno, los links van a My Trips.
    id_viaje = (viaje or {}).get("id_viaje")
    if not id_viaje and drafts:
        id_viaje = drafts[0].get("id_viaje")
    if not id_viaje:
        guardados = [
            v for v in (api_client.get_o_defecto(
                f"/viajes/usuario/{session['user_id']}", defecto=[]) or [])
            if v.get("estado") == "guardado"
        ]
        if guardados:
            id_viaje = guardados[0].get("id_viaje")

    # El link de Compare sólo tiene sentido en el contexto de los borradores.
    # Antes bastaba con que existiera un grupo de borradores para que apareciera
    # en TODOS los viajes, incluido uno guardado hace meses, y desde ahí llevaba
    # a comparar unos borradores que no tienen nada que ver con ese viaje.
    viendo_un_borrador = bool(viaje and viaje.get("estado") == "draft")
    sin_viaje_en_foco = viaje is None
    mostrar_compare = bool(drafts) and (viendo_un_borrador or sin_viaje_en_foco)

    return {
        "compare": url_for("compare") if mostrar_compare else None,
        "itinerary": (url_for("itinerary", id_viaje=id_viaje) if id_viaje
                      else url_for("mytrips")),
        "budget": (url_for("budget", id_viaje=id_viaje) if id_viaje
                   else url_for("budget")),
        "es_draft": bool(viaje and viaje.get("estado") == "draft"),
    }


def _tiene_viajes_guardados():
    viajes = api_client.get_o_defecto(
        f"/viajes/usuario/{session['user_id']}", defecto=[]) or []
    return any(v.get("estado") == "guardado" for v in viajes)


def _formatear_fecha(valor, formato="%d/%m/%Y"):
    if not valor:
        return ""
    try:
        return datetime.fromisoformat(str(valor)).strftime(formato)
    except ValueError:
        return str(valor)


def _fecha(valor):
    try:
        return datetime.fromisoformat(str(valor)).date()
    except (TypeError, ValueError):
        return None


def _hora_de_inicio(actividad):
    """Minutos desde medianoche del `horario_sugerido` ("08:00 - 16:00").

    Sirve para ordenar el día. Lo que no se pueda leer va al final, para que una
    actividad con el horario escrito de otra forma no se pierda arriba de todo.
    """
    horario = (actividad.get("horario_sugerido") or "").strip()
    match = re.match(r"(\d{1,2}):(\d{2})", horario)
    if not match:
        return (1, 0)
    return (0, int(match.group(1)) * 60 + int(match.group(2)))


def _destino_corto(nombre):
    """Extrae únicamente 'Ciudad, País' de nombres largos (ej: 'Madrid, Community of Madrid, Spain' -> 'Madrid, Spain')."""
    if not nombre:
        return ""
    partes = [p.strip() for p in str(nombre).split(",") if p.strip()]
    if len(partes) >= 2:
        return f"{partes[0]}, {partes[-1]}"
    return partes[0] if partes else ""


app.jinja_env.filters["short_dest"] = _destino_corto


@app.context_processor
def variables_globales():
    """Datos disponibles en todas las plantillas."""
    return {
        "user_id": session.get("user_id"),
        "user_lang": session.get("user_lang", "en"),
        "idiomas": IDIOMAS,
    }


# ─── Landing y autenticación ─────────────────────────────────────────────────

@app.route("/")
def index():
    has_drafts = False
    if session.get("user_id"):
        drafts = api_client.get_o_defecto(f"/viajes/usuario/{session['user_id']}/drafts", defecto=[])
        has_drafts = len(drafts) > 0 if drafts else False
    return render_template("index.html", has_drafts=has_drafts)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    datos = request.get_json() if request.is_json else request.form

    foto_url = _guardar_foto_subida(request.files.get("foto"))         or (datos.get("foto") or "").strip() or None

    payload = {
        "nombre": (datos.get("nombre") or "").strip(),
        "apellido": (datos.get("apellido") or "").strip(),
        "email": (datos.get("email") or "").strip().lower(),
        "contrasena": datos.get("contrasena") or datos.get("password"),
        "nacionalidad": (datos.get("nacionalidad") or "").strip() or None,
        "foto": foto_url,
    }
    payload = {k: v for k, v in payload.items() if v not in (None, "")}

    try:
        api_client.post("/usuarios/", json=payload, con_usuario=False)
    except BackendError as exc:
        if quiere_json():
            return jsonify({"error": exc.mensaje}), exc.status or 400
        return render_template("register.html", error=exc.mensaje)

    if quiere_json():
        return jsonify({"redirect": url_for("login")})
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    datos = request.get_json() if request.is_json else request.form
    recordar = datos.get("remember", False)
    if isinstance(recordar, str):
        recordar = recordar.lower() in ("true", "1", "on", "yes")

    try:
        usuario = api_client.post(
            "/usuarios/login",
            json={
                "email": (datos.get("email") or "").strip().lower(),
                "contrasena": datos.get("contrasena") or datos.get("password"),
            },
            con_usuario=False,
        )
    except BackendError as exc:
        if quiere_json():
            return jsonify({"error": exc.mensaje}), exc.status or 401
        return render_template("login.html", error=exc.mensaje)

    _guardar_sesion(usuario, recordar)

    destino = datos.get("next") or request.args.get("next")
    # Sólo aceptamos rutas internas: evita open redirect.
    if not destino or not destino.startswith("/") or destino.startswith("//"):
        # Sin viajes guardados no tiene sentido mandarlo a una lista vacía:
        # va directo al formulario, que es lo único que puede hacer.
        destino = url_for("mytrips") if _tiene_viajes_guardados() else url_for("index")

    if quiere_json():
        return jsonify({"redirect": destino})
    return redirect(destino)


# Sólo POST: un logout por GET se podría disparar desde un sitio externo.
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/login/google")
def login_google():
    if not os.getenv("GOOGLE_CLIENT_ID"):
        return render_template(
            "login.html",
            error="El inicio de sesión con Google no está configurado en este entorno.",
        )
    return google.authorize_redirect(url_for("authorize_google", _external=True))


@app.route("/login/google/callback")
def authorize_google():
    try:
        google.authorize_access_token()
        user_info = google.get("https://openidconnect.googleapis.com/v1/userinfo").json()
    except Exception as exc:
        logger.error("Falló el callback de Google: %s", exc)
        return render_template("login.html", error="No se pudo completar el login con Google.")

    try:
        usuario = api_client.post("/usuarios/google-login", json=user_info, con_usuario=False)
    except BackendError as exc:
        return render_template("login.html", error=exc.mensaje)

    _guardar_sesion(usuario, recordar=True)
    return redirect(url_for("mytrips") if _tiene_viajes_guardados() else url_for("index"))


# ─── Mis viajes ──────────────────────────────────────────────────────────────

@app.route("/mytrips")
@login_requerido
def mytrips():
    viajes = api_client.get_o_defecto(
        f"/viajes/usuario/{session['user_id']}", defecto=[]
    ) or []

    # Include 'draft' trips as well and group them
    guardados = []
    drafts_vistos = set()

    for v in viajes:
        estado = v.get("estado")
        if estado == "guardado":
            guardados.append(v)
        elif estado in ("draft", "borrador"):
            destinos_list = v.get("destinos") or []
            dest_nombres = tuple(d.get("nombre", str(d)) if isinstance(d, dict) else str(d) for d in destinos_list)
            clave = v.get("group_id") or (dest_nombres, v.get("fecha_inicio"), v.get("fecha_fin"))
            if clave not in drafts_vistos:
                drafts_vistos.add(clave)
                guardados.append(v)

    hoy = date.today()

    guardados.sort(key=lambda v: _fecha(v.get("fecha_inicio")) or date.min, reverse=True)

    for v in guardados:
        inicio = _fecha(v.get("fecha_inicio"))
        fin = _fecha(v.get("fecha_fin"))
        en_curso = bool(inicio and fin and inicio <= hoy <= fin)

        v["is_draft"] = v.get("estado") in ("draft", "borrador")

        if v["is_draft"]:
            v["status_label"] = "draft"
            v["filter_class"], v["is_past"] = "next-trip", False
        elif en_curso:
            v["status_label"] = "current trip"
            v["filter_class"], v["is_past"] = "current-trip", False
        elif fin and fin < hoy:
            v["status_label"] = "last trip"
            v["filter_class"], v["is_past"] = "past-trip", True
        elif inicio and inicio > hoy:
            v["status_label"] = "upcoming trip"
            v["filter_class"], v["is_past"] = "next-trip", False
        else:
            v["status_label"] = "upcoming trip"
            v["filter_class"], v["is_past"] = "next-trip", False

        v["fecha_inicio_fmt"] = _formatear_fecha(v.get("fecha_inicio"))
        v["fecha_fin_fmt"] = _formatear_fecha(v.get("fecha_fin"))
        dest_str = [_destino_corto(d.get("nombre", str(d)) if isinstance(d, dict) else str(d)) for d in (v.get("destinos") or [])]
        v["destinos_display"] = " → ".join(dest_str) or "Sin destino"
        v["imagen"] = v.get("imagen") or IMAGEN_POR_DEFECTO

    return render_template("mytrips.html", viajes=guardados)


# ─── Generación y comparación ────────────────────────────────────────────────

@app.route("/create_trip", methods=["POST"])
@login_requerido
def create_trip():
    """Guarda las preferencias, genera las 3 variantes y las persiste."""
    datos = request.get_json()
    if not datos:
        return jsonify({"error": "No se recibieron datos del formulario."}), 400

    destinos = [d.strip() for d in (datos.get("destinos") or []) if str(d).strip()]
    if not destinos:
        return jsonify({"error": "Tenés que indicar al menos un destino."}), 400

    fecha_inicio = _fecha(datos.get("fecha_inicio"))
    fecha_fin = _fecha(datos.get("fecha_fin"))
    if not fecha_inicio or not fecha_fin:
        return jsonify({"error": "Las fechas de salida y regreso son obligatorias."}), 400
    if fecha_inicio > fecha_fin:
        return jsonify({"error": "La fecha de salida no puede ser posterior a la de regreso."}), 400

    costo_min = datos.get("costo_min")
    costo_max = datos.get("costo_max")
    if costo_min is not None and costo_max is not None and float(costo_min) > float(costo_max):
        return jsonify({"error": "El presupuesto mínimo no puede superar al máximo."}), 400

    preferencias = {
        "id_usuario": session["user_id"],
        "destinos": destinos,
        "origen": datos.get("origen"),
        "costo_min": costo_min,
        "costo_max": costo_max,
        "cantidad_personas": datos.get("cantidad_personas"),
        "grupo": datos.get("grupo"),
        "edades_viajeros": datos.get("edades_viajeros"),
        "hospedaje": datos.get("hospedaje"),
        "tipo_transporte": datos.get("tipo_transporte"),
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "act_preferidas": datos.get("act_preferidas"),
        "otros": datos.get("otros"),
    }
    preferencias = {k: v for k, v in preferencias.items() if v not in (None, "")}

    # 1) Guardar las preferencias del usuario.
    try:
        respuesta = api_client.post("/preferencias/", json=preferencias)
        id_preferencia = (respuesta or {}).get("id")
    except BackendError as exc:
        logger.error("No se pudieron guardar las preferencias: %s", exc.mensaje)
        return jsonify({"error": f"No se pudieron guardar tus preferencias: {exc.mensaje}"}), 400

    # 2) Generar las 3 variantes con el flujo de n8n.
    try:
        opciones, proveedor, presupuesto = trip_generator.generar_opciones(preferencias)
    except Exception as exc:
        logger.exception("Falló la generación de viajes")
        return jsonify({"error": f"No se pudieron generar los viajes: {exc}"}), 500

    # 3) Persistirlas como borradores.
    try:
        api_client.post("/viajes/generate", json={
            "id_usuario": session["user_id"],
            "id_user_preferences": id_preferencia,
            "opciones": opciones,
        }, timeout=60)
    except BackendError as exc:
        return jsonify({"error": f"No se pudieron guardar los viajes: {exc.mensaje}"}), 502

    # El aviso es de esta generación, no del viaje: vive en la sesión hasta que
    # el usuario elija una opción o genere otro grupo.
    session["presupuesto"] = presupuesto

    logger.info("Viajes generados para el usuario %s con '%s'", session["user_id"], proveedor)
    return jsonify({"redirect": url_for("compare"), "proveedor": proveedor,
                    "presupuesto": presupuesto["estado"]})


@app.route("/compare")
@login_requerido
def compare():
    drafts = api_client.get_o_defecto(
        f"/viajes/usuario/{session['user_id']}/drafts", defecto=[]
    ) or []

    if not drafts:
        return redirect(url_for("index"))

    viajes_por_tipo = {"Economy": None, "Balanced": None, "Luxury": None}
    for draft in drafts:
        dest_str = [d.get("nombre", str(d)) if isinstance(d, dict) else str(d) for d in (draft.get("destinos") or [])]
        draft["destinos_display"] = " → ".join(dest_str)
        draft["fecha_inicio_fmt"] = _formatear_fecha(draft.get("fecha_inicio"), "%d %b")
        draft["fecha_fin_fmt"] = _formatear_fecha(draft.get("fecha_fin"), "%d %b")

        inicio, fin = _fecha(draft.get("fecha_inicio")), _fecha(draft.get("fecha_fin"))
        draft["dias"] = (fin - inicio).days + 1 if inicio and fin else 0

        if draft.get("tipo_viaje") in viajes_por_tipo:
            viajes_por_tipo[draft["tipo_viaje"]] = draft

    # Los "highlights" salen de las actividades reales de cada variante.
    for tipo, viaje in viajes_por_tipo.items():
        if not viaje:
            continue
        detalle = api_client.get_o_defecto(f"/viajes/{viaje['id_viaje']}", defecto={}) or {}
        viaje["highlights"] = _highlights_de(detalle)
        viaje["costos"] = detalle.get("costos") or {}

    presupuesto = session.get("presupuesto") or {"estado": "ok", "aviso": None}

    return render_template("compare.html", viajes_por_tipo=viajes_por_tipo,
                           nav=_sidebar(drafts=drafts),
                           presupuesto=presupuesto)


def _highlights_de(detalle, cantidad=3):
    """Elige las actividades más representativas de un viaje."""
    actividades = [
        act
        for itin in (detalle.get("itinerarios") or [])
        for act in (itin.get("actividades") or [])
    ]
    if not actividades:
        return []

    # Las más caras suelen ser las que definen el carácter del plan.
    destacadas = sorted(
        actividades, key=lambda a: a.get("precio_estimado") or 0, reverse=True
    )

    vistas, resultado = set(), []
    for act in destacadas:
        nombre = act.get("nombre")
        if nombre and nombre not in vistas:
            vistas.add(nombre)
            resultado.append(nombre)
        if len(resultado) == cantidad:
            break

    return resultado


@app.route("/select_trip/<int:id_viaje>", methods=["POST"])
@login_requerido
def select_trip(id_viaje):
    try:
        api_client.post(f"/viajes/{id_viaje}/select")
    except BackendError as exc:
        logger.warning("No se pudo confirmar el viaje %s: %s", id_viaje, exc.mensaje)
        return redirect(url_for("compare"))

    # El aviso era de este grupo de borradores, que acaba de resolverse.
    session.pop("presupuesto", None)
    return redirect(url_for("itinerary", id_viaje=id_viaje))


# ─── Itinerario ──────────────────────────────────────────────────────────────

def _cargar_viaje(id_viaje):
    """Trae el viaje del backend y lo prepara para las plantillas."""
    viaje = api_client.get(f"/viajes/{id_viaje}")

    inicio = _fecha(viaje.get("fecha_inicio"))
    fin = _fecha(viaje.get("fecha_fin"))
    hoy = date.today()

    viaje["fecha_inicio_fmt"] = _formatear_fecha(viaje.get("fecha_inicio"), "%d %b")
    viaje["fecha_fin_fmt"] = _formatear_fecha(viaje.get("fecha_fin"), "%d %b")
    # Fetch preferences to ensure 'cantidad_personas' is available
    if "cantidad_personas" not in viaje:
        id_prefs = viaje.get("id_user_preferences")
        if id_prefs:
            try:
                prefs = api_client.get(f"/preferencias/{id_prefs}")
                viaje["cantidad_personas"] = prefs.get("cantidad_personas", 1)
            except Exception:
                viaje["cantidad_personas"] = 1
        else:
            viaje["cantidad_personas"] = 1

    destinos_raw = viaje.get("destinos") or []
    destinos_obj = []
    destinos_str = []
    destinos_short = []
    for d in destinos_raw:
        if isinstance(d, dict):
            nombre = d.get("nombre", "")
            d_short = _destino_corto(nombre)
            destinos_obj.append(d)
            destinos_str.append(nombre)
            destinos_short.append(d_short)
        else:
            d_short = _destino_corto(str(d))
            destinos_obj.append({"nombre": str(d)})
            destinos_str.append(str(d))
            destinos_short.append(d_short)

    viaje["destinos_obj"] = destinos_obj
    viaje["destinos_display"] = " → ".join(destinos_short) or "Sin destino"
    viaje["titulo_corto"] = " → ".join(destinos_short) or viaje.get("titulo") or "Sin destino"
    viaje["destino_principal"] = destinos_short[0] if destinos_short else (destinos_str[0] if destinos_str else "")
    viaje["imagen"] = viaje.get("imagen") or IMAGEN_POR_DEFECTO
    viaje["dias_totales"] = (fin - inicio).days + 1 if inicio and fin else 0

    # Countdown real.
    if inicio:
        dias_restantes = (inicio - hoy).days
        if dias_restantes > 0:
            viaje["countdown"] = dias_restantes
            viaje["countdown_estado"] = "faltan"
        elif fin and inicio <= hoy <= fin:
            viaje["countdown"] = (fin - hoy).days
            viaje["countdown_estado"] = "en_curso"
        else:
            viaje["countdown"] = abs((hoy - (fin or inicio)).days)
            viaje["countdown_estado"] = "finalizado"
    else:
        viaje["countdown"] = 0
        viaje["countdown_estado"] = "desconocido"

    itinerarios = sorted(viaje.get("itinerarios") or [], key=lambda i: i.get("dia") or 0)

    destino_anterior = None
    for indice, itin in enumerate(itinerarios):
        fecha_dia = inicio + timedelta(days=indice) if inicio else None
        itin["fecha_fmt"] = fecha_dia.strftime("%d %b") if fecha_dia else ""
        itin["fecha_iso"] = fecha_dia.isoformat() if fecha_dia else ""

        # La base las devuelve en el orden en que se insertaron: una actividad
        # agregada a mano caería al final del día aunque sea de la mañana.
        itin["actividades"] = sorted(itin.get("actividades") or [], key=_hora_de_inicio)

        itin["actividades_cotizadas"] = round(
            sum(a.get("precio_estimado") or 0 for a in itin["actividades"]), 2
        )

        destino_del_dia = ""
        if fecha_dia:
            for dest in destinos_obj:
                ll = _fecha(dest.get("fecha_llegada"))
                pa = _fecha(dest.get("fecha_partida"))
                if ll and pa and ll <= fecha_dia <= pa:
                    destino_del_dia = dest.get("nombre")
                    break
        
        if not destino_del_dia and destinos_str:
            destino_del_dia = destinos_str[0]
            
        itin["destino_del_dia"] = destino_del_dia
        
        if destino_anterior is not None and destino_del_dia != destino_anterior:
            itin["cambio_destino"] = True
        else:
            itin["cambio_destino"] = False
            
        destino_anterior = destino_del_dia

        for act in (itin.get("actividades") or []):
            if not act.get("destino"):
                act["destino"] = destino_del_dia

    viaje["itinerarios"] = itinerarios

    _calcular_costos_por_dia(viaje, _personas_del_viaje(viaje))
    return viaje


def _personas_del_viaje(viaje):
    """Cuántos viajan, según las preferencias que originaron el viaje.

    Hace falta para pasar el desglose (que es del grupo) a la misma unidad que
    los precios de las actividades (que son por persona).
    """
    id_preferencia = viaje.get("id_user_preferences")
    if not id_preferencia:
        return 1
    prefs = api_client.get_o_defecto(f"/preferencias/{id_preferencia}", defecto={}) or {}
    return prefs.get("cantidad_personas") or 1


# Categorías con las que el flujo etiqueta las actividades. Se agrupan por
# rubro porque el vuelo y el check-in llegan como actividades del itinerario,
# no sólo dentro del desglose de costos.
RUBRO_POR_CATEGORIA = {
    "transporte": "transporte", "transport": "transporte", "vuelo": "transporte",
    "traslado": "transporte",
    "alojamiento": "alojamiento", "hospedaje": "alojamiento", "hotel": "alojamiento",
    "accommodation": "alojamiento", "lodging": "alojamiento",
    "gastronomía": "comidas", "gastronomia": "comidas", "comida": "comidas",
    "comidas": "comidas", "food": "comidas", "restaurante": "comidas",
}


# El flujo informa de dónde sacó cada precio. Las claves varían según el rubro
# (`vuelos` para transporte, `hoteles` para alojamiento), así que cada rubro
# acepta varios nombres y se queda con el primero que venga.
CLAVES_DE_FUENTE = {
    "transporte": ("transporte", "vuelos", "vuelo", "flights"),
    "alojamiento": ("alojamiento", "hoteles", "hotel", "hotels"),
    "comidas": ("comidas", "comida", "food"),
    "actividades": ("actividades", "actividad", "activities"),
}


def _fuentes_por_rubro(viaje):
    """Traduce `fuente_datos.fuentes` a un origen por rubro del presupuesto."""
    fuente_datos = viaje.get("fuente_datos")
    if not isinstance(fuente_datos, dict):
        return {}

    fuentes = fuente_datos.get("fuentes")
    if not isinstance(fuentes, dict):
        return {}

    resultado = {}
    for rubro, claves in CLAVES_DE_FUENTE.items():
        for clave in claves:
            valor = fuentes.get(clave)
            if isinstance(valor, str) and valor.strip():
                resultado[rubro] = valor.strip()
                break
    return resultado


def _rubro_de(actividad):
    """A qué rubro del presupuesto corresponde una actividad."""
    categoria = (actividad.get("categoria") or "").strip().lower()
    return RUBRO_POR_CATEGORIA.get(categoria, "actividades")


def _calcular_costos_por_dia(viaje, cantidad_personas=1):
    """Arma el gasto de cada día a partir de sus propias actividades.

    Antes esto escalaba los precios con un factor `costo_actividades / total
    cotizado`. Estaba mal: el flujo manda el vuelo y el alojamiento COMO
    actividades del itinerario y además dentro de `desglose_costos`, así que el
    divisor incluía plata que no era de actividades y achicaba todo (un día de
    $561 aparecía como $100).

    Ahora cada rubro se arma con las actividades reales de ese día, que es lo
    que el usuario puede sumar mirando las tarjetas. Lo que el itinerario no
    cubre —comer todos los días, moverse por la ciudad— se completa con el
    per-diem del desglose y se marca como estimado.
    """
    itinerarios = viaje.get("itinerarios") or []
    if not itinerarios:
        return

    costos = viaje.get("costos") or {}
    dias = len(itinerarios)
    personas = max(int(cantidad_personas or 1), 1)

    # El desglose viene en total del grupo; las actividades, por persona.
    def por_persona_por_dia(clave):
        return (costos.get(clave) or 0) / dias / personas

    per_diem = {
        "comidas": por_persona_por_dia("costo_comidas"),
        "transporte": por_persona_por_dia("costo_transporte"),
        "alojamiento": por_persona_por_dia("costo_alojamiento"),
    }

    for itin in itinerarios:
        rubros = {"actividades": 0.0, "comidas": 0.0, "transporte": 0.0, "alojamiento": 0.0}
        cubiertos = set()
        for actividad in itin.get("actividades") or []:
            rubro = _rubro_de(actividad)
            rubros[rubro] += actividad.get("precio_estimado") or 0
            # Se anota la presencia, no el monto: un vuelo de vuelta que ya
            # viene incluido en el de ida cuesta $0, y eso es un dato, no una
            # ausencia. Mirando el monto se le sumaba el promedio diario encima.
            cubiertos.add(rubro)

        cotizado = round(sum(rubros.values()), 2)

        # Sólo se estima el rubro que ese día no tiene ninguna actividad: si el
        # itinerario ya cotizó la cena, sumarle el per-diem la contaría dos veces.
        estimados = {
            rubro: round(monto, 2)
            for rubro, monto in per_diem.items()
            if rubro not in cubiertos and monto > 0
        }

        itin["costos_dia"] = {
            rubro: round(rubros[rubro] + estimados.get(rubro, 0), 2)
            for rubro in rubros
        }
        itin["costos_dia_estimados"] = sorted(estimados)
        itin["actividades_cotizadas"] = cotizado
        itin["total_dia"] = round(cotizado + sum(estimados.values()), 2)

    viaje["hay_costos_por_dia"] = True


@app.route("/itinerary/<int:id_viaje>")
@login_requerido
def itinerary(id_viaje):
    try:
        viaje = _cargar_viaje(id_viaje)
    except BackendError as exc:
        if exc.status == 404:
            return render_template("404.html"), 404
        if exc.status == 403:
            return render_template("403.html"), 403
        return render_template("500.html", detalle=exc.mensaje), 500

    # Para el datalist del formulario de actividades: las categorías que ya usa
    # el viaje, que son las que tienen icono y color propios en la tarjeta.
    categorias = sorted({
        (act.get("categoria") or "").strip()
        for itin in viaje.get("itinerarios") or []
        for act in itin.get("actividades") or []
        if (act.get("categoria") or "").strip()
    })

    return render_template("itinerary.html", viaje=viaje, nav=_sidebar(viaje),
                           categorias_actividad=categorias,
                           fuentes=_fuentes_por_rubro(viaje))


# Alias histórico: /viaje/<id> apunta al mismo itinerario.
@app.route("/viaje/<int:id_viaje>")
@login_requerido
def detalle_viaje(id_viaje):
    return redirect(url_for("itinerary", id_viaje=id_viaje))


@app.route("/trips/<int:id_viaje>", methods=["DELETE"])
@login_requerido
def eliminar_viaje(id_viaje):
    try:
        api_client.delete(f"/viajes/{id_viaje}")
    except BackendError as exc:
        return jsonify({"error": exc.mensaje}), exc.status or 500
    return jsonify({"ok": True})


# El viaje en sí no se edita desde la web: lo que se puede tocar del plan que
# armó la IA son las actividades (ver más arriba). Las fechas y el destino
# definen el itinerario entero, así que cambiarlos a mano dejaba días sin
# actividades y actividades fuera de rango.


# ─── Actividades del itinerario ──────────────────────────────────────────────
# El viaje que sugiere la IA es un punto de partida: desde /itinerary el usuario
# puede borrar lo que no le sirve, editar lo que le sirve a medias y agregar lo
# suyo. El backend recalcula el costo del viaje en cada uno de esos cambios.

CAMPOS_ACTIVIDAD = {
    "nombre", "descripcion", "precio_estimado",
    "categoria", "horario_sugerido", "ubicacion",
}


def _payload_actividad(datos):
    """Deja pasar sólo los campos editables, ya limpios."""
    payload = {}
    for campo in CAMPOS_ACTIVIDAD:
        if campo not in datos:
            continue
        valor = datos[campo]
        if campo == "precio_estimado":
            try:
                payload[campo] = float(valor or 0)
            except (TypeError, ValueError):
                return None, "El precio tiene que ser un número."
        else:
            payload[campo] = (valor or "").strip()
    return payload, None


@app.route("/activities", methods=["POST"])
@login_requerido
def crear_actividad():
    datos = request.get_json() or {}

    id_itinerario = datos.get("id_itinerario")
    if not id_itinerario:
        return jsonify({"error": "Falta el día al que agregar la actividad."}), 400

    payload, error = _payload_actividad(datos)
    if error:
        return jsonify({"error": error}), 400
    if not payload.get("nombre"):
        return jsonify({"error": "El título de la actividad es obligatorio."}), 400

    payload["id_itinerario"] = id_itinerario

    try:
        respuesta = api_client.post("/actividades/", json=payload)
    except BackendError as exc:
        return jsonify({"error": exc.mensaje}), exc.status or 500
    return jsonify(respuesta or {"ok": True}), 201


@app.route("/activities/<int:id_actividad>", methods=["PATCH"])
@login_requerido
def editar_actividad(id_actividad):
    datos = request.get_json() or {}

    payload, error = _payload_actividad(datos)
    if error:
        return jsonify({"error": error}), 400
    if not payload:
        return jsonify({"error": "No hay nada para actualizar."}), 400
    if "nombre" in payload and not payload["nombre"]:
        return jsonify({"error": "El título de la actividad es obligatorio."}), 400

    try:
        respuesta = api_client.request("PATCH", f"/actividades/{id_actividad}", json=payload)
    except BackendError as exc:
        return jsonify({"error": exc.mensaje}), exc.status or 500
    return jsonify(respuesta or {"ok": True})


@app.route("/activities/<int:id_actividad>", methods=["DELETE"])
@login_requerido
def eliminar_actividad(id_actividad):
    try:
        respuesta = api_client.delete(f"/actividades/{id_actividad}")
    except BackendError as exc:
        return jsonify({"error": exc.mensaje}), exc.status or 500
    return jsonify(respuesta or {"ok": True})


# ─── Presupuesto ─────────────────────────────────────────────────────────────

@app.route("/budget")
@app.route("/budget/<int:id_viaje>")
@login_requerido
def budget(id_viaje=None):
    if id_viaje is None:
        viajes = api_client.get_o_defecto(
            f"/viajes/usuario/{session['user_id']}", defecto=[]
        ) or []
        guardados = [v for v in viajes if v.get("estado") == "guardado"]
        if not guardados:
            return render_template("budget.html", viaje=None, viajes=[],
                                   nav=_sidebar())
        guardados.sort(key=lambda v: _fecha(v.get("fecha_inicio")) or date.min, reverse=True)
        id_viaje = guardados[0]["id_viaje"]

    try:
        viaje = _cargar_viaje(id_viaje)
    except BackendError as exc:
        if exc.status == 404:
            return render_template("404.html"), 404
        return render_template("500.html", detalle=exc.mensaje), 500

    costos = viaje.get("costos") or {}

    otros_viajes = api_client.get_o_defecto(
        f"/viajes/usuario/{session['user_id']}", defecto=[]
    ) or []

    return render_template(
        "budget.html",
        nav=_sidebar(viaje),
        viaje=viaje,
        costos=costos,
        streamlit_url=STREAMLIT_URL,
        viajes=[v for v in otros_viajes if v.get("estado") == "guardado"],
    )


# ─── Configuración ───────────────────────────────────────────────────────────

@app.route("/settings")
@login_requerido
def settings():
    perfil = api_client.get_o_defecto(f"/usuarios/{session['user_id']}", defecto={}) or {}
    return render_template("settings.html", perfil=perfil)


@app.route("/settings/profile", methods=["POST"])
@login_requerido
def actualizar_perfil():
    # El formulario puede llegar como JSON (cambio de contraseña) o como
    # multipart cuando el usuario sube una foto desde su computadora.
    datos = request.get_json(silent=True) if request.is_json else request.form

    payload = {
        campo: datos.get(campo)
        for campo in ("nombre", "apellido", "email", "nacionalidad", "foto")
        if datos.get(campo) not in (None, "")
    }

    subida = _guardar_foto_subida(request.files.get("foto"))
    if subida:
        payload["foto"] = subida

    if datos.get("contrasena"):
        payload["contrasena"] = datos["contrasena"]

    if not payload:
        return jsonify({"error": "No hay cambios para guardar."}), 400

    try:
        actualizado = api_client.put(f"/usuarios/{session['user_id']}", json=payload)
    except BackendError as exc:
        return jsonify({"error": exc.mensaje}), exc.status or 400

    session["user_nombre"] = actualizado.get("nombre", session.get("user_nombre"))
    session["user_apellido"] = actualizado.get("apellido", session.get("user_apellido"))
    session["user_email"] = actualizado.get("email", session.get("user_email"))
    session["user_foto"] = actualizado.get("foto") or ""

    return jsonify({"ok": True, "mensaje": "Perfil actualizado."})


@app.route("/settings/language", methods=["POST"])
@login_requerido
def actualizar_idioma():
    idioma = (request.get_json() or {}).get("idioma")
    if idioma not in IDIOMAS:
        return jsonify({"error": "Idioma no soportado."}), 400

    try:
        api_client.put(f"/usuarios/{session['user_id']}", json={"idioma": idioma})
    except BackendError as exc:
        return jsonify({"error": exc.mensaje}), exc.status or 400

    session["user_lang"] = idioma
    return jsonify({"ok": True})


@app.route("/settings/account", methods=["DELETE"])
@login_requerido
def eliminar_cuenta():
    try:
        api_client.delete(f"/usuarios/{session['user_id']}")
    except BackendError as exc:
        return jsonify({"error": exc.mensaje}), exc.status or 400

    session.clear()
    return jsonify({"ok": True, "redirect": url_for("index")})


# ─── Errores ─────────────────────────────────────────────────────────────────

@app.errorhandler(400)
def solicitud_invalida(e):
    detalle = getattr(e, "description", "La solicitud no es válida.")
    if quiere_json():
        return jsonify({"error": detalle}), 400
    return render_template("400.html", detalle=detalle), 400


@app.errorhandler(403)
def prohibido(_e):
    return render_template("403.html"), 403


@app.errorhandler(404)
def no_encontrado(_e):
    if quiere_json():
        return jsonify({"error": "Recurso no encontrado."}), 404
    return render_template("404.html"), 404


@app.errorhandler(500)
def error_interno(e):
    logger.exception("Error interno no controlado: %s", e)
    if quiere_json():
        return jsonify({"error": "Error interno del servidor."}), 500
    return render_template("500.html"), 500


# ─── Arranque ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.getenv("BACKEND_API_KEY"):
        logger.warning(
            "BACKEND_API_KEY no está definida: el backend va a rechazar todas las llamadas."
        )

    app.run(
        debug=os.getenv("FLASK_DEBUG", "true").lower() == "true",
        port=int(os.getenv("PORT", 8080)),
    )
