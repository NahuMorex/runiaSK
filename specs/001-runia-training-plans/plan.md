# Implementation Plan: Runia — Planes de entrenamiento para running

**Branch**: `master` (sin rama dedicada) | **Date**: 2026-10-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-runia-training-plans/spec.md` (fuente: `PRD.md`, PRD-001)

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Runia es una API FastAPI con un bot de Telegram en el mismo proceso. El usuario se registra, carga
su perfil de corredor y vincula su chat de Telegram. Con eso obtiene un plan semanal: lo pide por `POST /plan`
o el sistema lo genera solo los lunes. El plan lo propone Gemini (`gemini-3.5-flash-lite`, SDK `google-genai`) con salida
JSON estructurada. Antes de guardarlo y entregarlo pasa siempre por un pipeline determinista de guardarraíles de carga
escrito en Python puro: validación estructural, reclasificación pendiente, calidad, ritmo, topes por sesión, topes semanales y pisos.

Cada día con sesión, un *tick* del scheduler (una tarea asyncio que corre cada 60 s) evalúa el clima con
OpenWeatherMap a la hora de envío del usuario. Según el resultado alerta, sugiere un día alternativo o pospone
la sesión, y luego pregunta la fatiga por Telegram. Con la respuesta, o pasadas 2 horas sin ella, arma el mensaje
diario: Gemini lo redacta con un límite de 5 s, el código lo valida (AC-78) y, si algo falla, usa una plantilla.
El usuario registra el resultado desde el bot (`/registrar`). Ese comando usa el mismo servicio que el endpoint
`POST /sessions/{id}/result`. Un registro Parcial/Cortada con RPE ≥ 7 reclasifica las 2 sesiones siguientes.

Toda la IA vive en `app/ai/`. Es el único módulo que importa `google-genai`, y no accede a la base ni a Telegram.
El resto del sistema lo consume por funciones tipadas y en los tests lo reemplaza un doble.

## Technical Context

**Language/Version**: Python 3.12 (fijado con uv; no el 3.14 del sistema)

**Primary Dependencies**: FastAPI, uvicorn, `google-genai`, `python-telegram-bot` (polling), `argon2-cffi`,
PyJWT, httpx (cliente de OpenWeatherMap), `email-validator` (para `EmailStr` de pydantic), `tzdata`.
Detalle y justificación en [research.md](./research.md) R-01.

**Storage**: SQLite con `sqlite3` de la stdlib (archivo `runia.db`, ruta configurable con `RUNIA_DB_PATH`; en los tests, `:memory:` o un archivo temporal).
Las distancias se guardan como enteros en centésimas de km (ver [data-model.md](./data-model.md)).

**Testing**: pytest con el plugin de anyio para tests async (viene con FastAPI) y `fastapi.testclient.TestClient`.
Los dobles de prueba reemplazan IA, clima, Telegram y reloj.

**Target Platform**: servidor Linux, un solo proceso (uvicorn) que corre la API, el bot (polling) y el scheduler.

**Project Type**: web-service (API REST + bot de Telegram) en un único paquete Python `app/`.

**Performance Goals**: p95 ≤ 10 s con 10 usuarios simultáneos, medido desde la respuesta de fatiga hasta que
Telegram confirma la entrega del mensaje diario (RNF-01, SC-004). Para lograrlo, Gemini tiene un timeout de 5 s y,
si no responde, se usa la plantilla al instante; el clima no se vuelve a consultar porque ya se evaluó a la hora de envío.

**Constraints**: generación del plan con timeout de 20 s (AC-16, AC-17); redacción del mensaje con timeout de 5 s (AC-79);
espera de la fatiga de hasta 2 h (AC-47); código de vinculación válido por 15 min y código de restablecimiento por 30 min;
JWT de 2 h renovable hasta 7 días desde el login; Argon2id con m=19456, t=2, p=1; todo horario en `America/Argentina/Buenos_Aires`;
logs JSON sin secretos.

**Scale/Scope**: decenas de usuarios (el objetivo de rendimiento se mide con 10 simultáneos), 8 historias de usuario,
46 requerimientos funcionales, alrededor de 10 endpoints y 5 comandos del bot.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Evaluación inicial (antes de Phase 0)**: PASA.

- [x] **I. Lógica de IA aislada**: `app/ai/` es el único lugar donde se importa `google-genai` y se arman los prompts.
  Expone `propose_week_plan(PlanRequest) -> WeekPlanProposal` y `draft_daily_message(DailyMessageData) -> str`,
  ambas con modelos pydantic (ver [contracts/ai-module.md](./contracts/ai-module.md)). No accede a SQLite ni a Telegram:
  recibe datos ya armados y devuelve una propuesta. Los guardarraíles (`app/domain/guardrails.py`), las reglas de clima,
  la validación de perfil y la validación del mensaje son código determinista fuera de `app/ai/`.
- [x] **II. Sin secretos en el código**: `app/config.py` lee `GOOGLE_API_KEY`, `TELEGRAM_BOT_TOKEN`,
  `OPENWEATHER_API_KEY` y `JWT_SECRET` del entorno, sin valores por defecto. Cada componente que necesita
  una credencial falla con un error explícito si falta. La única excepción es `TELEGRAM_BOT_TOKEN`: si falta,
  la API arranca sin el bot ni el scheduler, como indica AGENTS.md. `.env` ya está en `.gitignore`.
  El logger de auditoría descarta las claves sensibles (`password`, `token`, `api_key`, `authorization`, `code`).
  Los tests usan valores falsos que se inyectan con monkeypatch, nunca credenciales reales.
- [x] **III. Alcance limitado al PRD vigente**: cada módulo, endpoint y comando del bot traza a un RF/RNF/AC
  (tabla de trazabilidad en [contracts/api.md](./contracts/api.md) y [contracts/telegram-bot.md](./contracts/telegram-bot.md)).
  Quedan fuera RF-20/AC-54 y AC-25/AC-26, como acordó la spec. No se implementa nada de "Fuera de Alcance"
  y no se crea `kb.md` (research R-14).

**Re-evaluación post-diseño (después de Phase 1)**: PASA, con la excepción del Principio II registrada en Complexity Tracking. El diseño de datos y contratos no agrega
endpoints ni comandos sin RF. El scheduler es una tarea asyncio propia y no suma dependencias.
`/registrar` usa el mismo servicio que `POST /sessions/{id}/result` (R-08) y no duplica reglas.
Las dependencias nuevas (httpx, email-validator, tzdata) trazan a RF-05, RF-01 y RF-03f respectivamente.

## Project Structure

### Documentation (this feature)

```text
specs/001-runia-training-plans/
├── plan.md              # Este archivo
├── research.md          # Phase 0: decisiones técnicas y de interpretación
├── data-model.md        # Phase 1: tablas SQLite, entidades, estados
├── quickstart.md        # Phase 1: guía de validación end-to-end
├── contracts/
│   ├── api.md           # Endpoints REST, esquemas, códigos HTTP, trazabilidad
│   ├── telegram-bot.md  # Comandos del bot, mensajes fijos, flujo de fatiga
│   └── ai-module.md     # Interfaz tipada del módulo de IA y esquema de la propuesta
├── checklists/          # Ya existentes (requirements.md, guardrails.md)
└── tasks.md             # Phase 2 (/speckit-tasks; no lo crea /speckit-plan)
```

### Source Code (repository root)

```text
pyproject.toml                 # uv; requires-python ==3.12.*; deps de R-01
.python-version                # 3.12
app/
├── __init__.py
├── main.py                    # FastAPI app + lifespan (init DB, bot, scheduler)
├── config.py                  # Lectura de variables de entorno; errores explícitos
├── clock.py                   # Clock inyectable (now en America/Argentina/Buenos_Aires)
├── db.py                      # Conexión sqlite3, PRAGMAs, schema (CREATE TABLE IF NOT EXISTS)
├── audit.py                   # Logger JSON estructurado + redacción de claves sensibles (FR-045)
├── security.py                # Argon2id, JWT (emisión, renovación, auth_time), códigos de un solo uso
├── deps.py                    # Dependencias FastAPI: conexión, usuario actual, servicios inyectables
├── api/
│   ├── __init__.py
│   ├── auth.py                # POST /auth/register, /auth/login, /auth/password-reset
│   ├── profile.py             # GET/PUT/DELETE /profile
│   ├── telegram_link.py       # POST /telegram/link-code
│   ├── plan.py                # POST /plan, GET /schedule
│   └── sessions.py            # POST /sessions/{id}/result, GET /history
├── domain/
│   ├── __init__.py
│   ├── models.py              # Dataclasses/pydantic de dominio: Block, Session, Plan, WeekSummary, …
│   ├── units.py               # km↔centésimas, mm:ss↔segundos, redondeos (floor 0,01 km, ritmo)
│   ├── profile_rules.py       # Validación de perfil y completitud (FR-005, FR-006, FR-012)
│   ├── weeks.py               # Semana lunes-domingo, semana cerrada, días restantes (FR-016)
│   ├── summaries.py           # Resúmenes semanales, racha, base de topes, elegibilidad de calidad
│   ├── structure.py           # Validación estructural de la propuesta (FR-027, R-05)
│   ├── guardrails.py          # Pipeline determinista FR-018..FR-026, FR-042 pendiente
│   ├── weather_rules.py       # Desfavorable/extremo, alternativa, posposición (FR-034..FR-039)
│   ├── daily_message.py       # Datos del mensaje, ajuste por fatiga, plantilla, validación AC-78
│   └── reclassification.py    # FR-042: reclasificación inmediata y pendiente
├── services/
│   ├── __init__.py
│   ├── repository.py          # Todo el SQL (usuarios, perfiles, planes, sesiones, códigos, dispatch)
│   ├── accounts.py            # Registro, login, reset, borrado
│   ├── linking.py             # Códigos de vinculación y vínculo de chat (FR-011)
│   ├── plan_service.py        # Orquesta: precondiciones → IA → estructura → guardarraíles → persistencia
│   ├── results.py             # Registro de resultados (FR-040, FR-041) + reclasificación
│   ├── daily_service.py       # Hora de envío: clima, posposición, pregunta de fatiga, envío del mensaje
│   ├── weekly_job.py          # Generación automática del lunes + fallback AC-16/AC-17b
│   └── notifier.py            # Protocolo Notifier (send_message) + implementación Telegram
├── ai/
│   ├── __init__.py            # Exporta propose_week_plan, draft_daily_message, errores tipados
│   ├── schemas.py             # PlanRequest, WeekPlanProposal, DailyMessageData (pydantic)
│   ├── prompts.py             # Textos de sistema e instrucciones (incluye prohibición médica)
│   └── gemini.py              # Único import de google-genai; timeouts 20 s / 5 s
├── integrations/
│   ├── __init__.py
│   └── openweather.py         # Cliente httpx del forecast 5 días/3 h → Forecast tipado
├── bot/
│   ├── __init__.py
│   └── handlers.py            # /start, /vincular, /registrar, /restablecer, respuesta de fatiga
└── scheduler.py               # Tarea asyncio: tick(now) cada 60 s → weekly_job + daily_service

