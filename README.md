# Runia

API con bot de Telegram que arma planes semanales de entrenamiento para running según el nivel y los objetivos
del corredor. El plan lo propone Gemini (`gemini-3.5-flash-lite`) y, antes de guardarse, pasa siempre por
guardarraíles deterministas de carga. Cada día con sesión, el bot pregunta la fatiga, evalúa el clima con
OpenWeatherMap y envía la sesión del día por Telegram.

- Requerimientos del producto: [`PRD.md`](PRD.md)
- Especificación, plan y contratos: [`specs/001-runia-training-plans/`](specs/001-runia-training-plans/)
- Guía de validación end-to-end: [`quickstart.md`](specs/001-runia-training-plans/quickstart.md)

## Stack

Python 3.12 con [uv](https://docs.astral.sh/uv/), FastAPI + uvicorn, SQLite (`sqlite3` de la stdlib),
SDK `google-genai`, `python-telegram-bot` (polling, en el mismo proceso que la API), Argon2 + JWT y pytest.

## Instalación y tests

Solo hace falta tener `uv` instalado. uv descarga Python 3.12 a partir de `.python-version`.

```bash
uv sync
uv run pytest
```

Los tests no necesitan claves ni red: la IA, el clima, Telegram y el reloj se reemplazan por dobles de prueba.

## Configuración

Copiá el ejemplo y completá los valores. El archivo `.env` no se commitea.

```bash
cp .env.example .env
```

| Variable | Obligatoria | De dónde sale |
|---|---|---|
| `JWT_SECRET` | Sí | Cualquier texto largo y aleatorio, por ejemplo `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `GOOGLE_API_KEY` | Sí | Clave de la API de Gemini, en [Google AI Studio](https://aistudio.google.com/apikey) |
| `OPENWEATHER_API_KEY` | Sí | Clave gratuita de [OpenWeatherMap](https://openweathermap.org/api). Una clave nueva puede tardar un rato en activarse |
| `TELEGRAM_BOT_TOKEN` | Para el bot | Token de un bot propio, creado con [@BotFather](https://t.me/BotFather) |
| `RUNIA_DB_PATH` | No | Ruta del archivo SQLite. Por defecto, `runia.db` |

Cada persona que corra la app necesita su propio bot: si dos procesos usan el mismo token a la vez,
Telegram rechaza a uno de los dos.

## Levantar la app

```bash
uv run --env-file .env uvicorn app.main:app --reload
```

La app no lee el `.env` sola: por eso va `--env-file`. Sin `TELEGRAM_BOT_TOKEN` arranca solo la API, sin el bot
ni el scheduler. La documentación interactiva queda en <http://localhost:8000/docs>; en los endpoints
autenticados, el header `authorization` se completa con `Bearer <access_token>`.

El mensaje diario y la generación automática de los lunes dependen del scheduler, que corre dentro del mismo
proceso: solo funcionan mientras la app está levantada con el bot.

## Uso

### API

| Endpoint | Para qué |
|---|---|
| `POST /auth/register`, `POST /auth/login` | Crear la cuenta e iniciar sesión (devuelve el JWT) |
| `GET` / `PUT /profile` | Ver y cargar el perfil: nivel, frecuencia, distancia objetivo, ritmo, ciudad, rango horario y hora de envío |
| `POST /telegram/link-code` | Generar el código para vincular el chat de Telegram |
| `POST /plan` | Generar el plan de la semana en curso |
| `GET /schedule`, `GET /history` | Ver el cronograma de la semana y el historial |
| `POST /sessions/{id}/result` | Registrar el resultado de la sesión del día |
| `POST /auth/password-reset` | Cambiar la contraseña con un código pedido desde el bot |
| `DELETE /profile?confirm=true` | Borrar la cuenta y todos sus datos |

El detalle de cada endpoint, con los códigos de respuesta, está en
[`contracts/api.md`](specs/001-runia-training-plans/contracts/api.md).

### Bot de Telegram

| Comando | Para qué |
|---|---|
| `/vincular <código>` | Vincular el chat con la cuenta (código de `POST /telegram/link-code`) |
| `/registrar <completada\|parcial\|salteada> [rpe] [notas]` | Registrar la sesión de hoy |
| `/restablecer` | Pedir un código para `POST /auth/password-reset` |

A la hora de envío configurada, el bot pregunta la fatiga del 1 al 10; con la respuesta, envía la sesión del día.

### Flujo mínimo

1. Registrarse, iniciar sesión y cargar el perfil completo con `PUT /profile`.
2. Pedir un código con `POST /telegram/link-code` y enviarle `/vincular <código>` al bot.
3. Pedir el plan con `POST /plan`.

El recorrido completo, con los resultados esperados en cada paso, está en el
[quickstart](specs/001-runia-training-plans/quickstart.md).

## Estructura

```text
app/
├── api/           # Endpoints REST
├── bot/           # Handlers de Telegram
├── services/      # Orquestación, persistencia (repository.py) y flujos diario y semanal
├── domain/        # Reglas deterministas puras: guardarraíles, clima, mensaje diario
├── ai/            # Único módulo que usa google-genai: prompts y llamadas a Gemini
├── integrations/  # Cliente de OpenWeatherMap
├── main.py        # App FastAPI: arranca API, bot y scheduler
└── scheduler.py   # Tick cada 60 s: generación de los lunes y mensaje diario
tests/
├── unit/          # Reglas puras, auditoría y principios de la constitución
├── integration/   # Servicios con SQLite y dobles de prueba
└── contract/      # Forma de las respuestas de la API
```
