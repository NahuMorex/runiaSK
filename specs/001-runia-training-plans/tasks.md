---

description: "Lista de tareas para implementar Runia (PRD-001)"
---

# Tasks: Runia — Planes de entrenamiento para running

**Input**: Documentos de diseño en `specs/001-runia-training-plans/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Se incluyen. La constitución ("Flujo de desarrollo") exige que `uv run pytest` pase antes de cerrar cada tarea y que la
lógica de negocio se pueda testear sin llamadas reales al modelo ni a servicios externos. El plan ya fija los archivos de
`tests/`. Dentro de cada historia, los tests se escriben primero y deben fallar antes de implementar. Una tarea de tests se cierra junto con su tarea de implementación: `uv run pytest` tiene que estar en verde al llegar al checkpoint de la historia, que es donde se aplica la regla de la constitución. Ninguna tarea de una fase se marca `[x]` antes de que su checkpoint pase `uv run pytest` en verde; al pasar, se marcan todas juntas. Así ninguna tarea se cierra con tests en rojo.

**Organization**: Las tareas están agrupadas por historia de usuario para que cada una se pueda implementar y testear por separado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (otro archivo, sin depender de tareas incompletas)
- **[Story]**: historia a la que pertenece (US1…US8)
- Las rutas son relativas a la raíz del repo (`/home/nahu/cursoia/runia2`)

## Convenciones para todas las tareas

- Comandos: `uv sync`, `uv run pytest`, `uv run pytest tests/ruta.py::test_x` (AGENTS.md). Python 3.12 vía uv, nunca el 3.14 del sistema.
- Las reglas citadas como **R-xx** están en `research.md`; las tablas y columnas, en `data-model.md`; los códigos, cuerpos y mensajes fijos, en `contracts/api.md` y `contracts/telegram-bot.md`. Los mensajes fijos se copian **literalmente**.
- `app/domain/` no importa nada de `app/services/`, `app/ai/`, `app/integrations/` ni `app/db.py`: son funciones puras.
- `google-genai` se importa **solo** en `app/ai/gemini.py` (principio I).
- Ninguna credencial lleva valor por defecto: se lee con `app/config.py` (principio II). Los tests inyectan valores falsos con `monkeypatch.setenv`.
- Distancias en centésimas de km (`*_hm`, entero), ritmos y tiempos en segundos, horarios en minutos desde las 00:00, todo en `America/Argentina/Buenos_Aires`.
- Todo SQL vive en `app/services/repository.py`. Las tareas de distintas historias que agregan funciones a ese archivo **no** son paralelas entre sí.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicializar el proyecto uv y el esqueleto de paquetes.

- [X] T001 Crear `pyproject.toml` (proyecto `runia`, `requires-python = "==3.12.*"`). Dependencias: `fastapi`, `uvicorn`, `google-genai`, `python-telegram-bot`, `argon2-cffi`, `pyjwt`, `httpx`, `email-validator`, `tzdata`. Grupo `dev`: `pytest`. Agregar `[tool.pytest.ini_options]` con `testpaths = ["tests"]` y `pythonpath = ["."]`. Crear `.python-version` con `3.12`. Ambos archivos van en la raíz del repo.
- [X] T002 Crear el esqueleto de paquetes con `__init__.py` vacíos: `app/__init__.py`, `app/api/__init__.py`, `app/domain/__init__.py`, `app/services/__init__.py`, `app/ai/__init__.py`, `app/integrations/__init__.py`, `app/bot/__init__.py`. Crear también los directorios `tests/unit/`, `tests/integration/` y `tests/contract/`, sin `__init__.py`.
- [X] T003 Ejecutar `uv sync` para generar `uv.lock` y `.venv/`. Verificar con `uv run python -c "import sys; print(sys.version)"` que la versión es 3.12, y confirmar que `.gitignore` ya ignora `.env`, `*.db` y `.venv/`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuración, reloj, auditoría, unidades, DB, seguridad, modelos de dominio, dependencias de FastAPI y dobles de prueba.

**⚠️ CRITICAL**: Ninguna historia puede empezar hasta terminar esta fase.

- [X] T004 [P] Implementar `app/config.py` con:
  - `class MissingConfigError(RuntimeError)`.
  - `google_api_key()`, `openweather_api_key()` y `jwt_secret()`: leen `os.environ` y lanzan `MissingConfigError("<VAR> no está definida")` si la variable falta o está vacía.
  - `telegram_bot_token() -> str | None`: devuelve `None` si falta, porque la API arranca sin el bot.
  - `db_path() -> str`: lee `RUNIA_DB_PATH`, con valor por defecto `"runia.db"` (no es un secreto).
  - Ninguna credencial lleva valor por defecto.
- [X] T005 [P] Implementar `app/clock.py` con:
  - `TZ = ZoneInfo("America/Argentina/Buenos_Aires")`.
  - El protocolo `Clock` con `now() -> datetime` (aware, en TZ).
  - `SystemClock` y `FixedClock(dt)`, este último con un `advance(timedelta)` mutable.
  - El helper `today(clock) -> date`.
- [X] T006 [P] Implementar `app/audit.py` según R-18:
  - Logger `runia.audit` con un handler a stdout que escribe una línea JSON por evento (`json.dumps(ensure_ascii=False, default=str)`).
  - `event(type: str, **fields)` agrega `ts` en ISO con TZ.
  - `redact(obj)` es recursivo: reemplaza por `"[redacted]"` los valores cuyas claves, en minúsculas, contengan `password`, `token`, `api_key`, `authorization`, `secret` o sean exactamente `code`.
  - `summarize(text, limit=500)` trunca los textos largos.
  - `configure_logging()`, llamado desde `create_app`: fija en `WARNING` los loggers `httpx`, `httpcore` y `telegram`, porque en INFO registran URLs con el token del bot y `appid=` (principio II, SC-008).
  - No importa nada de `app.services`, `app.db` ni `app.ai`.
- [X] T007 [P] Implementar `app/domain/units.py` (R-07):
  - Distancias: `km_to_hm(km: float) -> int` (`round(km*100)`); `hm_to_km(hm) -> float`; `format_km(hm) -> str` con coma decimal y 2 decimales (`235 → "2,35"`).
  - Ritmo: `parse_pace(text) -> int` acepta `m:ss` y `mm:ss` con segundos de 00 a 59 y lanza `ValueError`; `format_pace(s) -> "m:ss"`.
  - Horarios: `parse_hhmm(text) -> int` en minutos, de 00:00 a 23:59; `format_hhmm(min)`.
  - Duraciones: `format_duration(s)` devuelve `m:ss`, o `h:mm:ss` desde 3600 s.
  - Escalas y redondeos: `scale_floor(hm: int, factor: Fraction) -> int` (`floor(hm*factor)`); `target_time_s(hm, pace_s) -> int` (`round_half_up(hm*pace_s/100)` con aritmética entera); `fast_pace_limit(pace_s) -> int` (`ceil(pace_s*944/1000)` con enteros, de modo que 360 → 340).
- [X] T008 [P] Implementar `app/domain/weeks.py` (R-11, FR-016):
  - `week_start(d) -> date` (lunes) y `week_end(d) -> date` (domingo).
  - `remaining_days(d) -> int`, que incluye el día `d` (lunes = 7, domingo = 1).
  - `sessions_required(frequency, start_date) -> int`: `frequency` si `start_date` es lunes y `min(frequency, remaining_days)` en otro caso.
  - `allowed_dates(start_date) -> list[date]`, desde `start_date` hasta el domingo.
  - `is_closed(week_start, today) -> bool`, verdadero si el domingo de esa semana es anterior a `today`.
  - `previous_week_start(ws)`.
  - `WEEKDAY_NAMES_ES = ["lunes", …, "domingo"]` y `weekday_es(d)`.
- [X] T009 Implementar `app/db.py`:
  - `connect(path) -> sqlite3.Connection`, con `check_same_thread=False`, `row_factory=sqlite3.Row`, `PRAGMA foreign_keys=ON` y `PRAGMA journal_mode=WAL` (este último salvo con `:memory:`).
  - `init_db(conn)`: `CREATE TABLE IF NOT EXISTS` de las 11 tablas de `data-model.md` (`users`, `profiles`, `telegram_links`, `one_time_codes`, `plans`, `sessions`, `blocks`, `session_results`, `pending_reclassifications`, `daily_dispatches`, `weekly_generation_runs`), con sus `UNIQUE`, `CHECK` de enums y rangos, `FOREIGN KEY … ON DELETE CASCADE` y `adopted_from_plan_id … ON DELETE SET NULL`.
  - `@contextmanager transaction(conn)`: `BEGIN IMMEDIATE`, y después commit o rollback.
- [X] T010 [P] Implementar `app/domain/models.py`:
  - Dataclasses (`frozen` donde se pueda): `Block(kind: Literal["walk","run"], distance_hm: int, target_pace_s: int|None=None, target_time_s: int|None=None, recovery_after_s: int|None=None)`, `PlannedSession(date, title, blocks: list[Block], reclassified=False)`, `WeekSummary(week_start, has_plan, is_full, is_deload, planned_volume_hm, completed_count, has_partial_rpe7, profile_snapshot: dict|None)`, `GuardrailEvent(rule, scope, session_date, before, after)`, `GuardrailContext` (campos de data-model "Entidades de dominio sin tabla") y `WeatherAssessment(available, unfavorable, extreme, reasons: list[str], alternative_date: date|None, postpone: bool)`, y el modelo pydantic `DailyMessageData` con los campos de `contracts/ai-module.md` (vive acá porque `domain/` no puede importar `app.ai`).
  - Helpers: `run_volume_hm(blocks)`, `is_quality(blocks)` (algún `run` con `target_pace_s`), `session_type_label(blocks) -> "calidad"|"suave"` y `to_easy(blocks) -> list[Block]`. `to_easy` devuelve un único `Block("run", suma de run)`, sin ritmo, tiempo ni recuperación, y elimina la caminata (R-12). Constantes `EASY_TITLE = "Trote suave"` y `QUALITY_TITLE = "Calidad"` (R-05). Agregar `reclassify(blocks) -> list[Block]`: devuelve `to_easy(blocks)` si `is_quality(blocks)` y, si no, los mismos bloques sin cambios (FR-042).
- [X] T011 [P] Implementar `app/security.py`:
  - `PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)`, con `hash_password` y `verify_password`. `verify_password` devuelve `False` ante `VerifyMismatchError` o `InvalidHashError`.
  - `create_token(user_id, auth_time: datetime, now: datetime) -> (token, expires_at)`: JWT HS256 con `sub=str(user_id)`, `iat`, `exp=now+2h` y `auth_time` en epoch, usando `config.jwt_secret()`.
  - `decode_token(token, now) -> (user_id, auth_time)`: lanza `InvalidToken` si la firma no valida, si expiró (verificar `exp` contra `now`, que es inyectable, con `options={"verify_exp": False}` más un chequeo manual) o si `now - auth_time >= 7 días`.
  - `generate_code(length) -> str` con `secrets.choice` sobre `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`, y `hash_code(code) -> str` (SHA-256 hex del código en mayúsculas) (R-15, R-16).
- [X] T012 [P] Crear `app/ai/schemas.py` con los modelos pydantic de `contracts/ai-module.md` (`WeekSummaryIn`, `PlanRequest`, `BlockOut`, `SessionOut` y `WeekPlanProposal`; `DailyMessageData` se importa de `app.domain.models` y se reexporta), y `app/ai/errors.py` con `class AIUnavailableError(Exception)`, que tiene un atributo `reason` cuyo valor es `"timeout"`, `"rate_limit"`, `"server_error"`, `"invalid_response"`, `"invalid_structure"` o `"error"`. En `app/ai/__init__.py` reexportar esos nombres; las funciones se agregan en US3 y US4.
- [X] T013 Crear `app/services/repository.py` con el helper `now_iso(clock)` y las funciones base de usuario y perfil:
  - `create_user(conn, email, password_hash, now) -> int`: inserta también una fila vacía en `profiles`.
  - `get_user_by_email(conn, email)`, con el email normalizado a minúsculas, y `get_user(conn, user_id)`.
  - `get_profile(conn, user_id) -> dict`, `update_profile(conn, user_id, fields: dict, now)`.
  - `get_chat_id(conn, user_id) -> int|None`.
- [X] T014 Implementar `app/services/notifier.py`:
  - El protocolo `Notifier` con `async send_message(chat_id: int, text: str) -> bool`.
  - `TelegramNotifier(bot: telegram.Bot)`: envía sin `parse_mode`, devuelve `True` si Telegram confirma y `False` ante `TelegramError`. Registra `audit.event("message_sent", ok=…)` o `audit.event("external_error", service="telegram", reason=…)`.
- [X] T015 Implementar `app/deps.py` y `app/main.py`.
  - `app/deps.py`:
    - `get_conn(request)`: abre `db.connect(request.app.state.db_path)` por request con `yield` y la cierra al final.
    - `get_clock(request)`: devuelve `request.app.state.clock`.
    - `get_current_user(request, response, conn, clock, authorization: str|None = Header(None))`: valida `Bearer`, aplica `decode_token` y verifica que el usuario exista. Si algo falla, lanza `HTTPException(401, "No autenticado")`. Si todo está bien, setea `response.headers["X-Session-Token"]` con `create_token(user_id, auth_time, now)` (R-15).
    - Getters de `app.state` para `planner`, `writer`, `weather` y `notifier`.
  - `app/main.py`:
    - `create_app(*, db_path=None, clock=None, planner=None, writer=None, weather=None, notifier=None, start_background=True) -> FastAPI`. Guarda todo en `app.state` y, en `lifespan`, llama a `config.jwt_secret()` (si falta, `MissingConfigError` y la app no arranca), abre una conexión y ejecuta `init_db`.
    - `app = create_app()` a nivel de módulo.
    - Por ahora sin routers ni bot: se agregan en cada historia.
- [X] T016 Crear `tests/conftest.py`:
  - Fixture `env` (autouse): `monkeypatch.setenv` con `JWT_SECRET`, `GOOGLE_API_KEY` y `OPENWEATHER_API_KEY` falsos, y `delenv("TELEGRAM_BOT_TOKEN")`.
  - Fixture `db_path`: un archivo en `tmp_path`. Fixture `conn`: `connect` más `init_db`.
  - Fixture `clock`: `FixedClock` en jueves 2026-10-15 10:00 BA.
  - Dobles:
    - `FakePlanner`: `proposal` configurable o `error: AIUnavailableError`; guarda los `PlanRequest` recibidos.
    - `FakeWriter`: texto configurable, error o `delay`.
    - `FakeWeather`: un `Forecast` configurable o `WeatherUnavailableError`, que se importa con lazy import para no romper antes de US5.
    - `FakeNotifier`: guarda `(chat_id, text)` y devuelve `True`.
  - Fixture `client`: `TestClient(create_app(db_path=…, clock=…, planner=…, writer=…, weather=…, notifier=…, start_background=False))`.
  - Helpers `register_and_login(client, email, password="clave-segura-1") -> headers` y `seed_profile(conn, user_id, **overrides)`, este último con un perfil intermedio completo y válido por defecto.
- [X] T017 [P] Escribir `tests/unit/test_units.py` (conversiones, `format_km`, `parse_pace` inválidos, `fast_pace_limit(360)==340`, `target_time_s`, `scale_floor` con `Fraction(5,8)`), `tests/unit/test_weeks.py` (`sessions_required` lunes/jueves/domingo, `is_closed`, `allowed_dates`) y `tests/unit/test_security.py` (parámetros Argon2id en el hash `$argon2id$v=19$m=19456,t=2,p=1`, token vencido a las 2 h, rechazo con `auth_time` de 7 días, `hash_code` estable, `MissingConfigError` sin `JWT_SECRET`). Ejecutar `uv run pytest tests/unit`.

**Checkpoint**: la base está lista y `uv run pytest` pasa. Desde acá se pueden empezar las historias.

---

## Phase 3: User Story 1 - Crear cuenta y cargar perfil de corredor (Priority: P1) 🎯 MVP

**Goal**: registro, login con JWT renovable y perfil validado (FR-001..FR-006).

**Independent Test**: registrar una cuenta, iniciar sesión, hacer `PUT /profile` con datos válidos y `GET /profile` para ver los valores. Enviar datos inválidos y verificar 422 sin cambios (AC-01..AC-07, AC-51, AC-72, AC-73).

### Tests for User Story 1 ⚠️

- [X] T018 [P] [US1] Escribir `tests/unit/test_profile_rules.py`. Casos que se aceptan: cada campo en sus límites (frecuencia 1 y 7; distancia 1 y 42,2; ritmo 3:00 y 10:00; ciudad de 100 caracteres; rango de exactamente 60 min; envío un minuto antes del fin). Casos que se rechazan: frecuencia 0 y 8, distancia 0,99 y 42,21, ritmo 2:59, 10:01 y "6:60", ciudad vacía o de espacios y de 101 caracteres, nivel "experto", inicio ≥ fin, rango de 59 min, envío ≥ fin, `null` en un campo distinto de `current_pace`. También verificar que la validación combina el PUT parcial con el perfil guardado (R-20).
- [X] T019 [P] [US1] Escribir `tests/integration/test_auth_api.py`:
  - Registro: 201, 409 con el mismo email en mayúsculas, 422 con email inválido y con contraseñas de 7 y 129 caracteres, sin crear filas (AC-01, AC-02, AC-72).
  - Login: 200 con `access_token` y `expires_at` a 2 h, y 401 con credenciales incorrectas (AC-03, AC-04).
  - Autenticación: un `GET /profile` sin token, con un token basura y con un token vencido (avanzando `FixedClock` 2 h 1 min) da 401 sin cuerpo de datos (AC-73).
  - Renovación: una request válida devuelve `X-Session-Token` con un `exp` nuevo. Si se renueva continuamente durante 7 días desde el login, la siguiente request da 401 (AC-05).
- [X] T020 [P] [US1] Escribir `tests/integration/test_profile_api.py`. Casos:
  - Un `PUT /profile` completo da 200 y un `GET` posterior devuelve los mismos valores (AC-06, AC-51).
  - Un PUT parcial solo cambia los campos enviados.
  - Un PUT con un campo inválido entre varios válidos da 422 y `GET` muestra que no se guardó ninguno (AC-07).
  - El paso de intermedio a novato y el de novato a avanzado dan 200 (AC-55, FR-008).
  - `telegram_linked` es `false` mientras no hay un vínculo.

### Implementation for User Story 1

- [X] T021 [US1] Implementar `app/domain/profile_rules.py`:
  - `ProfileUpdate` (pydantic, todos los campos opcionales; ver `contracts/api.md`), con `model_config = ConfigDict(extra="forbid")` y validadores de formato (`level` es Literal, `preferred_range: {start, end}`).
  - `merge_and_validate(stored: dict, update: ProfileUpdate) -> dict`: devuelve el perfil combinado en unidades internas (`*_hm`, `*_s`, `*_min`) y lanza `ProfileValidationError(list[str])` ante reglas cruzadas o un `null` no permitido.
  - `to_public(profile: dict, linked: bool) -> dict`, con el formato `Profile` del contrato.
- [X] T022 [US1] Implementar `app/services/accounts.py` con `register(conn, email, password, now) -> int`, que lanza `EmailTakenError` si el email existe, y `login(conn, email, password, clock) -> (token, expires_at)`, que lanza `InvalidCredentialsError`. El login usa `auth_time = now`. Registrar `audit.event("tool_call", tool="db", op="register"|"login")` sin datos sensibles.
- [X] T023 [US1] Implementar `app/api/auth.py` (`APIRouter(prefix="/auth")`):
  - `POST /register` recibe un body con `email: EmailStr` y `password: str` de 8 a 128 caracteres (`Field(min_length=8, max_length=128)`). Responde 201 `{id, email}`, o 409 `{"detail": "El email ya está registrado"}`.
  - `POST /login` responde 200 `{access_token, token_type: "bearer", expires_at}`, o 401 `{"detail": "Credenciales inválidas"}`.
- [X] T024 [US1] Implementar `app/api/profile.py` (`APIRouter(prefix="/profile")`), donde todas las rutas dependen de `get_current_user`:
  - `GET ""` devuelve `to_public`.
  - `PUT ""` valida con `merge_and_validate`, guarda con `update_profile` en una transacción, emite `audit.event("tool_call", tool="db", op="update_profile")` y responde 200. Si la validación falla, responde 422 con `detail` sin persistir nada.
- [X] T025 [US1] Registrar los routers `auth` y `profile` en `create_app` de `app/main.py`. Ejecutar `uv run pytest tests/unit/test_profile_rules.py tests/integration/test_auth_api.py tests/integration/test_profile_api.py` hasta que todo pase.

**Checkpoint**: US1 funciona y se puede testear sola.

---

## Phase 4: User Story 2 - Vincular la cuenta con Telegram (Priority: P1)

**Goal**: código de vinculación de un solo uso (15 min) y vínculo 1:1 permanente desde el bot (FR-011).

**Independent Test**: generar un código, enviarlo con `/vincular` antes de los 15 minutos, reintentar con el mismo código, con uno vencido y desde un segundo chat (AC-44..AC-46).

### Tests for User Story 2 ⚠️

- [X] T026 [P] [US2] Escribir `tests/integration/test_linking.py`. Los casos se testean llamando a `handle_vincular(conn, clock, chat_id, args)` de `app/bot/handlers.py`, sin PTB real:
  - `POST /telegram/link-code` da 201 con un código de 8 caracteres.
  - `/vincular` con el código vincula el chat y el texto de respuesta coincide con el contrato.
  - Reusar el código se rechaza (AC-44).
  - Un código inexistente o con 15 min 1 s se rechaza sin crear un vínculo (AC-45).
  - Un segundo código válido desde otro chat para una cuenta ya vinculada se rechaza sin cambiar el `chat_id`, y el código **no** queda consumido.
  - Un chat ya vinculado que intenta vincular otra cuenta se rechaza (AC-46).
  - `POST /telegram/link-code` con una cuenta ya vinculada da 409.
  - `GET /profile` devuelve `telegram_linked: true` después de vincular.

### Implementation for User Story 2

- [X] T027 [US2] Agregar a `app/services/repository.py`:
  - `create_code(conn, user_id, purpose, code_hash, expires_at)`.
  - `consume_code(conn, purpose, code_hash, now) -> user_id|None`: `UPDATE one_time_codes SET used_at=? WHERE code_hash=? AND purpose=? AND used_at IS NULL AND expires_at > ? RETURNING user_id`.
  - `find_valid_code(conn, purpose, code_hash, now) -> user_id|None`, que lee sin consumir.
  - `get_user_by_chat(conn, chat_id)` y `create_link(conn, user_id, chat_id, now)`.
- [X] T028 [US2] Implementar `app/services/linking.py`:
  - `create_link_code(conn, user_id, clock) -> (code, expires_at)`: 8 caracteres, vence en 15 min y lanza `AlreadyLinkedError` si la cuenta ya tiene un chat. Emite `audit.event("tool_call", tool="db", op="create_link_code")` sin el código.
  - `link_chat(conn, chat_id, code, clock) -> Literal["linked","invalid","already_linked"]`: dentro de `transaction`, busca el código válido, verifica que ni el chat ni la cuenta estén vinculados y solo después consume el código y crea el vínculo.
  - Registrar `audit.event("tool_call", tool="db", op="link_chat", outcome=…)`.
- [X] T029 [US2] Implementar `app/api/telegram_link.py` con `POST /telegram/link-code`. Responde 201 con `{code, expires_at, instructions}` (el texto del contrato) o 409 con `{"detail": "Tu cuenta ya tiene un chat de Telegram vinculado"}`. Registrarlo en `app/main.py`.
- [X] T030 [US2] Implementar `app/bot/handlers.py`. Hay dos capas:
  - **Funciones núcleo**, testeables: `async handle_start() -> str` y `async handle_vincular(conn, clock, chat_id, args) -> str`. Devuelven los textos exactos de `contracts/telegram-bot.md`; si falta el argumento, devuelven el texto de código inválido.
  - **Adaptadores PTB**: `build_application(token, app_state) -> telegram.ext.Application`, que registra `CommandHandler("start")` y `CommandHandler("vincular")`. Cada adaptador abre su propia conexión con `db.connect(app_state.db_path)` y responde con `update.message.reply_text(text)`. La aplicación se construye con `ApplicationBuilder().token(token).concurrent_updates(True).build()`, para que las respuestas de fatiga de varios usuarios se procesen en paralelo (SC-004); con WAL y el `timeout` por defecto de 5 s de `sqlite3` alcanza para 10 escrituras concurrentes.
- [X] T031 [US2] En el `lifespan` de `app/main.py`, si `start_background` es verdadero y `config.telegram_bot_token()` no es `None`:
  - Al arrancar: `application = build_application(...)`, después `await application.initialize()`, `await application.start()` y `await application.updater.start_polling()`, y guardar `app.state.notifier = TelegramNotifier(application.bot)`, salvo que se haya inyectado otro notifier.
  - Al apagar: `updater.stop()`, `stop()` y `shutdown()`.
  - Si no hay token, registrar `audit.event("startup", bot=False)`.
  - Ejecutar `uv run pytest tests/integration/test_linking.py`.

**Checkpoint**: US1 y US2 funcionan cada una por separado.

---

## Phase 5: User Story 3 - Recibir un plan semanal seguro y progresivo (Priority: P1)

**Goal**: `POST /plan` y la generación del lunes, con validación estructural, el pipeline determinista de guardarraíles (R-06) y el fallback de AC-16 y AC-17b (FR-012..FR-028).

**Independent Test**: con un perfil completo y un `FakePlanner` que propone cargas excesivas, pedir el plan y verificar los topes, las conversiones y los recortes. Simular el lunes con `scheduler.tick` (AC-08..AC-11, AC-14..AC-22, AC-56..AC-67, AC-74, AC-76, AC-77, AC-82, AC-83).

### Tests for User Story 3 ⚠️

- [X] T032 [P] [US3] Escribir `tests/unit/test_structure.py`, con un caso por regla de R-05 que valide la propuesta:
  - Rechazos generales: cantidad distinta de `sessions_required`, una fecha repetida, una fecha antes de `start_date` o después del domingo, una sesión sin `run`, un bloque con km 0 o negativo, un ritmo fuera de 60..1200 s y una recuperación negativa.
  - Primera semana de un novato: se rechaza si no alterna walk/run y se acepta si alterna `walk,run,walk,run`. Se rechaza si alterna pero algún `run` tiene `target_pace_s` (regla (c)).
  - Título: vacío, de 41 caracteres o con dígitos se reemplaza por `"Calidad"` o `"Trote suave"` según el tipo; uno válido se conserva.
  - Calidad con 2 tramos: se rechaza si el primero no tiene `recovery_after_s` y se acepta si el último no la tiene.
- [X] T033 [P] [US3] Escribir `tests/unit/test_summaries.py`, construyendo filas en memoria:
  - Racha: 4 semanas con una Completada dan descarga; una semana sin plan corta la racha; una semana sin Completadas la vuelve a 0 (AC-19b); el conteo reinicia después de una descarga (AC-19c); una primera semana parcial con una Completada cuenta.
  - Calidad de novatos: elegible solo con ritmo y 3 semanas cerradas que cumplen; no elegible con menos de 3 semanas, con una semana sin Completada o con una Parcial de RPE ≥ 7 (AC-20).
  - Contexto: sin semana anterior da topes iniciales (AC-61); una anterior parcial sin semanas completas previas da topes iniciales (AC-62); una anterior parcial con una completa previa da base = última completa (AC-74); una anterior sin Completadas da `no_increase_hm` (AC-63).
  - Piso de AC-66: solo aplica si el snapshot del perfil es igual al actual, la semana anterior fue completa, tuvo al menos una Completada y no fue de descarga.
  - Semana posterior a la descarga: target = V4; si la descarga no tuvo ninguna Completada, target = None y `no_increase` = V5 (AC-19d).
  - AC-42: una sesión pospuesta por clima en la semana anterior no descuenta la base del 10% (se usa el `planned_volume_hm` completo) y su volumen no se suma a la semana actual.
- [X] T034 [P] [US3] Escribir `tests/unit/test_guardrails.py`, un test por regla, que además verifica que se emite un `GuardrailEvent` con `before` y `after`:
  - Topes iniciales de 2, 5 y 10 km por sesión y × frecuencia semanal (AC-61).
  - Tope del 10% sin piso que lo supere (AC-18).
  - Caso de AC-76: sesión de 8 km con tope de 5, factor 5/8 y después factor semanal sobre el volumen ya recortado; la caminata, las recuperaciones y el ritmo no cambian; `target_time_s` se recalcula.
  - Conversión de calidad no permitida y de la segunda calidad en un único bloque de trote (AC-77, AC-21).
  - Ritmo acotado a 340..360 para 6:00, con el tiempo recalculado y los km sin cambios (AC-22, AC-83).
  - Tope por distancia objetivo (AC-67), usando el menor entre el tope inicial y la distancia (CHK016).
  - Descarga dentro de [0,70; 0,80] × V4 (AC-19a).
  - Semana posterior iguala V4 con la tolerancia de 0,01 km por bloque (AC-19d).
  - Escalado al piso de AC-66 sin superar un tope por sesión; si el tope impide llegar al piso, el volumen queda en el tope (AC-82).
  - Pisos que no se aplican a planes parciales (R-10).
  - Reclasificación pendiente de 2: convierte las dos primeras sesiones si son de calidad y deja intactas las suaves (incluida la caminata de un novato), marcando ambas como reclasificadas. Las de calidad convertidas quedan con `title = "Trote suave"`.
  - Bloque que queda en 0 km sin eliminarse (R-07).
- [X] T035 [P] [US3] Escribir `tests/integration/test_plan_api.py`, usando `seed_profile` y un vínculo insertado directamente:
  - Mensajes 422 de AC-08, AC-09 (un caso por campo, con el texto exacto `{campo}`) y AC-11.
  - Un novato sin ritmo genera el plan (AC-10).
  - Un 201 con un plan parcial de jueves tiene `min(freq, 4)` sesiones (AC-56, AC-57), y `FakeNotifier` no recibe nada.
  - Un segundo POST da 409 (AC-58).
  - Si `FakePlanner` lanza `AIUnavailableError` o devuelve una propuesta inválida, la respuesta es 503 con el mensaje exacto y no se crea ninguna fila en `plans` (AC-17).
  - La primera semana de un novato tiene bloques walk/run (AC-14). Un novato cuyo primer plan fue parcial recibe `first_week_novice=True` también en su primer plan completo y `False` en el siguiente; un intermedio que baja a novato vuelve a recibir `True` (FR-015).
  - Una sesión de calidad intermedia trae `target_time` y `recovery_after` (AC-15).
  - Un plan completo en lunes tiene N sesiones en días distintos (AC-65).
  - El `PlanRequest` recibido por `FakePlanner` solo contiene `WeekSummaryIn` y ningún email ni chat_id (FR-028).
- [X] T036 [P] [US3] Escribir `tests/integration/test_weekly_job.py`, llamando a `scheduler.tick(app_state, now)` con `now` = lunes 2026-10-19 00:01:
  - Un usuario elegible recibe un plan completo y `FakeNotifier` recibe el resumen con día, tipo y km (AC-59).
  - Un usuario sin vínculo o con el perfil incompleto no recibe ningún plan (AC-60).
  - Un segundo tick no duplica nada.
  - Si `FakePlanner` falla y hay un plan previo, el sistema adopta los mismos días de la semana, aplica los guardarraíles actuales (si la semana previa no tuvo Completadas, el volumen no supera el planificado), usa `source='fallback'` y envía el mensaje con el aviso exacto (AC-16).
  - Si falla sin un plan previo, envía "No es posible generar un plan en este momento." y no crea ningún plan (AC-17b). Un tick posterior no reenvía el mensaje.
  - Con una reclasificación pendiente de 1 y un `FakePlanner` que falla, el plan adoptado tiene la primera sesión reclasificada a suave, `get_pending_reclass` queda en 0 y el plan del lunes siguiente no reclasifica nada (FR-042).
  - Si el último plan válido fue parcial (jueves a domingo, 3 sesiones), el plan adoptado tiene `start_date` el lunes, `is_full=1`, sesiones el jueves, el viernes y el domingo de la semana actual, y se le aplican los pisos (R-13).
  - Si `FakePlanner` lanza `RuntimeError` para un usuario, los demás reciben su plan, la corrida del primero queda con `outcome="error"` y un tick posterior no lo reintenta.
- [X] T088 [P] [US3] Verificador independiente de SC-001 (lista cerrada de la spec):
  - Crear `tests/sc001_check.py` con `check_sc001(sessions: list[PlannedSession], ctx: GuardrailContext) -> list[str]`, que devuelve una violación por regla incumplida. Se reimplementa desde la spec y **no** importa `app.domain.guardrails` (puede usar `app.domain.models` y `app.domain.units`). Los tests lo importan con `from tests.sc001_check import check_sc001` (`pythonpath = ["."]`). Reglas:
    - Por sesión: km de trote ≤ `min` entre el tope inicial por nivel (si `ctx.initial_caps`) y `target_distance_hm` (FR-018, FR-025).
    - Semanal: volumen ≤ `min` entre `tope_inicial×frequency`, `floor(base_10_hm×11/10)` (salvo `is_post_deload`), `no_increase_hm`, `floor(deload_v4_hm×8/10)` y `post_deload_target_hm` (FR-018 a FR-021).
    - Calidad: ninguna sesión de calidad si `level == "novato"` y no `novice_quality_allowed`; como máximo una por semana (FR-022, FR-023).
    - Ritmo: todo tramo con ritmo en `[fast_pace_limit(p), p]` y `target_time_s == round_half_up(distance_hm × ritmo ÷ 100)` (FR-024).
    - Reclasificación: las primeras `pending_reclass` sesiones por fecha tienen `reclassified=True` y ninguna es de calidad (FR-042).
    - Pisos, solo si `ctx.is_full`: volumen ≥ piso − n.º de bloques `run` (en hm), salvo que un tope lo impida: alguna sesión está en su tope o el volumen está en el tope semanal, con la misma tolerancia (FR-026, AC-82).
  - Escribir `tests/unit/test_sc001.py`: correr `guardrails.apply` sobre una matriz de propuestas adversas (sesiones largas, volumen excesivo, varias de calidad, ritmos fuera de rango, novatos con tramos con ritmo) por cada contexto (topes iniciales, 10%, semana vacía, descarga, posterior a la descarga con y sin Completadas, AC-66, parcial y completa, reclasificación pendiente de 1 y 2, piso bloqueado por un tope) y verificar que `check_sc001` no devuelve violaciones. Agregar casos negativos con planes armados a mano que violan cada regla, para comprobar que el verificador las detecta.
  - Escribir `tests/integration/test_sc001_delivered.py`: con un `FakePlanner` adverso, verificar con `check_sc001` el plan guardado por `POST /plan`, por la generación del lunes y por el fallback de AC-16, armando `ctx` con `build_context` sobre el historial guardado (SC-001 cuenta los planes generados y los adoptados).

### Implementation for User Story 3

- [X] T037 [US3] Agregar a `app/domain/profile_rules.py` la función `missing_field_message(profile: dict, linked: bool) -> str | None`, con el orden de `data-model.md` (nivel → frecuencia → distancia objetivo → ritmo, solo si el nivel no es novato → ciudad → rango horario → hora de envío → Telegram). Devuelve los textos exactos: `"No hay datos sobre tu ritmo cargados en tu perfil"`, `"No hay datos sobre tu {campo} cargados en tu perfil"` y `"Tu cuenta no tiene un chat de Telegram vinculado"`.
- [X] T038 [P] [US3] Implementar `app/domain/structure.py` con `validate_proposal(proposal: WeekPlanProposal, *, start_date, sessions_required, first_week_novice) -> list[PlannedSession]`. Lanza `InvalidProposalError(reason)` según R-05, incluida la regla (c) (un tramo con ritmo en la primera semana de un novato), normaliza `title` según R-05 y, si la propuesta es válida, la convierte a `PlannedSession` con `Block` en centésimas (`km_to_hm`), sin `target_time_s` (lo calcula el pipeline). `app/domain/` no puede importar `app.ai`: recibir la propuesta como un objeto con atributos `sessions[].date/title/blocks[].kind/distance_km/target_pace_s/recovery_after_s` (duck typing) o como `dict`.
- [X] T039 [P] [US3] Implementar `app/domain/summaries.py` (R-11):
  - `summarize_weeks(plans_rows, sessions_rows, results_rows) -> dict[date, WeekSummary]`.
  - `deload_streak(summaries, current_week_start) -> int`.
  - `novice_quality_allowed(level, current_pace_s, summaries, current_week_start) -> bool`.
  - `build_context(profile, summaries, current_week_start, start_date, pending_reclass) -> GuardrailContext`. Calcula `initial_caps`, `base_10_hm`, `no_increase_hm`, `is_deload` y `deload_v4_hm` (si la racha es 4), `is_post_deload` (si el plan de la semana anterior tiene `is_deload=1`, haya tenido Completadas o no), `post_deload_target_hm` (si la semana anterior fue de descarga y tuvo alguna Completada; si no tuvo, `no_increase_hm = V5`) y `floor_prev_hm` (AC-66: semana anterior completa, con alguna Completada, no de descarga y snapshot igual al perfil actual; no aplica si la semana actual es de descarga).
  - `recent_summaries_for_ai(summaries, n=4) -> list[WeekSummary]`.
- [X] T040 [US3] Implementar en `app/domain/guardrails.py` la función `apply(sessions: list[PlannedSession], ctx: GuardrailContext) -> (list[PlannedSession], list[GuardrailEvent])` con los pasos 1 a 4 de R-06:
  - Paso 1, reclasificación pendiente: aplica `reclassify` a las primeras `ctx.pending_reclass` sesiones por fecha (solo convierte las de calidad) y marca `reclassified=True` en todas ellas.
  - Paso 2, calidad de novatos (FR-022): convierte todas las de calidad si `level == "novato"` y no `novice_quality_allowed`.
  - Paso 3, máximo una de calidad (FR-023): conserva la primera por fecha.
  - Paso 4, ritmo (FR-024): con `current_pace_s` definido, acota cada tramo a `[fast_pace_limit(p), p]`. Si no hay ritmo (un novato no elegible), ya no quedan tramos después del paso 2.
  - Toda sesión de calidad convertida en los pasos 1 a 3 queda con `title = EASY_TITLE`.
  - Al final, recalcula `target_time_s` de todo tramo con ritmo.
  - Emite eventos `reclassification_pending`, `novice_quality`, `max_one_quality` y `pace_clamp`.
- [X] T041 [US3] Completar en `app/domain/guardrails.py` los pasos 5 y 6 de R-06:
  - **Topes por sesión**: el tope efectivo es `min` entre el tope inicial por nivel (200, 500 o 1000 hm si `ctx.initial_caps`) y `target_distance_hm`. Si `run_volume > tope`, el factor es `Fraction(tope, run_volume)` y se aplica `scale_floor` solo a los bloques `run`.
  - **Topes semanales**: el tope efectivo es `min` entre `tope_inicial×frequency`, `floor(base_10_hm×11/10)`, `no_increase_hm`, `floor(deload_v4_hm×8/10)` y `post_deload_target_hm`. El 10% se omite si `ctx.is_post_deload`. El factor `Fraction(tope, volumen)` se calcula sobre el volumen ya recortado.
  - Recalcular `target_time_s` después de cada escala.
  - Emitir los eventos `session_cap` (`rule`: `initial_cap` o `target_distance`) y `weekly_cap` (`rule`: `initial_weekly`, `ten_percent`, `no_increase`, `deload` o `post_deload`).
- [X] T042 [US3] Completar en `app/domain/guardrails.py` el paso 7 de R-06, los pisos, que solo se aplican si `ctx.is_full`:
  - El piso es el `max` entre `floor_prev_hm`, `ceil(deload_v4_hm×7/10)` y `post_deload_target_hm`.
  - Si `volumen < piso − n_bloques_run` (la tolerancia), el factor es `min(Fraction(piso, vol), min_s Fraction(tope_s, run_s), Fraction(tope_semanal, vol))`, y se aplica `scale_floor` a los bloques `run` solo si el factor es mayor que 1.
  - Emitir el evento `floor_scale`.
  - Agregar `planned_volume_hm(sessions)`.
- [X] T043 [P] [US3] Implementar `app/ai/prompts.py` con `PLAN_SYSTEM_PROMPT` (en español, con las reglas de `contracts/ai-module.md` para el plan, incluida la de que la entrada en calor y la vuelta a la calma, si se proponen, vengan como bloques explícitos `run` o `walk`, sin km implícitos (FR-019), y la prohibición de consejo médico o de lesiones) y `build_plan_prompt(req: PlanRequest) -> str`, que serializa `req.model_dump_json()` con instrucciones. No debe incluir ningún email ni chat_id.
- [X] T044 [US3] Implementar en `app/ai/gemini.py`, el único archivo que importa `from google import genai` y `from google.genai import types`:
  - `_client()`: perezoso, con `genai.Client(api_key=config.google_api_key())`.
  - `async propose_week_plan(req) -> WeekPlanProposal`: llama a `asyncio.wait_for(client.aio.models.generate_content(model="gemini-3.5-flash-lite", contents=build_plan_prompt(req), config=types.GenerateContentConfig(system_instruction=PLAN_SYSTEM_PROMPT, response_mime_type="application/json", response_schema=WeekPlanProposal)), 20)` y parsea el resultado con `WeekPlanProposal.model_validate_json(resp.text)`.
  - Mapear `asyncio.TimeoutError` a `"timeout"`, un `errors.APIError` con code 429 a `"rate_limit"`, uno con code ≥ 500 a `"server_error"` y `ValidationError`/`ValueError` o un texto vacío a `"invalid_response"`, siempre lanzando `AIUnavailableError(reason)`.
  - Emitir `audit.event("llm_call", operation="plan", prompt_summary=…, response_summary=…, duration_ms=…, outcome=…)`.
  - Exportar `propose_week_plan` en `app/ai/__init__.py`.
- [X] T045 [US3] Agregar a `app/services/repository.py`:
  - `get_plan_for_week(conn, user_id, week_start)` y `get_last_plan(conn, user_id)` (el de `week_start` más reciente, con sesiones y bloques).
  - `save_plan(conn, user_id, *, week_start, start_date, is_full, is_deload, is_post_deload, source, adopted_from_plan_id, planned_volume_hm, profile_snapshot, sessions: list[PlannedSession], now) -> int`, que inserta `plans`, `sessions` (con `user_id`) y `blocks` con su `position`.
  - `history_rows_for_summaries(conn, user_id, before_week_start)`, que devuelve los planes, las sesiones y los resultados de semanas anteriores.
  - `get_pending_reclass(conn, user_id) -> int` y `consume_pending_reclass(conn, user_id)`.
  - `eligible_users_for_monday(conn)` (usuarios con un vínculo) y `record_weekly_run(conn, user_id, week_start, outcome, now) -> bool`, que devuelve `False` si ya existe.
- [X] T046 [US3] Implementar `app/services/plan_service.py`:
  - `async build_and_save_plan(conn, user_id, clock, planner, *, source) -> plan_id`:
    1. Lee el perfil y el vínculo, y valida con `missing_field_message`; si falta algo, lanza `IncompleteProfileError(msg)`.
    2. Calcula `ws` y `start_date` (hoy) y lanza `PlanExistsError` si ya existe un plan para la semana.
    3. Calcula los resúmenes y el contexto.
    4. Arma el `PlanRequest` (con `target_volume_km` igual al tope semanal efectivo o a 0,75 × V4 en la descarga, `max_session_km`, `first_week_novice` = el nivel actual es novato y no existe un plan anterior de semana completa con `profile_snapshot` de nivel novato (FR-015), `quality_allowed` y `recent_weeks`).
    5. `await planner(req)`, después `validate_proposal` y después `guardrails.apply`. `InvalidProposalError` se trata como `AIUnavailableError("invalid_structure")` y se registra con `audit.event("plan_generation", outcome="failed", reason=…)`.
    6. Guarda dentro de `transaction` con `is_deload=ctx.is_deload` e `is_post_deload=ctx.is_post_deload`, consume la reclasificación pendiente y emite `audit.event("tool_call", tool="db", op="save_plan")`.
    7. Emite `audit.event("guardrail", …)` por cada evento y `audit.event("plan_generation", source, outcome="created", planned_volume_hm)`.
  - `async adopt_last_valid_plan(conn, user_id, clock) -> plan_id | None` (R-13): mapea por día de la semana las sesiones del último plan a la semana actual y aplica `guardrails.apply` con el contexto actual, armado con `build_context(..., start_date=ws, ...)`. Dentro de una misma `transaction` guarda con `source="fallback"`, `adopted_from_plan_id`, `start_date=ws`, `is_full=True` e `is_deload`/`is_post_deload` tomados de `ctx`, consume la reclasificación pendiente con `consume_pending_reclass` (igual que `build_and_save_plan`) y emite `audit.event("tool_call", tool="db", op="adopt_plan")`.
  - `serialize_plan(conn, plan_id, today) -> dict`, con la forma `Plan` del contrato (`type`, `run_km`, `blocks` con `kind` "trote"/"caminata", `target_pace`, `target_time`, `recovery_after` y `status` calculado con `status_label`).
  - `status_label(session_row, result_row, today) -> str` (R-19).
- [X] T047 [US3] Implementar `app/api/plan.py` con `POST /plan`, que depende de `get_current_user` y `planner`. Llama a `build_and_save_plan(source="on_demand")` y mapea las excepciones: `IncompleteProfileError` a 422 con `detail` igual al mensaje, `PlanExistsError` a 409 con "Ya tenés un plan para la semana en curso" y `AIUnavailableError` a 503 con "No es posible generar un plan en este momento.". Si todo sale bien, responde 201 con `serialize_plan`. No llama al notifier. Registrar el router en `app/main.py` e inyectar el `planner` por defecto (`app.ai.propose_week_plan`) en `create_app`. Si se usa el planner por defecto, el `lifespan` llama a `config.google_api_key()` al arrancar (principio II).
- [X] T048 [US3] Implementar `app/services/weekly_job.py`:
  - `async run_monday(conn, clock, planner, notifier)`: corre si `today` es lunes. Para cada usuario de `eligible_users_for_monday` sin una corrida registrada para la semana:
    1. Si el perfil está incompleto, `outcome="skipped_incomplete"` sin generar nada (AC-60).
    2. Si ya tiene plan, `outcome="skipped_existing"`.
    3. Si no, `build_and_save_plan(source="monday")` y envía el resumen.
    4. Ante `AIUnavailableError`, `adopt_last_valid_plan`, que envía el aviso más el resumen; si no hay un plan previo, envía "No es posible generar un plan en este momento.".
    5. Cualquier otra excepción se captura por usuario: registra `audit.event("plan_generation", source="monday", outcome="error", reason=…)` y la corrida con `outcome="error"`, y sigue con el usuario siguiente.
  - `format_plan_summary(plan_dict) -> str`, con el formato de `contracts/telegram-bot.md` (`"Tu plan de la semana del dd/mm:"` más líneas `- Día: tipo, x,xx km de trote`).
- [X] T049 [US3] Implementar `app/scheduler.py`:
  - `async tick(state, now)`: abre una conexión y llama a `weekly_job.run_monday` con un `FixedClock(now)`. La parte diaria se agrega en US4.
  - `async run_forever(state)`: un bucle `while True` con `tick(state, state.clock.now())` y `asyncio.sleep(60)`; captura y registra en audit cualquier excepción sin cortar el bucle.
  - En el `lifespan` de `app/main.py`, si el bot arrancó, crear `asyncio.create_task(run_forever(app.state))` y cancelarla al apagar.
  - Ejecutar `uv run pytest tests/unit/test_structure.py tests/unit/test_summaries.py tests/unit/test_guardrails.py tests/integration/test_plan_api.py tests/integration/test_weekly_job.py tests/unit/test_sc001.py tests/integration/test_sc001_delivered.py`.

**Checkpoint**: US1 a US3 funcionan. Se genera un plan seguro a demanda y los lunes.

---

## Phase 6: User Story 4 - Recibir el mensaje diario ajustado por fatiga (Priority: P1)

**Goal**: a la hora de envío, preguntar la fatiga y esperarla hasta 2 h; con la respuesta, enviar el mensaje redactado por Gemini y validado, o la plantilla (FR-029..FR-033).

**Independent Test**: con un plan vigente y una sesión hoy, avanzar `FixedClock` hasta la hora de envío, ejecutar `tick` y responder la fatiga con el núcleo del handler. Verificar el contenido, el máximo de 150 palabras, la plantilla de respaldo y la espera de 2 h (AC-27, AC-28, AC-47, AC-48, AC-75, AC-78..AC-80).

### Tests for User Story 4 ⚠️

- [X] T050 [P] [US4] Escribir `tests/unit/test_daily_message.py`:
  - `render_template` siempre da ≤ 150 palabras e incluye el tipo, el rango y, según la sesión, el ritmo y la secuencia (AC-27, AC-28).
  - Con fatiga ≥ 8 y una sesión de calidad, el tipo es "suave/recuperación" y queda un solo bloque de trote sin ritmo (AC-48).
  - Con fatiga ≥ 8 y una sesión suave, se conservan los bloques y aparece "La sesión se mantiene suave por la fatiga." (AC-80).
  - `validate_draft` rechaza, en un caso cada uno: texto vacío, 151 palabras, falta del rango, falta del ritmo, un número ajeno ("12 km"), "¿", "?", `**`, `# `, `- ` al inicio de línea y `[x](y)` (AC-78). Acepta un texto válido que reordena los datos.
