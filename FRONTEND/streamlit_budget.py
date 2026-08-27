"""Dashboard interactivo de presupuesto, embebido como iframe en /budget.

Corre como un proceso Streamlit aparte (puerto 8501 por defecto) y no depende
de Flask ni de su sesión: `budget.html` le pasa `id_viaje`, `id_usuario` y
`lang` por query string, y este script llama al mismo backend que el resto del
frontend, con la misma X-API-KEY (ver FRONTEND/.env) + X-User-Id. El backend
es quien decide si ese usuario puede ver ese viaje; acá no se asume nada.

El tema (claro, verde de marca) se fuerza desde .streamlit/config.toml: la
página que lo embebe es blanca, así que seguir el modo oscuro del sistema
dejaría texto claro sobre fondo blanco.

Levantar a mano:
    cd FRONTEND
    streamlit run streamlit_budget.py --server.port 8501
`run.bat`, desde la raíz, ya lo hace junto con el backend y el frontend.
"""

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:5000").rstrip("/")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")
TIMEOUT = float(os.getenv("BACKEND_TIMEOUT", "15"))

# Los mismos colores que usaba el Chart.js anterior, para que la página no
# cambie de identidad al reemplazar la implementación.
VERDE = "#006d5b"
COLOR = {
    "alojamiento": "#0f766e",
    "transporte": "#0369a1",
    "actividades": "#7c3aed",
    "comidas": "#b45309",
}
GRIS_TEXTO = "#1f2937"
GRIS_SUAVE = "#e5e7eb"

TEXTOS = {
    "en": {
        "destinations": "Destinations", "all": "All", "day_range": "Day range",
        "per_person": "Per person", "of": "of",
        "kpi_total": "Trip total", "kpi_per_day": "Cost per day",
        "kpi_budget": "Budget used", "kpi_selection": "Selected range",
        "no_budget": "no budget set", "over_budget": "over budget", "left": "left",
        "tab_overview": "Overview", "tab_daily": "Day by day",
        "tab_categories": "Categories", "tab_compare": "Compare options",
        "tab_simulator": "What-if",
        "lodging": "Accommodation", "transport": "Transport",
        "activities": "Activities", "food": "Food",
        "category": "Category", "amount": "Amount", "share": "Share",
        "per_day_chart": "Daily spending (fixed costs prorated + real activities)",
        "cumulative": "Cumulative spending across the trip",
        "day_detail": "Day detail", "pick_day": "Pick a day",
        "activity": "Activity", "time": "Time", "place": "Place", "price": "Price",
        "quoted": "Quoted price",
        "quoted_note": "Quoted price of each activity. The totals above distribute the "
                       "official activities budget across days, weighted by these prices.",
        "fixed_costs": "Prorated fixed costs", "day_total": "Day total",
        "no_activities": "No priced activities in this selection.",
        "by_category": "Activity spending by category",
        "filter_categories": "Filter categories", "download": "Download CSV",
        "compare_intro": "The three variants generated for this trip.",
        "compare_none": "The other options were discarded when this trip was confirmed, "
                        "so there is nothing left to compare.",
        "sim_intro": "Edit any amount and the totals recalculate live.",
        "sim_reset": "Reset to original", "sim_total": "Simulated total",
        "sim_vs": "vs. original", "simulated": "Simulated",
        "insight_title": "Automatic insight",
        "no_trip": "No trip selected.",
        "no_costs": "This trip has no cost breakdown loaded.",
        "conn_error": "Couldn't reach the backend",
        "days_short": "days", "day_short": "Day", "budget_line": "budget",
        "avg_day": "avg/day", "people": "people",
    },
    "es": {
        "destinations": "Destinos", "all": "Todos", "day_range": "Rango de días",
        "per_person": "Por persona", "of": "de",
        "kpi_total": "Total del viaje", "kpi_per_day": "Promedio por día",
        "kpi_budget": "Presupuesto usado", "kpi_selection": "Tramo seleccionado",
        "no_budget": "sin presupuesto fijado", "over_budget": "por encima",
        "left": "disponible",
        "tab_overview": "Resumen", "tab_daily": "Día a día",
        "tab_categories": "Categorías", "tab_compare": "Comparar opciones",
        "tab_simulator": "Simulador",
        "lodging": "Alojamiento", "transport": "Transporte",
        "activities": "Actividades", "food": "Comidas",
        "category": "Categoría", "amount": "Monto", "share": "Peso",
        "per_day_chart": "Gasto diario (costos fijos prorrateados + actividades reales)",
        "cumulative": "Gasto acumulado a lo largo del viaje",
        "day_detail": "Detalle del día", "pick_day": "Elegí un día",
        "activity": "Actividad", "time": "Horario", "place": "Lugar", "price": "Precio",
        "quoted": "Precio cotizado",
        "quoted_note": "Precio cotizado de cada actividad. Los totales de arriba reparten "
                       "el presupuesto oficial de actividades entre los días, usando estos "
                       "precios como peso.",
        "fixed_costs": "Costos fijos prorrateados", "day_total": "Total del día",
        "no_activities": "No hay actividades con precio en esta selección.",
        "by_category": "Gasto en actividades por categoría",
        "filter_categories": "Filtrar categorías", "download": "Descargar CSV",
        "compare_intro": "Las tres variantes generadas para este viaje.",
        "compare_none": "Las otras opciones se descartaron al confirmar este viaje, "
                        "así que no queda nada para comparar.",
        "sim_intro": "Editá cualquier monto y los totales se recalculan solos.",
        "sim_reset": "Volver a los valores originales", "sim_total": "Total simulado",
        "sim_vs": "vs. original", "simulated": "Simulado",
        "insight_title": "Análisis automático",
        "no_trip": "No se seleccionó ningún viaje.",
        "no_costs": "Este viaje no tiene costos cargados.",
        "conn_error": "No se pudo conectar con el servidor",
        "days_short": "días", "day_short": "Día", "budget_line": "presupuesto",
        "avg_day": "prom/día", "people": "personas",
    },
}

