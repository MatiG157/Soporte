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

Los `.env` **no están en el repo** (llevan claves), así que después de un clone
o un pull hay que generarlos. Desde la raíz:

```bash
python setup.py
```

Eso crea `BACKEND/.env` y `FRONTEND/.env` a partir de los `.env.example`, genera
las claves y —lo importante— **deja la misma en los dos lados**: `API_KEY` en el
backend y `BACKEND_API_KEY` en el frontend tienen que coincidir o el backend
rechaza todo con 401 y no se puede ni registrar ni loguear.

Es idempotente: no pisa lo que ya esté configurado.

```bash
python setup.py --check    # sólo revisa y reporta qué falta
python setup.py --rotar    # claves nuevas (cierra las sesiones abiertas)
```

Lo único que queda a mano es la conexión a MySQL en `BACKEND/.env`:
`DB_USER`, `DB_PASSWORD`, `DB_NAME`. El script avisa si siguen en el placeholder.

### 4. Base de datos

**El backend aplica las migraciones pendientes al arrancar**, así que en general
no hay que hacer nada. Igual se puede correr a mano:

```bash
cd BACKEND
python migrate.py            # aplica lo pendiente (idempotente)
python migrate.py --status   # ver qué está aplicado y qué no
python seed_dev.py           # datos de prueba (opcional)
python seed_dev.py --con-drafts   # + 3 borradores para probar /compare
```

Usuarios sembrados: `ana.gomez.dev@example.com`, `lucas.perez.dev@example.com`,
`marta.lopez.dev@example.com` — contraseña `DevPass123`.

Para desactivar la migración automática: `AUTO_MIGRATE=false` en `BACKEND/.env`.

### 5. Levantar

En Windows, desde la raíz: `run.bat` (corre `setup.py` y levanta los dos servidores).

O a mano, en dos terminales:

```bash
cd BACKEND  && python app.py    # http://localhost:5000
cd FRONTEND && python app.py    # http://localhost:8080
```

---

## Problemas frecuentes

**`Unknown column 'usuarios.idioma'`**
La base quedó con el esquema viejo. Reiniciá el backend (migra al arrancar) o
corré `cd BACKEND && python migrate.py`.

**No puedo registrarme ni loguearme / todo devuelve 401**
`API_KEY` y `BACKEND_API_KEY` no coinciden, o falta algún `.env`. Corré
`python setup.py` desde la raíz y reiniciá los dos servidores. Con
`python setup.py --check` lo verificás sin escribir nada.

**`El backend no tiene API_KEY configurada`**
Falta `BACKEND/.env`. Mismo remedio: `python setup.py`.

**El backend arranca pero `/health` devuelve 503**
MySQL no está levantado, o las credenciales de `BACKEND/.env` están mal.

**n8n responde `403 Authorization data is wrong!`**
n8n usa ese mismo texto para Basic Auth y para Header Auth. Corré
`python probar_n8n.py`: mira el header `WWW-Authenticate` de la respuesta y te
dice cuál de las dos espera tu webhook. Si es Header Auth y el nombre no
coincide, `--descubrir-header` prueba los habituales.

Ojo: un 403 **prueba que llegás al VPS** — el mensaje lo genera n8n. Si no
llegaras, verías un error de DNS, de conexión o un timeout.

**Los viajes salen siempre iguales / genéricos**
n8n no está respondiendo y se está usando el generador local. Corré
`cd FRONTEND && python probar_n8n.py` para ver por qué.

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

### Conectar n8n

n8n puede estar en un VPS mientras la web corre en tu máquina: la llamada es
**saliente** (Flask → webhook) y sincrónica, así que no hace falta hostear la web
ni abrir puertos.

En `FRONTEND/.env`:

```
N8N_WEBHOOK_URL=https://n8n.tu-vps.com/webhook/generate-trips
N8N_TIMEOUT=120
```

La autenticación depende de cómo esté el nodo Webhook en n8n. Las dos formas
están soportadas:

**Basic Auth** (`Authentication` → `Basic Auth`):

```
N8N_BASIC_USER=usuario
N8N_BASIC_PASSWORD=contraseña
```

**Header Auth** (`Authentication` → `Header Auth`):

```
N8N_TOKEN=el-token-que-inventes
N8N_HEADER=X-N8N-TOKEN
```

En Header Auth, `N8N_HEADER` tiene que ser idéntico al campo `Name` de la
credencial, y `N8N_TOKEN` al campo `Value`. El token no se saca de n8n: es un
secreto que inventás vos y ponés en los dos lados.

Si no sabés cuál tenés configurada, `python probar_n8n.py` te lo dice.

Del lado de n8n, tres cosas que suelen fallar:

1. Usar la URL de **producción** (`/webhook/...`), no la de test
   (`/webhook-test/...` sólo responde con el editor escuchando).
2. El workflow tiene que estar en **Active**.
3. En el nodo Webhook, `Respond` = **"Using Respond to Webhook node"**. Con el
   valor por defecto n8n contesta al instante `{"message": "Workflow was started"}`
   sin esperar al modelo, y la web descarta esa respuesta.

Para verificar la conexión sin levantar la web:

```bash
cd FRONTEND
python probar_n8n.py                 # manda un payload real y valida la respuesta
python probar_n8n.py --dias 8        # probar otra duración
python probar_n8n.py --json          # ver la respuesta cruda del flujo
python probar_n8n.py --descubrir-header   # qué header espera tu n8n
```

Valida con la misma función que usa la aplicación: si pasa ahí, pasa en la web.

### Regla de negocio de costos

`costo_total_base = alojamiento + transporte + actividades + comidas`

Qué pasa después depende de **de dónde salió el costo**:

**Si el generador manda `desglose_costos`** (el flujo de n8n cotiza vuelo y
alojamiento contra APIs reales y ya diferencia los tres niveles), ese número se
respeta tal cual. No se le aplica el multiplicador ni la reoptimización:
volver a aplicar el premium del nivel lo contaría dos veces, y recortar la
variante Luxury la dejaría con precio de presupuesto medio y contenido de cinco
estrellas. **Que Luxury exceda el presupuesto es intencional** — para eso están
las tres opciones.

**Si no manda desglose**, el costo es una estimación: se reparte por categoría
(35 % alojamiento / 30 % transporte / 20 % actividades / 15 % comidas) y ahí sí
corren las dos reglas:

- `costo_total_estimado = costo_total_base × multiplicador(tipo_viaje)`,
  con `0.90` para Economy, `1.10` para Balanced y `1.25` para Luxury.
- Si el total supera el `costo_max`, `reoptimizar_por_presupuesto()` recorta
  primero lo discrecional (actividades y comidas, hasta un 40 %) y recién
  después escala el resto proporcionalmente.

El ajuste se decide **al guardar**, no al leer: `GET /costos/viajes/<id>` informa
lo que quedó persistido. Pasarle `?tipo_viaje=X` recalcula a propósito, para
simular cuánto costaría el mismo viaje en otro nivel.

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
cd BACKEND  && python -m pytest    # 63 tests
cd FRONTEND && python -m pytest    # 51 tests
```

El backend corre sobre SQLite en memoria y el frontend con el backend simulado:
ninguno toca MySQL ni la red.

---

## Estructura

```
setup.py                  genera y sincroniza los .env (correr tras cada pull)

BACKEND/
  app.py                  fábrica de la app; migra la base al arrancar
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
  probar_n8n.py           prueba la conexión con el flujo y diagnostica fallos
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