- [X] T051 [P] [US4] Escribir `tests/integration/test_daily_flow.py`, sembrando un plan con `save_plan`, con `send_time` 06:00 y `FakeWeather` sin alertas:
  - `tick` a las 05:59 no hace nada. `tick` a las 06:00 envía la pregunta de fatiga exacta y crea un `daily_dispatch` `awaiting_fatigue` (AC-47).
  - `handle_text(chat_id, "abc")` vuelve a preguntar sin enviar el mensaje, y `asked_at` no cambia (AC-75).
  - `handle_text(chat_id, "9")` envía el mensaje ajustado, devuelve `None`, `FakeNotifier` registra exactamente un envío a ese chat y el estado pasa a `sent`.
  - Sin respuesta, un `tick` a las 08:00 envía el mensaje sin ajuste, y una respuesta tardía se ignora.
  - Si `FakeWriter` lanza `AIUnavailableError` o tarda más de 5 s, se envía la plantilla y se registra `external_error`/`llm_call` (AC-79).
  - Si `FakeWriter` devuelve un texto inválido, se envía la plantilla (AC-78).
  - Un día sin sesión no envía nada.
  - Un plan creado a las 10:00 con sesión hoy y `send_time` 06:00: el `tick` de las 10:01 envía la pregunta de fatiga. Si la sesión de hoy ya tiene resultado registrado, el `tick` no envía nada (FR-029).
  - Si `FakeNotifier` devuelve `False` en el mensaje final, el dispatch queda en `sent` con `delivered=0` y el siguiente `tick` no lo reenvía (SC-002).