st.set_page_config(page_title="Budget", layout="wide", initial_sidebar_state="collapsed")

# Sólo se esconde el cromo de Streamlit (menú, header, footer): el dashboard
# vive dentro de la página del sitio y no debe parecer una app aparte.
st.markdown(
    """
    <style>
    #MainMenu, header[data-testid="stHeader"], footer,
    [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
    .block-container { padding: 0.5rem 0.75rem 2rem 0.75rem; max-width: 100%; }
    [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.72rem; font-weight: 700;
                                    letter-spacing: .5px; text-transform: uppercase; }
    /* Estilo de pills para que se parezcan a los del itinerario */
    div[data-testid="stVerticalBlock"] div[data-testid="stPills"] button {
        border-radius: 0.25rem !important;
        border: 1px solid #dee2e6 !important;
        background-color: #f8f9fa !important;
        color: #6c757d !important;
        font-weight: 600 !important;
        padding: 0.25rem 0.5rem !important;
        min-height: 0 !important;
    }
    div[data-testid="stVerticalBlock"] div[data-testid="stPills"] button[aria-pressed="true"],
    div[data-testid="stVerticalBlock"] div[data-testid="stPills"] button[data-pressed="true"] {
        background-color: #006d5b !important;
        color: white !important;
        border-color: #006d5b !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ─── Backend ─────────────────────────────────────────────────────────────────

def cabeceras(id_usuario):
    h = {"X-API-KEY": BACKEND_API_KEY}
    if id_usuario:
        h["X-User-Id"] = str(id_usuario)
    return h


@st.cache_data(ttl=30, show_spinner=False)
def cargar_viaje(id_viaje, id_usuario):
    resp = requests.get(
        f"{BACKEND_URL}/viajes/{id_viaje}", headers=cabeceras(id_usuario), timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=30, show_spinner=False)
def cargar_preferencias(id_preferencia, id_usuario):
    if not id_preferencia:
        return {}
    resp = requests.get(
        f"{BACKEND_URL}/preferencias/{id_preferencia}",
        headers=cabeceras(id_usuario), timeout=TIMEOUT,
    )
    return resp.json() if resp.status_code == 200 else {}


@st.cache_data(ttl=30, show_spinner=False)
def cargar_variantes(group_id, id_usuario):
    """Las otras variantes (Economy/Balanced/Luxury) del mismo grupo.

    Sólo existen mientras son borradores: al confirmar una, el backend descarta
    el resto (`POST /viajes/<id>/select`). Devuelve [] en ese caso.
    """
    if not group_id or not id_usuario:
        return []

    resp = requests.get(
        f"{BACKEND_URL}/viajes/usuario/{id_usuario}/drafts",
        headers=cabeceras(id_usuario), timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        return []

    variantes = []
    for draft in resp.json() or []:
        if draft.get("group_id") != group_id:
            continue
        try:
            variantes.append(cargar_viaje(draft["id_viaje"], id_usuario))
        except requests.exceptions.RequestException:
            continue
    return variantes


def parse_fecha(valor):
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return None


def dinero(valor):
    return f"${valor:,.0f}"


def dinero_md(valor):
    """Igual que `dinero()`, pero para markdown.

    Streamlit trata `$...$` como fórmula LaTeX: dos importes en la misma línea
    se comen el texto del medio y lo renderizan como ecuación. Escapar el signo
    lo evita.
    """
    return f"\\${valor:,.0f}"


def estilo(fig, alto=300, leyenda=True):
    """Estilo común de los gráficos: fondo transparente y sin ruido visual."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif",
                  size=13, color=GRIS_TEXTO),
        margin=dict(t=20, b=8, l=8, r=8),
        height=alto,
        showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=-0.24, x=0,
                    bgcolor="rgba(0,0,0,0)", title_text=""),
        hoverlabel=dict(bgcolor="white", bordercolor=GRIS_SUAVE, font_size=12),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRIS_SUAVE)
    fig.update_yaxes(gridcolor=GRIS_SUAVE, zeroline=False, linecolor="rgba(0,0,0,0)")
    return fig