tests/
├── conftest.py                # DB temporal, Clock fijo, FakeAI, FakeWeather, FakeNotifier, TestClient
├── unit/
│   ├── test_units.py
│   ├── test_profile_rules.py
│   ├── test_weeks.py
│   ├── test_summaries.py
│   ├── test_structure.py
│   ├── test_guardrails.py
│   ├── test_weather_rules.py
│   ├── test_daily_message.py
│   └── test_security.py
├── integration/
│   ├── test_auth_api.py
│   ├── test_profile_api.py
│   ├── test_linking.py
│   ├── test_plan_api.py
│   ├── test_weekly_job.py
│   ├── test_daily_flow.py
│   ├── test_results.py
│   ├── test_schedule_history.py
│   └── test_isolation.py      # AC-37/AC-38
└── contract/
    └── test_api_contract.py   # Códigos y formas de respuesta de contracts/api.md
```

**Structure Decision**: un único proyecto Python con el paquete `app/`, que respeta el comando de AGENTS.md
`uvicorn app.main:app`. Las capas son: `api/` y `bot/` como entrada, `services/` para orquestación e I/O,
`domain/` para reglas deterministas puras sin I/O y `ai/` e `integrations/` para servicios externos.
`domain/` no importa nada de `services/`, `ai/` ni `integrations/`, así que los guardarraíles se testean
como funciones puras. `ai/` no importa `services/` ni `db`. Los tests se dividen en unit (reglas puras),
integration (servicios + SQLite + dobles) y contract (forma de la API).

## Complexity Tracking

> Una excepción documentada al Principio II; ninguna otra violación.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Principio II ("si falta una credencial obligatoria, fallar con error explícito"): sin `TELEGRAM_BOT_TOKEN` la app arranca sin bot ni scheduler en lugar de fallar | AGENTS.md define que sin `TELEGRAM_BOT_TOKEN` se levanta la API sin el bot. Así se pueden desarrollar y testear la API (US1, US7, US8) sin un bot real. El arranque deja un `audit.event("startup", bot=False)` explícito (T031). | Fallar al arrancar sin el token: obliga a tener un bot real para cualquier desarrollo de la API y contradice AGENTS.md. Usar un token falso por defecto: viola el Principio II. |