### Implementation for User Story 4

- [X] T052 [US4] Implementar `app/domain/daily_message.py`:
  - `apply_fatigue(blocks, title, fatigue) -> (blocks, type_label, title, kept_easy: bool)`: con fatiga ≥ 8, una sesión de calidad pasa por `to_easy` y queda con el tipo "suave/recuperación" y el título `EASY_TITLE`; una suave conserva sus bloques y devuelve `kept_easy=True`.
  - `render_sequence(blocks) -> str`, con el formato de `contracts/telegram-bot.md` (`"trote 1,00 km a 5:45 min/km (5:45), recuperación 2:00; caminata 0,50 km"`).
  - `build_message_data(session, profile, fatigue, weather: WeatherAssessment|None, weather_unavailable: bool) -> DailyMessageData` (importado de `app.domain.models`, nunca de `app.ai`). El rango sugerido es el rango preferido (R-17). Los campos de clima quedan en `None` hasta US5.
  - `render_template(data) -> str`, que garantiza ≤ 150 palabras porque la secuencia se trunca y se resume como "y n bloques más" si hace falta.
  - `required_fragments(data) -> list[str]` y `allowed_numbers(data) -> set[str]`, que toman los números de `render_template(data)` normalizados (coma/punto, `m:ss`).
  - `validate_draft(text, data) -> bool`, con las 6 reglas de R-17.
  - Las constantes `FATIGUE_QUESTION` y `FATIGUE_RETRY`, con los textos del contrato.