# ─── Parámetros y carga ──────────────────────────────────────────────────────

params = st.query_params
id_viaje = params.get("id_viaje")
id_usuario = params.get("id_usuario")
lang = "es" if params.get("lang") == "es" else "en"
t = TEXTOS[lang]
es = lang == "es"

if not id_viaje:
    st.info(t["no_trip"], icon=":material/info:")
    st.stop()

try:
    viaje = cargar_viaje(id_viaje, id_usuario)
except requests.exceptions.RequestException as exc:
    st.error(f"{t['conn_error']}: {exc}", icon=":material/wifi_off:")
    st.stop()

costos = viaje.get("costos") or {}
if not costos:
    st.warning(t["no_costs"], icon=":material/warning:")
    st.stop()

prefs = cargar_preferencias(viaje.get("id_user_preferences"), id_usuario)
cantidad_personas = viaje.get("cantidad_personas") or prefs.get("cantidad_personas") or 1
presupuesto_max = prefs.get("costo_max")

destinos = viaje.get("destinos") or []
itinerarios = sorted(viaje.get("itinerarios") or [], key=lambda i: i.get("dia") or 0)
fecha_inicio = parse_fecha(viaje.get("fecha_inicio"))
dias_totales = len(itinerarios) or 1

# Costos fijos del viaje (los del desglose que devolvió el backend).
FIJOS = {
    "alojamiento": costos.get("costo_alojamiento") or 0,
    "transporte": costos.get("costo_transporte") or 0,
    "comidas": costos.get("costo_comidas") or 0,
}
cat_actividades = costos.get("costo_actividades") or 0
total_viaje = (costos.get("costo_total_ajustado") or viaje.get("costo_total_estimado")
               or costos.get("costo_total_base") or 0)

# Cada día del itinerario se asigna al destino cuyo rango de fechas lo contiene
# (misma lógica que `_cargar_viaje()` en FRONTEND/app.py).
filas = []
dia_destino = {}
for indice, itin in enumerate(itinerarios):
    fecha_dia = fecha_inicio + timedelta(days=indice) if fecha_inicio else None
    destino_dia = None
    if fecha_dia:
        for d in destinos:
            llegada = parse_fecha(d.get("fecha_llegada"))
            partida = parse_fecha(d.get("fecha_partida"))
            if llegada and partida and llegada <= fecha_dia <= partida:
                destino_dia = d.get("nombre")
                break
    if not destino_dia and destinos:
        destino_dia = destinos[0].get("nombre")
    dia_destino[itin.get("dia")] = destino_dia or ""

    # Por horario y no por orden de inserción: una actividad agregada a mano
    # desde /itinerary llega última aunque sea de la mañana.
    actividades_del_dia = sorted(
        itin.get("actividades") or [],
        key=lambda a: (a.get("horario_sugerido") or "~"),
    )

    for act in actividades_del_dia:
        filas.append({
            "dia": itin.get("dia"),
            "destino": act.get("destino") or destino_dia or "",
            "actividad": act.get("nombre") or "",
            "categoria": act.get("categoria") or ("Otros" if es else "Other"),
            "horario": act.get("horario_sugerido") or "",
            "lugar": act.get("ubicacion") or "",
            "precio": float(act.get("precio_estimado") or 0),
        })

