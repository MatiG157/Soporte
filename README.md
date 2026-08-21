# TravelPlanner

Planificador de viajes con IA. El usuario carga origen, destinos, fechas,
presupuesto y preferencias; el sistema genera **tres variantes del viaje**
(Economy, Balanced y Luxury) con itinerario día por día, calcula el costo con
una regla de negocio y deja que el usuario elija una para guardarla.

## Arquitectura en capas

| Capa | Dónde vive | Qué hace |
|---|---|---|
| **Presentación** | `FRONTEND/` — Flask + Jinja2 + Bootstrap | Renderiza las vistas. No habla con la base ni con la IA: todo pasa por el backend o por el generador. |
| **Negocio** | `BACKEND/src/services/` | Regla de cálculo de costos, ajuste por tipo de viaje, reoptimización por presupuesto, ciclo de vida de los borradores. |
| **Datos** | `BACKEND/src/models/` — SQLAlchemy + MySQL | Entidades y relaciones. |
| **Integración** | `FRONTEND/trip_generator.py` | Pide las variantes al flujo de n8n. `BACKEND/src/services/ai_recommendation_service.py` guarda lo que n8n devolvió. |

```
Navegador ──► FRONTEND (:8080) ──X-API-KEY──► BACKEND (:5000) ──► MySQL
                   │
                   └──► n8n  (generación de itinerarios)
```

El backend nunca se expone al navegador: sólo el frontend lo llama, autenticado
con una API key compartida (`X-API-KEY`) más el id del usuario de la sesión
(`X-User-Id`), que el backend usa para verificar propiedad de cada recurso.

---

## Puesta en marcha

### 1. Requisitos

- Python 3.11+
- MySQL 8 con una base ya creada (por defecto `travelplannerbd`)

```sql
CREATE DATABASE travelplannerbd CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. Entorno virtual y dependencias

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r BACKEND/requirements.txt
pip install -r FRONTEND/requirements.txt
```

### 3. Variables de entorno

```bash
cp BACKEND/.env.example  BACKEND/.env
cp FRONTEND/.env.example FRONTEND/.env
```

Generá **una** clave y poné el mismo valor en los dos archivos:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

- `BACKEND/.env` → `API_KEY=<esa clave>`
- `FRONTEND/.env` → `BACKEND_API_KEY=<la misma clave>`

Además, en `FRONTEND/.env` poné un `SECRET_KEY` propio (otra clave aleatoria).
Si falta, las sesiones se invalidan en cada reinicio.

### 4. Base de datos

```bash
cd BACKEND
python migrate.py            # crea/actualiza el esquema (idempotente)
python migrate.py --status   # ver qué migraciones están aplicadas
python seed_dev.py           # datos de prueba (opcional)
python seed_dev.py --con-drafts   # + 3 borradores para probar /compare
```

Usuarios sembrados: `ana.gomez.dev@example.com`, `lucas.perez.dev@example.com`,
`marta.lopez.dev@example.com` — contraseña `DevPass123`.

### 5. Levantar

En Windows, desde la raíz: `run.bat`

O a mano, en dos terminales:

```bash
cd BACKEND  && python app.py    # http://localhost:5000
cd FRONTEND && python app.py    # http://localhost:8080
```

---

## Generación de viajes

`POST /create_trip` guarda las preferencias y le pide las tres variantes al
**flujo de n8n**, que es el único proveedor de IA del sistema. El contrato de
entrada y salida está documentado en [PROMPT_N8N.md](PROMPT_N8N.md).

Si n8n no responde —no está configurado, se cayó, o devolvió algo que no cumple
el contrato— se usa un **generador local** determinístico, sin IA, que respeta
la cantidad real de días, el presupuesto y las actividades preferidas. No
reemplaza a n8n: existe para que la web funcione en la defensa aunque no haya red.

Los dos devuelven el mismo JSON, que se valida y se recorta a los límites de las
columnas antes de persistirlo. El backend nunca llama a una IA: sólo guarda lo
que recibe, incluida la salida cruda en `recomendaciones_ia` para trazabilidad.

### Regla de negocio de costos

`costo_total_base = alojamiento + transporte + actividades + comidas`

`costo_total_estimado = costo_total_base × multiplicador(tipo_viaje)`
donde el multiplicador es `0.90` para Economy, `1.10` para Balanced y `1.25`
para Luxury.

Si el total supera el `costo_max` de las preferencias, `reoptimizar_por_presupuesto()`
recorta primero lo discrecional (actividades y comidas, hasta un 40 %) y recién
después escala el resto de forma proporcional.

---

## Endpoints del backend

Todos exigen `X-API-KEY`. Los marcados con 👤 exigen además `X-User-Id` y
verifican que el recurso pertenezca a ese usuario.

| Método | Ruta | |
|---|---|---|
| `GET` | `/health` | Estado del servicio y de la base |
| `POST` | `/usuarios/` | Alta de usuario |
| `POST` | `/usuarios/login` | Login |
| `POST` | `/usuarios/google-login` | Login con Google |
| `GET/PUT/DELETE` | `/usuarios/<id>` | 👤 Perfil |
| `GET/POST/PUT/DELETE` | `/preferencias/...` | 👤 Preferencias |
| `POST` | `/viajes/generate` | 👤 Guarda las N variantes como borradores |
| `GET` | `/viajes/usuario/<id>` | 👤 Viajes del usuario |
| `GET` | `/viajes/usuario/<id>/drafts` | 👤 Borradores activos |
| `GET/PATCH/DELETE` | `/viajes/<id>` | 👤 Detalle, edición y baja |
| `POST` | `/viajes/<id>/select` | 👤 Confirma un borrador y descarta el resto |
| `GET/POST` | `/costos/...` | 👤 Desglose de costos |
| `GET/POST/PUT/DELETE` | `/itinerarios/...` | 👤 Itinerarios |
| `GET/POST/PUT/DELETE` | `/actividades/...` | 👤 Actividades |
| `GET` | `/tipos_alojamiento/` | Catálogo (escritura: requiere `X-ADMIN-KEY`) |
| `GET` | `/api/recommendations/viaje/<id>` | 👤 Salida cruda de n8n, guardada por viaje |

---

## Tests

```bash
cd BACKEND
python -m pytest -v
```

Los tests usan SQLite en memoria: no tocan la base de MySQL.

---

## Estructura

```
BACKEND/
  app.py                  fábrica de la app y registro de blueprints
  migrate.py              migraciones idempotentes
  seed_dev.py             datos de desarrollo
  src/
    auth.py               API key + verificación de propiedad
    models/               entidades SQLAlchemy
    routes/               capa HTTP
    services/             reglas de negocio
    validators/           esquemas Marshmallow
  tests/

FRONTEND/
  app.py                  vistas
  api_client.py           cliente HTTP del backend
  security.py             protección CSRF
  trip_generator.py       cliente de n8n + generador local de respaldo
  templates/
  static/
    i18n/<lang>.json      traducciones (9 idiomas)
```

## Idiomas

La interfaz está traducida a inglés, español, portugués, francés, italiano,
alemán, ruso, chino y japonés. Los diccionarios viven en
`FRONTEND/static/i18n/`. El idioma elegido se guarda en el perfil del usuario
(columna `usuarios.idioma`) y, si no hay sesión, en `localStorage`.

Para agregar una clave nueva: agregala en los nueve JSON y usá
`data-i18n="clave"` en el HTML (o `data-i18n-placeholder` / `data-i18n-title`).
Desde JavaScript, `t('clave')`.