- [X] T053 [US4] Agregar a `app/ai/prompts.py` las constantes `MESSAGE_SYSTEM_PROMPT` (con las reglas de "Mensaje diario" de `contracts/ai-module.md`, incluida la prohibición explícita de dar consejo médico o de lesiones, FR-033) y `build_message_prompt(data: DailyMessageData)`. En `app/ai/gemini.py`, implementar `async draft_daily_message(data) -> str` con un timeout de 5 s y el mismo mapeo de errores y `audit.event("llm_call", operation="daily_message", …)` que en T044, y exportarla en `app/ai/__init__.py`. En `create_app`, inyectarla como `writer` por defecto; si se usa, el `lifespan` llama a `config.google_api_key()` al arrancar (principio II).
- [X] T054 [US4] Agregar a `app/services/repository.py`:
  - `get_session_for_user_on(conn, user_id, date)`, que devuelve la sesión con sus bloques.
  - `users_due_for_dispatch(conn, today, now_min)`: usuarios con un vínculo, `send_time_min <= now_min`, una sesión `today` sin resultado registrado y sin un `daily_dispatch` para `today` (FR-029).
  - `create_dispatch`, `get_open_dispatch_by_chat(conn, chat_id, today)`, `set_dispatch_sent(conn, id, fatigue, used_template, delivered, now)` y `expired_dispatches(conn, cutoff_iso)`.