df_actividades = pd.DataFrame(filas, columns=[
    "dia", "destino", "actividad", "categoria", "horario", "lugar", "precio"
])
dias_disponibles = [i.get("dia") for i in itinerarios if i.get("dia") is not None] or [1]

# El desglose de n8n trae un total de categoría para actividades que no coincide
# con la suma de los precios cotizados actividad por actividad (son dos salidas
# independientes del flujo). El total del desglose es el que cierra con el costo
# del viaje, así que es el que manda: se reparte entre los días usando los
# precios cotizados como peso. Así cada día y cada tramo suman exactamente el
# total del viaje, y la forma del gasto (qué día pesa más) se conserva.
suma_cotizada = float(df_actividades["precio"].sum())
factor_actividades = (cat_actividades / suma_cotizada) if suma_cotizada else 0.0
df_actividades["asignado"] = df_actividades["precio"] * factor_actividades


# ─── Filtros ─────────────────────────────────────────────────────────────────

col_dest, col_dias, col_modo = st.columns([3, 3, 1.4], vertical_alignment="bottom")

nombres_destinos = [d.get("nombre") for d in destinos if d.get("nombre")]
with col_dest:
    filtro_destino = st.pills(
        t["destinations"], [t["all"]] + nombres_destinos, default=t["all"], key="f_dest"
    ) or t["all"]

with col_dias:
    if len(dias_disponibles) > 1:
        rango = st.slider(
            t["day_range"], min_value=min(dias_disponibles), max_value=max(dias_disponibles),
            value=(min(dias_disponibles), max(dias_disponibles)), key="f_rango",
        )
    else:
        rango = (dias_disponibles[0], dias_disponibles[0])
        st.caption(f"{t['day_range']}: {t['day_short']} {rango[0]}")

with col_modo:
    por_persona = st.toggle(
        t["per_person"], key="f_persona", disabled=cantidad_personas <= 1,
        help=f"{cantidad_personas} {t['people']}",
    )

divisor = cantidad_personas if por_persona else 1

# Filtrar por destino recorta también los días: los costos fijos se prorratean
# sobre los días que se están mirando, no sobre los del viaje entero.
dias_sel = [d for d in dias_disponibles if rango[0] <= d <= rango[1]]
if filtro_destino != t["all"]:
    dias_sel = [d for d in dias_sel if dia_destino.get(d) == filtro_destino]
tramo_completo = len(dias_sel) == len(dias_disponibles) and filtro_destino == t["all"]

# Los costos fijos se prorratean por día: así el "día a día" y cualquier tramo
# muestran lo que cuesta estar ahí, no sólo las actividades sueltas. Sin esto,
# filtrar por un día dejaba el desglose en 100% actividades y no decía nada.
fijos_por_dia = {k: v / dias_totales / divisor for k, v in FIJOS.items()}
fijo_diario = sum(fijos_por_dia.values())

df_f = df_actividades.copy()
if filtro_destino != t["all"]:
    df_f = df_f[df_f["destino"] == filtro_destino]
df_f = df_f[df_f["dia"].isin(dias_sel)].copy()
df_f[["precio", "asignado"]] = df_f[["precio", "asignado"]] / divisor

actividades_tramo = float(df_f["asignado"].sum())
subtotal_tramo = actividades_tramo + fijo_diario * len(dias_sel)


# ─── KPIs ────────────────────────────────────────────────────────────────────

total_mostrado = total_viaje / divisor
k1, k2, k3, k4 = st.columns(4)

k1.metric(
    t["kpi_total"], dinero(total_mostrado),
    delta=viaje.get("tipo_viaje"), delta_color="off",
    help=f"{dias_totales} {t['days_short']}"
         + (f" · {cantidad_personas} pax" if cantidad_personas > 1 else ""),
)
k2.metric(t["kpi_per_day"], dinero(total_mostrado / dias_totales), help=t["per_day_chart"])