- [X] T055 [US4] Implementar `app/services/daily_service.py`:
  - `async start_dispatches(conn, clock, notifier, weather)`: para cada usuario debido, crea un dispatch `awaiting_fatigue` con `asked_at=now`, emite `audit.event("tool_call", tool="db", op="create_dispatch")` y envía `FATIGUE_QUESTION`. El hook de clima queda preparado con `weather=None`, que significa sin evaluación, y se completa en US5.
  - `async handle_fatigue_reply(conn, clock, notifier, writer, chat_id, text) -> str|None`: si no hay un dispatch abierto o pasaron 2 h desde `asked_at`, devuelve `None`. Si el texto no es un entero de 1 a 10, devuelve `FATIGUE_RETRY`. Si es válido, llama a `compose_and_send`, que envía el mensaje por el `notifier`, y devuelve `None`. Solo devuelve texto (`FATIGUE_RETRY`) cuando el adaptador tiene que responder.
  - `async expire_waits(conn, clock, notifier, writer)`: envía sin ajuste los dispatches con `asked_at <= now-2h`.
  - `async compose_and_send(...)`: llama a `build_message_data`, intenta `asyncio.wait_for(writer(data), 5)` con `validate_draft` y, si falla o se pasa del tiempo (se trata como `AIUnavailableError("timeout")`), usa `render_template`; después llama a `notifier.send_message` y a `set_dispatch_sent` con `delivered` igual al booleano devuelto, emite `audit.event("tool_call", tool="db", op="set_dispatch_sent")`, y emite `audit.event("message_sent", template=…, user_id=…, delivered=…)`. No hay reintentos. El ajuste por fatiga no modifica la sesión guardada (FR-030).