if presupuesto_max:
    presupuesto_mostrado = presupuesto_max / divisor
    sobrante = presupuesto_mostrado - total_mostrado
    k3.metric(
        t["kpi_budget"], f"{total_mostrado / presupuesto_mostrado * 100:,.0f}%",
        delta=(f"{dinero(abs(sobrante))} {t['over_budget']}" if sobrante < 0
               else f"{dinero(sobrante)} {t['left']}"),
        delta_color="inverse" if sobrante < 0 else "normal",
        help=f"{dinero(total_mostrado)} {t['of']} {dinero(presupuesto_mostrado)}",
    )
else:
    k3.metric(t["kpi_budget"], "—", delta=t["no_budget"], delta_color="off")

prom_dia_tramo = subtotal_tramo / len(dias_sel) if dias_sel else 0
k4.metric(
    t["kpi_selection"], dinero(subtotal_tramo),
    delta=(f"{len(dias_sel)} {t['days_short']}" if tramo_completo
           else f"{dinero(prom_dia_tramo)} {t['avg_day']}"),
    delta_color="off",
    help=f"{len(dias_sel)} {t['days_short']}",
)

if presupuesto_max:
    st.progress(min(total_mostrado / (presupuesto_max / divisor), 1.0))

st.write("")


# ─── Pestañas ────────────────────────────────────────────────────────────────

tab_resumen, tab_dia, tab_cat, tab_comp, tab_sim = st.tabs([
    t["tab_overview"], t["tab_daily"], t["tab_categories"],
    t["tab_compare"], t["tab_simulator"],
])


# 1) Resumen: el desglose oficial, el que suma el total del viaje.
with tab_resumen:
    etiquetas = [t["lodging"], t["transport"], t["activities"], t["food"]]
    valores = [FIJOS["alojamiento"] / divisor, FIJOS["transporte"] / divisor,
               cat_actividades / divisor, FIJOS["comidas"] / divisor]
    colores = [COLOR["alojamiento"], COLOR["transporte"],
               COLOR["actividades"], COLOR["comidas"]]

    col_g, col_tabla = st.columns([5, 6], vertical_alignment="center")

    with col_g:
        if sum(valores) > 0:
            fig = go.Figure(go.Pie(
                labels=etiquetas, values=valores, hole=0.68, sort=False,
                marker=dict(colors=colores, line=dict(color="white", width=3)),
                textinfo="percent", textfont=dict(size=13, color="white"),
                hovertemplate="<b>%{label}</b><br>$%{value:,.0f} · %{percent}<extra></extra>",
            ))
            fig.add_annotation(
                text=f"<b>{dinero(sum(valores))}</b>", showarrow=False,
                font=dict(size=22, color=GRIS_TEXTO),
            )
            st.plotly_chart(estilo(fig, alto=320), width="stretch",
                            config={"displayModeBar": False})
        else:
            st.caption(t["no_activities"])

    with col_tabla:
        total_cat = sum(valores) or 1
        df_cat = pd.DataFrame({
            t["category"]: etiquetas,
            t["amount"]: valores,
            t["share"]: [v / total_cat * 100 for v in valores],
        })
        st.dataframe(
            df_cat, hide_index=True, width="stretch",
            column_config={
                t["amount"]: st.column_config.NumberColumn(format="$%,.0f"),
                t["share"]: st.column_config.ProgressColumn(
                    format="%.0f%%", min_value=0, max_value=100),
            },
        )


# 2) Día a día: acá el rango de días sí cambia lo que se ve.
with tab_dia:
    if not dias_sel:
        st.caption(t["no_activities"])
    else:
        gasto_dia = (df_f.groupby("dia")["asignado"].sum() if not df_f.empty
                     else pd.Series(dtype=float))
        df_dias = pd.DataFrame({"dia": dias_sel})
        df_dias[t["activities"]] = df_dias["dia"].map(gasto_dia).fillna(0.0)
        for clave, etiqueta in (("alojamiento", t["lodging"]), ("transporte", t["transport"]),
                                ("comidas", t["food"])):
            df_dias[etiqueta] = fijos_por_dia[clave]
        df_dias["etiqueta"] = df_dias["dia"].map(lambda d: f"{t['day_short']} {d}")

        st.caption(t["per_day_chart"])
        fig = go.Figure()
        for etiqueta, clave in ((t["lodging"], "alojamiento"), (t["transport"], "transporte"),
                                (t["food"], "comidas"), (t["activities"], "actividades")):
            fig.add_bar(
                name=etiqueta, x=df_dias["etiqueta"], y=df_dias[etiqueta],
                marker=dict(color=COLOR[clave], line=dict(width=0)),
                hovertemplate="<b>%{x}</b><br>" + etiqueta + ": $%{y:,.0f}<extra></extra>",
            )
        fig.update_layout(barmode="stack", bargap=0.25)
        fig.update_yaxes(tickprefix="$")
        st.plotly_chart(estilo(fig, alto=330), width="stretch", config={"displayModeBar": False})

        # Gráfico nativo de Streamlit (Vega-Lite por debajo): acumulado del tramo.
        df_acum = pd.DataFrame({
            t["day_short"]: df_dias["dia"],
            t["cumulative"]: df_dias[[t["lodging"], t["transport"], t["food"],
                                      t["activities"]]].sum(axis=1).cumsum(),
        }).set_index(t["day_short"])
        st.caption(t["cumulative"])
        st.area_chart(df_acum, color=VERDE, height=220)

        st.divider()

        # Plegado: el dashboard va embebido en una página más larga y esta
        # pestaña es la que más alto ocupa.
        with st.expander(t["day_detail"], icon=":material/event:"):
            dia_elegido = st.selectbox(
                t["pick_day"], dias_sel, format_func=lambda d: f"{t['day_short']} {d}",
                key="f_dia_detalle",
            )
            detalle = df_f[df_f["dia"] == dia_elegido]

            c1, c2, c3 = st.columns(3)
            c1.metric(t["activities"], dinero(detalle["asignado"].sum()))
            c2.metric(t["fixed_costs"], dinero(fijo_diario), help=t["per_day_chart"])
            c3.metric(t["day_total"], dinero(detalle["asignado"].sum() + fijo_diario))

            if detalle.empty:
                st.caption(t["no_activities"])
            else:
                st.dataframe(
                    detalle[["horario", "actividad", "categoria", "lugar", "precio"]].rename(
                        columns={
                            "horario": t["time"], "actividad": t["activity"],
                            "categoria": t["category"], "lugar": t["place"],
                            "precio": t["quoted"],
                        }
                    ),
                    hide_index=True, width="stretch",
                    column_config={t["quoted"]: st.column_config.NumberColumn(format="$%,.0f")},
                )
                st.caption(t["quoted_note"])


# 3) Categorías: sobre las actividades reales, que son las que traen categoría.
with tab_cat:
    if df_f.empty:
        st.caption(t["no_activities"])
    else:
        categorias = sorted(df_f["categoria"].unique().tolist())
        elegidas = st.multiselect(t["filter_categories"], categorias, default=categorias,
                                  key="f_cats")
        df_c = df_f[df_f["categoria"].isin(elegidas)] if elegidas else df_f.iloc[0:0]

        if df_c.empty:
            st.caption(t["no_activities"])
        else:
            resumen = (df_c.groupby("categoria")["asignado"].agg(["sum", "count"])
                       .reset_index().sort_values("sum", ascending=False))
            resumen.columns = ["categoria", "total", "cantidad"]

            col_a, col_b = st.columns([6, 5], vertical_alignment="center")

            with col_a:
                st.caption(t["by_category"])
                # Escala de violetas (el color de "Actividades" en el resto de
                # la página), de más a menos gasto. Todos los tonos son lo
                # bastante oscuros como para que el texto blanco se lea.
                ramp = ["#4c1d95", "#5b21b6", "#6d28d9", "#7c3aed", "#8b5cf6", "#9061f9"]
                fig = go.Figure(go.Treemap(
                    labels=resumen["categoria"], parents=[""] * len(resumen),
                    values=resumen["total"],
                    texttemplate="<b>%{label}</b><br>$%{value:,.0f}",
                    textfont=dict(color="white", size=13),
                    marker=dict(
                        colors=[ramp[i % len(ramp)] for i in range(len(resumen))],
                        line=dict(color="white", width=2),
                    ),
                    hovertemplate="<b>%{label}</b><br>$%{value:,.0f}<extra></extra>",
                ))
                fig.update_traces(root_color="rgba(0,0,0,0)")
                st.plotly_chart(estilo(fig, alto=320, leyenda=False), width="stretch",
                                config={"displayModeBar": False})

            with col_b:
                total_c = resumen["total"].sum() or 1
                tabla = resumen.copy()
                tabla["peso"] = tabla["total"] / total_c * 100
                st.dataframe(
                    tabla.rename(columns={
                        "categoria": t["category"], "total": t["amount"],
                        "cantidad": "N", "peso": t["share"],
                    }),
                    hide_index=True, width="stretch",
                    column_config={
                        t["amount"]: st.column_config.NumberColumn(format="$%,.0f"),
                        t["share"]: st.column_config.ProgressColumn(
                            format="%.0f%%", min_value=0, max_value=100),
                    },
                )

            st.download_button(
                t["download"],
                data=df_c.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"presupuesto_viaje_{id_viaje}.csv",
                mime="text/csv", icon=":material/download:",
            )