- [X] T056 [US4] Agregar a `app/bot/handlers.py` el núcleo `async handle_text(conn, clock, notifier, writer, chat_id, text) -> str|None`, que delega en `handle_fatigue_reply`, y su adaptador `MessageHandler(filters.TEXT & ~filters.COMMAND)`, que responde solo si el resultado no es `None`.
- [X] T057 [US4] Extender `scheduler.tick` en `app/scheduler.py` para que, después de `run_monday`, llame a `daily_service.start_dispatches` y a `daily_service.expire_waits`. Ejecutar `uv run pytest tests/unit/test_daily_message.py tests/integration/test_daily_flow.py`.

**Checkpoint**: las 4 historias P1 (US1 a US4) están completas. Este es el MVP del producto.

---

## Phase 7: User Story 5 - Adaptar la sesión al clima (Priority: P2)

**Goal**: evaluar el pronóstico a la hora de envío y, según el caso, alertar, sugerir un día alternativo o posponer la sesión; si el servicio falla, seguir sin ajuste (FR-034..FR-039).

**Independent Test**: con `FakeWeather`, simular lluvia > 60%, temperatura > 32 °C, una condición extrema con y sin alternativa y una falla del servicio, y verificar los mensajes y los estados (AC-12, AC-13, AC-23, AC-24, AC-40..AC-43, AC-64, AC-68).

### Tests for User Story 5 ⚠️

- [X] T058 [P] [US5] Escribir `tests/unit/test_weather_rules.py`:
  - `day_conditions`: toma el máximo de los intervalos de 3 h que se solapan con el rango; un intervalo 06:00–09:00 se solapa con un rango 08:00–10:00 y uno 10:00–13:00 no.
  - Umbrales con valores justo en el límite y apenas por encima: pop 60/61, temperatura 32/32,1, temperatura 38/38,1 y pop 80/81; además, tormenta con id 211.
  - La alternativa es el primer día de los 3 siguientes sin condición desfavorable, nunca después del domingo; un día sin datos de pronóstico no puede ser alternativa.
  - Se pospone si la condición es extrema y no hay alternativa; si es extrema pero hay alternativa, solo se alerta.
  - Texto de los motivos según el contrato (`"lluvia probable (70%)"`, `"calor extremo (35 °C)"`, `"tormenta eléctrica"`, unidos con " y ").
- [X] T059 [P] [US5] Escribir `tests/integration/test_weather_flow.py`:
  - Con lluvia de 70%, el mensaje incluye la alerta y el día alternativo, la pregunta de fatiga se sigue enviando y la sesión no cambia de estado (AC-23, AC-24, FR-036).
  - Sin alternativa, el mensaje dice "No hay una alternativa disponible esta semana" y la sesión sigue ejecutable (AC-64).
  - Con una condición extrema sin alternativa, `system_status='postponed_weather'`, se envía un único mensaje de posposición de ≤ 150 palabras, no se pregunta la fatiga y el dispatch queda `postponed_sent` (AC-40, AC-68).
  - Con una segunda sesión pospuesta en la misma semana, el mensaje informa "2 sesiones" (AC-43).
  - Si `FakeWeather` lanza `WeatherUnavailableError`, se registra el evento `external_error` y el mensaje incluye el texto exacto de clima no disponible (AC-12, AC-13).
  - Si se cambia la ciudad con `PUT /profile`, la siguiente consulta usa la ciudad nueva (AC-71).

### Implementation for User Story 5

- [X] T060 [P] [US5] Implementar `app/integrations/openweather.py`:
  - `@dataclass Slot(start: datetime, pop_pct: int, temp_c: float, thunderstorm: bool)`, `@dataclass Forecast(slots: list[Slot])` y `class WeatherUnavailableError(Exception)` con `reason`.
  - `async fetch_forecast(city: str) -> Forecast`: usa `httpx.AsyncClient(timeout=5)` para `GET https://api.openweathermap.org/data/2.5/forecast` con `params={"q": f"{city},AR", "units": "metric", "appid": config.openweather_api_key()}`. Convierte `dt` (UTC) a la TZ de Buenos Aires, `pop*100` a entero y marca `thunderstorm` si algún `weather.id` está entre 200 y 232.
  - Timeout, 429, 5xx, 404, error de red y JSON inválido se traducen a `WeatherUnavailableError(reason)`.
  - Emitir `audit.event("tool_call", tool="weather", city=…, outcome=…)`. La `appid` nunca se registra.
- [X] T061 [P] [US5] Implementar `app/domain/weather_rules.py` (R-04, FR-035, FR-037):
  - `day_conditions(forecast_slots, day, range_start_min, range_end_min) -> DayConditions|None` (`max_pop`, `max_temp`, `thunder`), que devuelve `None` si no hay intervalos que se solapen con el rango.
  - `is_unfavorable(c)`: pop > 60 o temperatura > 32. `is_extreme(c)`: temperatura > 38, tormenta o pop > 80.
  - `reasons_text(c) -> str`.
  - `assess(forecast_slots, session_date, range_start_min, range_end_min) -> WeatherAssessment`, que busca la alternativa en `session_date+1..min(+3, domingo)`.
  - Las constantes `NO_ALTERNATIVE_TEXT = "No hay una alternativa disponible esta semana"` y `WEATHER_UNAVAILABLE_TEXT = "Clima no disponible: seguí las pautas base de ritmo e hidratación."`, y `postponement_message(reason, count_week) -> str`, con el texto del contrato.
- [X] T062 [US5] Agregar a `app/services/repository.py` las funciones `set_session_postponed(conn, session_id, reason)`, `count_postponed_in_week(conn, user_id, week_start)`, `set_dispatch_weather(conn, dispatch_id, weather_json)` y `create_dispatch(..., state="postponed_sent")`, esta última aceptando el estado y `delivered` como parámetros.
- [X] T063 [US5] Extender `app/services/daily_service.py`:
  - En `start_dispatches`, antes de preguntar la fatiga, llamar a `weather.fetch_forecast(profile.city)`, que usa la ciudad vigente (AC-71).
    - Si falla, registrar `audit.event("external_error", service="openweather", reason=…)` y guardar `weather_json={"available": false}`.
    - Si responde, llamar a `assess` y emitir `audit.event("weather_decision", unfavorable, extreme, alternative, postpone)`.
    - Si `postpone`, ejecutar `set_session_postponed` y emitir `audit.event("tool_call", tool="db", op="set_session_postponed")` y `audit.event("session_postponed", …)`, enviar `postponement_message(reason, count)`, crear el dispatch `postponed_sent` con `delivered` igual al booleano que devuelve el envío (con `audit.event("tool_call", tool="db", op="create_dispatch")`) y no preguntar la fatiga (FR-038).
    - Si no se pospone, guardar `weather_json` en el dispatch y preguntar la fatiga.
  - En `compose_and_send`, reconstruir el `WeatherAssessment` desde `weather_json` y pasarlo a `build_message_data`.
  - En `users_due_for_dispatch`, filtrar las sesiones con `system_status` no nulo.
- [X] T064 [US5] Completar los campos de clima de `build_message_data` en `app/domain/daily_message.py`: `weather_alert = "Alerta climática: {motivos}."`, `alternative_day = weekday_es(alt)` (en `render_template` se escribe como `"Día alternativo: {día}."`), `no_alternative_text` y `weather_unavailable_text`. Agregar estos campos a `required_fragments` y `allowed_numbers`. Inyectar `app.integrations.openweather` como `weather` por defecto en `create_app` de `app/main.py`; si se usa, el `lifespan` llama a `config.openweather_api_key()` al arrancar (principio II). Ejecutar `uv run pytest tests/unit/test_weather_rules.py tests/integration/test_weather_flow.py tests/integration/test_daily_flow.py`.

**Checkpoint**: US5 funciona sobre el flujo diario de US4.

---

## Phase 8: User Story 6 - Registrar cómo salió la sesión (Priority: P2)