# 4) Comparar las tres variantes generadas para el mismo viaje.
with tab_comp:
    variantes = cargar_variantes(viaje.get("group_id"), id_usuario)

    if len(variantes) < 2:
        st.info(t["compare_none"], icon=":material/info:")
    else:
        st.caption(t["compare_intro"])
        orden = {"Economy": 0, "Balanced": 1, "Luxury": 2}
        variantes.sort(key=lambda v: orden.get(v.get("tipo_viaje"), 9))

        cols = st.columns(len(variantes))
        for col, v in zip(cols, variantes):
            c = v.get("costos") or {}
            total_v = ((c.get("costo_total_ajustado") or v.get("costo_total_estimado") or 0)
                       / divisor)
            es_actual = str(v.get("id_viaje")) == str(id_viaje)
            delta, color = None, "off"
            if presupuesto_max:
                dif = (presupuesto_max / divisor) - total_v
                delta = (f"{dinero(abs(dif))} {t['over_budget']}" if dif < 0
                         else f"{dinero(dif)} {t['left']}")
                color = "inverse" if dif < 0 else "normal"
            col.metric(
                (v.get("tipo_viaje") or "") + ("  ←" if es_actual else ""),
                dinero(total_v), delta=delta, delta_color=color,
            )

        claves = (
            (t["lodging"], "costo_alojamiento", "alojamiento"),
            (t["transport"], "costo_transporte", "transporte"),
            (t["activities"], "costo_actividades", "actividades"),
            (t["food"], "costo_comidas", "comidas"),
        )
        fig = go.Figure()
        for etiqueta, clave_costo, clave_color in claves:
            fig.add_bar(
                name=etiqueta,
                x=[v.get("tipo_viaje") for v in variantes],
                y=[((v.get("costos") or {}).get(clave_costo) or 0) / divisor
                   for v in variantes],
                marker=dict(color=COLOR[clave_color], line=dict(width=0)),
                hovertemplate="<b>%{x}</b><br>" + etiqueta + ": $%{y:,.0f}<extra></extra>",
            )
        fig.update_layout(barmode="stack", bargap=0.45)
        fig.update_yaxes(tickprefix="$")
        if presupuesto_max:
            fig.add_hline(
                y=presupuesto_max / divisor, line_dash="dash", line_color="#dc2626",
                annotation_text=t["budget_line"], annotation_position="top left",
                annotation_font_color="#dc2626",
            )
        st.plotly_chart(estilo(fig, alto=340), width="stretch",
                        config={"displayModeBar": False})


# 5) Simulador: mover los costos y ver el impacto, sin tocar la base.
with tab_sim:
    st.caption(t["sim_intro"])

    originales = pd.DataFrame({
        t["category"]: [t["lodging"], t["transport"], t["activities"], t["food"]],
        t["amount"]: [FIJOS["alojamiento"] / divisor, FIJOS["transporte"] / divisor,
                      cat_actividades / divisor, FIJOS["comidas"] / divisor],
    })

    if st.button(t["sim_reset"], icon=":material/restart_alt:"):
        st.session_state.pop("editor_sim", None)

    editado = st.data_editor(
        originales, hide_index=True, width="stretch", key="editor_sim",
        disabled=[t["category"]],
        column_config={
            t["amount"]: st.column_config.NumberColumn(format="$%,.0f", min_value=0, step=50),
        },
    )

    total_sim = float(editado[t["amount"]].sum())
    total_orig = float(originales[t["amount"]].sum())

    s1, s2, s3 = st.columns(3)
    diferencia = total_sim - total_orig
    s1.metric(
        t["sim_total"], dinero(total_sim),
        # Sin cambios no hay delta: un "$0" en rojo se lee como si algo pasara.
        delta=(f"{dinero(diferencia)} {t['sim_vs']}" if round(diferencia) else None),
        delta_color="inverse",
    )
    s2.metric(t["kpi_per_day"], dinero(total_sim / dias_totales))
    if presupuesto_max:
        presu = presupuesto_max / divisor
        dif = presu - total_sim
        s3.metric(
            t["kpi_budget"], f"{total_sim / presu * 100:,.0f}%",
            delta=(f"{dinero(abs(dif))} {t['over_budget']}" if dif < 0
                   else f"{dinero(dif)} {t['left']}"),
            delta_color="inverse" if dif < 0 else "normal",
        )
        st.progress(min(total_sim / presu, 1.0))

    fig = go.Figure()
    fig.add_bar(name="Original", x=originales[t["category"]], y=originales[t["amount"]],
                marker_color=GRIS_SUAVE,
                hovertemplate="Original: $%{y:,.0f}<extra></extra>")
    fig.add_bar(name=t["simulated"], x=editado[t["category"]], y=editado[t["amount"]],
                marker_color=VERDE,
                hovertemplate=t["simulated"] + ": $%{y:,.0f}<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.3)
    fig.update_yaxes(tickprefix="$")
    st.plotly_chart(estilo(fig, alto=300), width="stretch", config={"displayModeBar": False})


# ─── Análisis automático ─────────────────────────────────────────────────────
# Determinístico, sobre los datos ya cargados. El proyecto usa n8n para generar
# los itinerarios (ver FRONTEND/trip_generator.py); no hay un flujo de n8n para
# analizar presupuestos, así que esto no llama a ninguna IA.

frases = []

if presupuesto_max:
    uso = total_viaje / presupuesto_max
    if uso > 1:
        frases.append(
            f"Este plan **{viaje.get('tipo_viaje')}** se pasa del presupuesto en "
            f"**{dinero_md(total_viaje - presupuesto_max)}** ({uso * 100:.0f}% del máximo). "
            f"Que la variante más cara lo exceda es esperado: para eso están las tres opciones."
            if es else
            f"This **{viaje.get('tipo_viaje')}** plan goes over budget by "
            f"**{dinero_md(total_viaje - presupuesto_max)}** ({uso * 100:.0f}% of the max). "
            f"The priciest variant going over is expected: that's why there are three options."
        )
    else:
        frases.append(
            f"Entra en el presupuesto y sobran **{dinero_md(presupuesto_max - total_viaje)}** "
            f"({uso * 100:.0f}% usado)."
            if es else
            f"It fits the budget with **{dinero_md(presupuesto_max - total_viaje)}** to spare "
            f"({uso * 100:.0f}% used)."
        )

if any(FIJOS.values()) and total_viaje:
    clave_mayor, monto_mayor = max(FIJOS.items(), key=lambda kv: kv[1])
    nombre_cat = {"alojamiento": t["lodging"], "transporte": t["transport"],
                  "comidas": t["food"]}[clave_mayor]
    frases.append(
        f"**{nombre_cat}** es el rubro más pesado: {dinero_md(monto_mayor)}, un "
        f"{monto_mayor / total_viaje * 100:.0f}% del viaje."
        if es else
        f"**{nombre_cat}** is the heaviest line: {dinero_md(monto_mayor)}, "
        f"{monto_mayor / total_viaje * 100:.0f}% of the trip."
    )

if not df_f.empty:
    por_dia_serie = df_f.groupby("dia")["asignado"].sum()
    if len(por_dia_serie) > 1 and por_dia_serie.max() > 0:
        frases.append(
            f"En actividades, el **{t['day_short'].lower()} {por_dia_serie.idxmax()}** es el "
            f"más cargado ({dinero_md(por_dia_serie.max())}), contra un promedio de "
            f"{dinero_md(por_dia_serie.mean())}."
            if es else
            f"On activities, **{t['day_short'].lower()} {por_dia_serie.idxmax()}** is the "
            f"busiest ({dinero_md(por_dia_serie.max())}), against a "
            f"{dinero_md(por_dia_serie.mean())} average."
        )

if cantidad_personas > 1 and not por_persona:
    frases.append(
        f"Dividido entre {cantidad_personas} personas, son "
        f"{dinero_md(total_viaje / cantidad_personas)} por cabeza."
        if es else
        f"Split across {cantidad_personas} people, that's "
        f"{dinero_md(total_viaje / cantidad_personas)} each."
    )

if frases:
    st.write("")
    with st.container(border=True):
        st.markdown(f"**{t['insight_title']}**")
        for frase in frases:
            st.markdown(f"- {frase}")