**Goal**: registrar el resultado de la sesión del día (Completada, Parcial/Cortada o Salteada, con RPE y notas) por la API y por el bot. Una Parcial/Cortada con RPE ≥ 7 reclasifica las 2 sesiones siguientes (FR-040..FR-042, FR-044).

**Independent Test**: con una sesión hoy, registrar cada estado con y sin RPE o notas, y probar los rechazos (409, 422, 403) y la reclasificación inmediata y pendiente (AC-29..AC-34, AC-37..AC-39, AC-41, AC-69, AC-81).

### Tests for User Story 6 ⚠️

- [X] T065 [P] [US6] Escribir `tests/integration/test_results.py`:
  - Un registro `completed` con RPE 6 da 201, con y sin notas (AC-29, AC-34). Un `skipped` sin RPE da 201 (AC-30).
  - Dan 422: `completed` sin RPE (AC-31), RPE 0 u 11 (AC-32), `skipped` con RPE, una sesión de ayer o de mañana (AC-69) y una sesión `postponed_weather`, que además conserva su estado (AC-81, AC-41).
  - Un segundo registro da 409 y no cambia el primero (AC-33).
  - Un `partial` con RPE 7 el jueves, con sesiones el sábado y el domingo, con la del sábado de calidad y la del domingo suave con caminata/trote: la del sábado queda con un único bloque de trote sin ritmo, la del domingo conserva sus bloques, y ambas tienen `reclassified=1` (AC-39).
  - Un `partial` con RPE 7 el sábado, con una sola sesión restante, la convierte y deja `pending_reclassifications.remaining=1`. El plan siguiente generado convierte su primera sesión y consume la fila (FR-042).
  - Un `partial` con RPE 6 no reclasifica.
  - `/registrar` por el núcleo del bot: `handle_registrar(conn, clock, chat_id, ["completada","6","buenas","piernas"])` da el texto de éxito y `["completada"]` da el texto de RPE.
- [X] T066 [P] [US6] Escribir `tests/integration/test_isolation.py`:
  - El usuario B hace `POST /sessions/{id de A}/result` y recibe 403 con `{"detail": "Acceso denegado"}`, sin ningún dato de A, y el registro de A no cambia (AC-37).
  - Un `session_id` inexistente da 404.
  - Con el chat de B, `/registrar` solo afecta la sesión de B, y si B no tiene sesión hoy responde "No tenés una sesión planificada para hoy." sin tocar la de A (AC-38).
  - `GET /profile`, `/schedule` y `/history` con el token de B nunca devuelven datos de A. Estos endpoints se completan en US7: marcar con `pytest.mark.skipif` hasta que existan.

### Implementation for User Story 6

- [X] T067 [P] [US6] Implementar `app/domain/reclassification.py` con `targets_after(session_date, upcoming_sessions: list[(id, date)]) -> (ids_to_convert: list[int], remaining_pending: int)`. Toma las 2 primeras sesiones con fecha mayor a `session_date`, y `remaining_pending = 2 - len(ids)` si no alcanzan. Las sesiones pospuestas no cuentan como objetivo.
- [X] T068 [US6] Agregar a `app/services/repository.py`:
  - `get_session(conn, session_id)` y `get_result(conn, session_id)`.
  - `insert_result(conn, session_id, user_id, status, rpe, notes, now)`.
  - `upcoming_sessions(conn, user_id, after_date)`, que solo devuelve las sesiones de planes ya existentes.
  - `replace_session_blocks(conn, session_id, blocks, title, reclassified=True)`.
  - `upsert_pending_reclass(conn, user_id, remaining)`, que se queda con el máximo entre el valor existente y el nuevo.
- [X] T069 [US6] Implementar `app/services/results.py` con `register_result(conn, user_id, session_id, status, rpe, notes, today, clock) -> dict`.
  - Valida en el orden del contrato y lanza `SessionNotFound`, `Forbidden`, `PostponedSession`, `NotToday`, `AlreadyRegistered` o `InvalidRpe`.
  - Dentro de `transaction`, inserta el resultado. Si es `partial` con RPE ≥ 7, llama a `targets_after`, ejecuta `replace_session_blocks(reclassify(blocks))` (las suaves conservan sus bloques y su título; solo se marca `reclassified=1`; las de calidad convertidas pasan a `title = EASY_TITLE`) y `upsert_pending_reclass`, y emite `audit.event("guardrail", rule="reclassification", before, after)`. Siempre emite `audit.event("tool_call", tool="db", op="register_result")`.
  - Devuelve `{session_id, status, rpe, notes, reclassified_sessions, pending_reclassification}`.
- [X] T070 [US6] Implementar en `app/api/sessions.py` el endpoint `POST /sessions/{session_id}/result` con un body pydantic: `status: Literal["completed","partial","skipped"]`, `rpe: int|None` entre 1 y 10, y `notes: str|None` de hasta 500 caracteres. Un `model_validator` exige `rpe` si el estado es `completed` o `partial` y lo prohíbe si es `skipped`. Mapear las excepciones a 404, 403, 422, 422, 409 y 422 con los `detail` exactos del contrato y responder 201 si todo sale bien. Registrar el router en `app/main.py`.
- [X] T071 [US6] Agregar a `app/bot/handlers.py` el núcleo `async handle_registrar(conn, clock, chat_id, args) -> str` y su `CommandHandler("registrar")`. El núcleo resuelve el usuario por chat y la sesión de hoy, parsea el estado (`completada`, `parcial` o `salteada`), el RPE y las notas, y llama a `register_result`. Mapea cada excepción al texto de `contracts/telegram-bot.md` y no expone ids ni datos de otros usuarios (R-08). Ejecutar `uv run pytest tests/integration/test_results.py tests/integration/test_isolation.py`.

**Checkpoint**: US6 funciona. La reclasificación se integra con el plan siguiente de US3.

---

## Phase 9: User Story 7 - Ver el cronograma de la semana y el historial (Priority: P3)

**Goal**: `GET /schedule` y `GET /history`, con los estados de R-19 (FR-043).

**Independent Test**: con un plan que tiene sesiones registradas, sin registrar, pospuestas y futuras, consultar ambos endpoints y verificar los estados, el RPE y las notas (AC-35, AC-36).

### Tests for User Story 7 ⚠️

- [X] T072 [P] [US7] Escribir `tests/integration/test_schedule_history.py`. Usar un plan de lunes a domingo, con hoy jueves:
  - En `GET /schedule`: la sesión del lunes, registrada, aparece "Completada" con RPE y notas; la del martes, sin registro, "Sin registrar"; la del miércoles, pospuesta, "Pospuesta por clima"; la de hoy, "Hoy"; y la del sábado, "Proyectada" (AC-35).
  - Sin un plan para la semana, `GET /schedule` da 404 con el mensaje exacto.
  - `GET /history` incluye las sesiones de semanas anteriores y las pasadas, más la de hoy solo si ya tiene un registro, ordenadas por fecha descendente y con `rpe` y `notes` en `null` cuando no existen (AC-36, AC-29).
  - Quitar el `skipif` de `tests/integration/test_isolation.py`.

### Implementation for User Story 7

- [X] T073 [US7] Agregar a `app/services/repository.py` las funciones `sessions_with_results_for_week(conn, user_id, week_start)` y `history_sessions(conn, user_id, today)`. La segunda devuelve las sesiones con `date < today` o con un resultado, unidas a `session_results` con `LEFT JOIN`, ordenadas por `date DESC`.
- [X] T074 [US7] Agregar a `app/services/plan_service.py` la función `serialize_history_item(row, today) -> dict` con la forma `HistoryItem` del contrato, que reutiliza `status_label` (T046).
- [X] T075 [US7] Implementar `GET /schedule` en `app/api/plan.py` (200 con `serialize_plan` más `result` por sesión, o 404 con "No tenés un plan para la semana en curso") y `GET /history` en `app/api/sessions.py` (200 con `{"sessions": [...]}`). Ambos dependen de `get_current_user`. Ejecutar `uv run pytest tests/integration/test_schedule_history.py tests/integration/test_isolation.py`.

**Checkpoint**: US7 funciona.

---

## Phase 10: User Story 8 - Administrar la cuenta (Priority: P3)

**Goal**: restablecer la contraseña con un código enviado por el bot, eliminar la cuenta con confirmación y garantizar cuándo se aplican los cambios de perfil (FR-007, FR-009, FR-010).

**Independent Test**: restablecer la contraseña con un código válido, vencido y reutilizado; eliminar la cuenta con y sin `confirm=true`; editar el perfil con un plan vigente (AC-49, AC-50, AC-52, AC-53, AC-70, AC-71).

### Tests for User Story 8 ⚠️

- [ ] T076 [P] [US8] Escribir `tests/integration/test_account_admin.py`:
  - `handle_restablecer` desde un chat vinculado devuelve un texto con un código de 10 caracteres. `POST /auth/password-reset` con ese código y una contraseña nueva da 200, el login con la contraseña nueva da 200 y con la vieja da 401 (AC-49).
  - Reusar el código da 400. Un código con 30 min 1 s da 400 y uno inexistente también, sin cambiar el hash. Con una contraseña de 7 caracteres da 422 y el código sigue sin consumirse (AC-50).
  - `/restablecer` desde un chat no vinculado devuelve el texto del contrato.
  - `DELETE /profile` sin `confirm` o con `confirm=yes` da 400 con la advertencia exacta y no borra nada (AC-52).
  - `DELETE /profile?confirm=true` da 204. Las tablas `users`, `profiles`, `plans`, `sessions`, `blocks`, `session_results`, `telegram_links` y `one_time_codes` quedan sin filas del usuario. El login da 401 y el token anterior da 401 (AC-53).
  - `PUT /profile` con una frecuencia nueva, con un plan vigente, no cambia las sesiones guardadas, y el próximo `build_and_save_plan` usa la frecuencia nueva (AC-70).

### Implementation for User Story 8

- [ ] T077 [US8] Agregar a `app/services/repository.py` las funciones `update_password_hash(conn, user_id, hash)` y `delete_user(conn, user_id)`. Esta última es un `DELETE FROM users WHERE id=?` que borra todo en cascada; verificar que `PRAGMA foreign_keys=ON` está activo en la conexión.
- [ ] T078 [US8] Agregar a `app/services/accounts.py` las funciones:
  - `create_reset_code(conn, user_id, clock) -> str`: 10 caracteres y vence en 30 min. Emite `audit.event("tool_call", tool="db", op="create_reset_code")` sin el código.
  - `reset_password(conn, code, new_password, clock)`: dentro de `transaction`, ejecuta `consume_code(purpose="reset")` y `update_password_hash`, y lanza `InvalidResetCode` si el código no es válido. Emite `audit.event("tool_call", tool="db", op="reset_password", outcome=…)` sin el código.
  - `delete_account(conn, user_id)`, que emite `audit.event("tool_call", tool="db", op="delete_account")`.
- [ ] T079 [US8] Implementar `POST /auth/password-reset` en `app/api/auth.py`. El body es `{code: str, new_password: str}`, con `new_password` de 8 a 128 caracteres; la validación de pydantic va antes de consumir el código. Responde 200 con `{"detail": "Contraseña actualizada"}` o 400 con `{"detail": "Código inválido o vencido"}`.
- [ ] T080 [US8] Implementar `DELETE /profile` en `app/api/profile.py`, con `confirm: str | None = Query(None)`. Si `confirm != "true"`, responde 400 con la advertencia exacta del contrato. Si es `"true"`, llama a `delete_account` y devuelve `Response(status_code=204)`. No debe enviar el header `X-Session-Token`: borrarlo de la respuesta en este endpoint.
- [ ] T081 [US8] Agregar a `app/bot/handlers.py` el núcleo `async handle_restablecer(conn, clock, chat_id) -> str` y su `CommandHandler("restablecer")`, con los textos del contrato. Ejecutar `uv run pytest tests/integration/test_account_admin.py`.

**Checkpoint**: las 8 historias funcionan.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: contrato de la API, auditoría, secretos, rendimiento y validación final.

- [ ] T082 [P] Escribir `tests/contract/test_api_contract.py`. Para cada endpoint de `contracts/api.md`, verificar el código de estado y las claves exactas del cuerpo de éxito (`Profile`, `Plan`, `HistoryItem`, `{access_token, token_type, expires_at}`, `{code, expires_at, instructions}`), los `detail` literales de los mensajes fijos y la presencia de `X-Session-Token` en las respuestas autenticadas (salvo en el 204 de DELETE).
- [ ] T083 [P] Escribir `tests/unit/test_audit.py` con `caplog` sobre `runia.audit`:
  - `redact` oculta `password`, `access_token`, `api_key`, `code` y `Authorization`, también anidados.
  - Recorrer los flujos de `POST /plan` (con un recorte), el dispatch diario (con una falla de clima y una posposición) y el registro con reclasificación, y verificar que se emiten `llm_call`, `tool_call` (con `tool="db"` y cada `op` de la lista cerrada de R-18; para eso recorrer también registro, login, edición del perfil, vinculación, reseteo de contraseña, fallback del lunes y borrado de cuenta), `guardrail` (con `before` y `after`), `session_postponed`, `external_error` y `weather_decision` (FR-045).
  - Ninguna línea de log de **ningún** logger (todos los registros de `caplog`, no solo `runia.audit`) contiene la contraseña, el JWT, `TELEGRAM_BOT_TOKEN` ni `OPENWEATHER_API_KEY` usados en el test (SC-008). Incluye un flujo de clima con el cliente real de `app/integrations/openweather.py` sobre un transporte httpx mockeado, con `caplog.set_level(logging.DEBUG)` después de `configure_logging()`.
- [ ] T084 [P] Escribir `tests/unit/test_constitution.py`:
  - Recorrer `app/**/*.py` y verificar que `google.genai` o `from google import genai` solo aparecen en `app/ai/gemini.py` (principio I).
  - Verificar que `app/domain/*.py` no importa `app.services`, `app.ai`, `app.integrations` ni `app.db`.
  - Verificar que los archivos versionados (`git ls-files`) no contienen patrones de credenciales (`AIza[0-9A-Za-z_-]{20,}` y `\d{8,10}:[A-Za-z0-9_-]{35}`) y que `.env` está ignorado (principio II, SC-009).
  - Verificar que `PLAN_SYSTEM_PROMPT` y `MESSAGE_SYSTEM_PROMPT` de `app/ai/prompts.py` contienen la prohibición de consejo médico y de lesiones, que `PLAN_SYSTEM_PROMPT` pide la entrada en calor y la vuelta a la calma como bloques explícitos (FR-019), y que `build_plan_prompt` y `build_message_prompt` no incluyen email ni chat_id (FR-033, FR-028).
- [ ] T085 [P] Escribir `tests/integration/test_performance.py` (SC-004, RNF-01). Con 10 usuarios en `awaiting_fatigue`, un `FakeWriter` con 1 s de latencia y un `FakeNotifier` con 0,2 s, lanzar 10 llamadas a `handle_fatigue_reply` con `asyncio.gather` y verificar que el p95 de las duraciones es de 10 s o menos. Agregar un caso con un `FakeWriter` que tarda 6 s: el timeout de 5 s activa la plantilla y el total queda por debajo de 10 s. Agregar un caso que verifique `build_application("123:dummy", state).concurrent_updates > 1` (no usa red: `build()` no llama a Telegram).
- [ ] T086 Actualizar `AGENTS.md` en la sección "Cómo correr": agregar `RUNIA_DB_PATH`, que es opcional y no es un secreto (por defecto `runia.db`), y los comandos del bot (`/vincular`, `/registrar`, `/restablecer`). No modificar el resto del archivo.
- [ ] T087 Ejecutar `uv run pytest` completo y corregir los fallos. Después, seguir `specs/001-runia-training-plans/quickstart.md`, pasos 1 a 3 (tests, verificación de secretos y arranque con y sin `TELEGRAM_BOT_TOKEN`), y registrar en el PR cualquier desvío que se encuentre.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no tiene dependencias.
- **Foundational (Phase 2)**: depende de Setup y **bloquea todas las historias**.
- **US1 (Phase 3)**: depende de Foundational.
- **US2 (Phase 4)**: depende de Foundational. Usa `get_current_user` y las cuentas de US1 para emitir el código, así que en la práctica va después de US1.
- **US3 (Phase 5)**: depende de US1 (perfil) y US2 (vínculo, por FR-012). Sus tests siembran el perfil y el vínculo directamente en la DB, así que se pueden escribir en paralelo.
- **US4 (Phase 6)**: depende de US3 (necesita planes y sesiones guardados con `save_plan`) y de US2 (bot y notifier).
- **US5 (Phase 7)**: depende de US4, porque extiende `daily_service`.
- **US6 (Phase 8)**: depende de US3 (sesiones) y US2 (bot). Es independiente de US4 y US5.
- **US7 (Phase 9)**: depende de US3. Si se hace antes de US6, los estados registrados se testean sembrando `session_results` directamente.
- **US8 (Phase 10)**: depende de US1 y US2. Es independiente de US3 a US7, salvo el test de AC-70, que usa `build_and_save_plan` de US3.
- **Polish (Phase 11)**: depende de todas las historias.

### Grafo de historias

```text
Setup → Foundational → US1 → US2 ─┬─→ US3 ─┬─→ US4 → US5
                                  │        ├─→ US6
                                  │        └─→ US7
                                  └─→ US8
```

### Within Each User Story

- Tests primero; fallan hasta que se implementa la historia y se cierran en su checkpoint.
- `domain/`, que tiene funciones puras.
- `repository`.
- `services`.
- `api` y `bot`.
- Registro en `main.py` y `scheduler.py`.
- Ejecución de los tests de la historia.

### Parallel Opportunities

- **Foundational**: T004, T005, T006, T007, T008, T010, T011 y T012 en paralelo. T009 y T013 a T016 van en secuencia (T013 depende de T009; T015 depende de T009, T011 y T013; T016 depende de T015).
- **US1**: T018, T019 y T020 en paralelo.
- **US3**: los tests T032 a T036 y T088 en paralelo. T038, T039 y T043 en paralelo entre sí. T040, T041 y T042 en secuencia (mismo archivo).
- **US5**: T058, T059, T060 y T061 en paralelo.
- **US6**: T065, T066 y T067 en paralelo.
- Después de US3, **US6, US7 y US4** pueden avanzar en paralelo con personas distintas, salvo las funciones que agregan a `repository.py`, `api/plan.py`, `api/sessions.py` y `bot/handlers.py`, que van en secuencia o coordinadas.
- **Polish**: T082 a T085 en paralelo.

---

## Parallel Example: User Story 3

```bash
# Tests de US3, todos juntos:
Task: "T032 tests/unit/test_structure.py"
Task: "T033 tests/unit/test_summaries.py"
Task: "T034 tests/unit/test_guardrails.py"
Task: "T035 tests/integration/test_plan_api.py"
Task: "T036 tests/integration/test_weekly_job.py"
Task: "T088 tests/sc001_check.py + tests/unit/test_sc001.py + tests/integration/test_sc001_delivered.py"

# Módulos puros en paralelo:
Task: "T038 app/domain/structure.py"
Task: "T039 app/domain/summaries.py"
Task: "T043 app/ai/prompts.py"
```

## Parallel Example: User Story 5

```bash
Task: "T058 tests/unit/test_weather_rules.py"
Task: "T059 tests/integration/test_weather_flow.py"
Task: "T060 app/integrations/openweather.py"
Task: "T061 app/domain/weather_rules.py"
```

## Parallel Example: User Story 6

```bash
Task: "T065 tests/integration/test_results.py"
Task: "T066 tests/integration/test_isolation.py"
Task: "T067 app/domain/reclassification.py"
```

---

## Implementation Strategy

### MVP First (US1)

1. Phase 1 (Setup) y Phase 2 (Foundational).
2. Phase 3 (US1): cuenta, login y perfil.
3. **STOP and VALIDATE**: `uv run pytest` y los pasos 4.1 a 4.3 de `quickstart.md`.

El MVP **de producto**, el que da valor al corredor, es US1 a US4, las cuatro P1: un plan seguro y el mensaje diario por Telegram.

### Incremental Delivery

1. Setup + Foundational: la base está lista.
2. US1: cuentas y perfil. Validar.
3. US2: vínculo con Telegram. Validar `/vincular` contra un bot real.
4. US3: planes con guardarraíles. Validar SC-001 con el verificador de T088 (`test_sc001.py` y `test_sc001_delivered.py`).
5. US4: mensaje diario. Con esto queda el MVP de producto.
6. US5: clima. US6: registro, que activa la descarga y la calidad de novatos con datos reales.
7. US7: cronograma e historial. US8: administración de la cuenta.
8. Polish: contrato, auditoría, constitución, rendimiento y quickstart.

### Notas

- [P] significa archivos distintos y sin dependencias pendientes.
- Cada checkpoint de historia termina con `uv run pytest` en verde (constitución). Ninguna tarea de la fase se marca `[x]` antes de ese checkpoint; al pasar, se marcan todas juntas.
- No agregar endpoints, comandos ni dependencias que no estén en `contracts/` o en R-01 (principio III).
- Quedan fuera de esta iteración RF-20/AC-54 (cambio de nivel restringido) y AC-25/AC-26 (confirmación y reprogramación por clima).
