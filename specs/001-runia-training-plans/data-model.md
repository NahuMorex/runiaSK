# Data Model: Runia — Planes de entrenamiento para running

**Fase**: 1 · **Fecha**: 2026-10-15 · **Plan**: [plan.md](./plan.md) · **Decisiones**: [research.md](./research.md)

SQLite con `sqlite3` de la stdlib. El schema se crea con `CREATE TABLE IF NOT EXISTS` en `app/db.py::init_db`.
Cada conexión ejecuta `PRAGMA foreign_keys = ON` y `PRAGMA journal_mode = WAL`.

**Convenciones**:

- `*_hm`: distancia en **centésimas de km**, como entero (R-07). Por ejemplo, 2,35 km se guarda como `235`.
- `*_s`: segundos, como entero. El ritmo se guarda en s/km.
- `*_min`: minutos desde las 00:00, como entero (horarios HH:MM en Buenos Aires).
- Fechas: texto ISO `YYYY-MM-DD` en Buenos Aires. Instantes: texto ISO 8601 con offset `-03:00`.
- Booleanos: `INTEGER` 0/1.
- Todas las tablas hijas de `users` usan `ON DELETE CASCADE`, así que el borrado de cuenta (FR-009) es un solo `DELETE FROM users`.

---

## users — Usuario (FR-001, FR-004, FR-009)

| Columna | Tipo | Reglas |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| email | TEXT NOT NULL UNIQUE | Normalizado a minúsculas; formato validado con `EmailStr` (AC-72) |
| password_hash | TEXT NOT NULL | Argon2id, m=19456, t=2, p=1 (RNF-03) |
| created_at | TEXT NOT NULL | |

## profiles — Perfil (FR-005..FR-008, FR-012)

Un perfil por usuario. Se crea vacío (todo NULL) al registrarse, así que `GET /profile` siempre devuelve 200.

| Columna | Tipo | Reglas |
|---|---|---|
| user_id | INTEGER PK FK→users | |
| level | TEXT NULL | `novato` \| `intermedio` \| `avanzado` |
| frequency | INTEGER NULL | 1..7 |
| target_distance_hm | INTEGER NULL | 100..4220 (1 a 42,2 km) |
| current_pace_s | INTEGER NULL | 180..600 (3:00 a 10:00); obligatorio para generar un plan si `level ≠ novato` |
| city | TEXT NULL | 1..100 caracteres después de `strip()` |
| range_start_min | INTEGER NULL | 0..1439 |
| range_end_min | INTEGER NULL | > range_start_min y diferencia ≥ 60 |
| send_time_min | INTEGER NULL | < range_end_min |
| updated_at | TEXT NOT NULL | |

**Completitud** (FR-012): para generar un plan se exigen `level`, `frequency`, `target_distance_hm`, `city`,
`range_*`, `send_time_min`, un vínculo de Telegram y, si `level ≠ novato`, `current_pace_s`. El orden en que se
verifican fija qué mensaje se devuelve: nivel → frecuencia → distancia objetivo → ritmo → ciudad → rango horario →
hora de envío → Telegram. El `{campo}` de AC-09 se completa con: `nivel`, `frecuencia`, `distancia objetivo`,
`ciudad`, `rango horario`, `hora de envío`.

## telegram_links — Vínculo de Telegram (FR-011)

| Columna | Tipo | Reglas |
|---|---|---|
| user_id | INTEGER PK FK→users | Una cuenta tiene un solo chat |
| chat_id | INTEGER NOT NULL UNIQUE | Un chat pertenece a una sola cuenta |
| linked_at | TEXT NOT NULL | |

Es permanente: no hay endpoint ni comando para desvincular (Fuera de Alcance).

## one_time_codes — Código de un solo uso (FR-010, FR-011)

| Columna | Tipo | Reglas |
|---|---|---|
| id | INTEGER PK | |
| user_id | INTEGER NOT NULL FK→users | |
| purpose | TEXT NOT NULL | `link` (15 min) \| `reset` (30 min) |
| code_hash | TEXT NOT NULL UNIQUE | SHA-256 hex del código (R-16) |
| expires_at | TEXT NOT NULL | |
| used_at | TEXT NULL | Se marca al usarse en la misma transacción que el efecto |

**Estados**: `vigente` → `usado` (cuando `used_at` deja de ser NULL), o `vigente` → `vencido` (cuando `now ≥ expires_at`).
Los dos son terminales.

## plans — Plan semanal (FR-013..FR-027)

| Columna | Tipo | Reglas |
|---|---|---|
| id | INTEGER PK | |
| user_id | INTEGER NOT NULL FK→users | |
| week_start | TEXT NOT NULL | Lunes de la semana; `UNIQUE(user_id, week_start)` (AC-58) |
| start_date | TEXT NOT NULL | Primer día que cubre el plan (lunes en un plan completo; día de generación en uno parcial) |
| is_full | INTEGER NOT NULL | 1 si `start_date == week_start` |
| is_deload | INTEGER NOT NULL | Semana de descarga (FR-021) |
| is_post_deload | INTEGER NOT NULL | Semana siguiente a una descarga (vuelve a V4) |
| source | TEXT NOT NULL | `on_demand` \| `monday` \| `fallback` |
| adopted_from_plan_id | INTEGER NULL FK→plans ON DELETE SET NULL | Solo cuando `source = fallback` |
| planned_volume_hm | INTEGER NOT NULL | Km de trote después de los guardarraíles; **no cambia nunca** (RF-06b) |
| profile_snapshot | TEXT NOT NULL | JSON `{level, frequency, target_distance_hm, current_pace_s}` (AC-66, R-11) |
| created_at | TEXT NOT NULL | |

## sessions — Sesión (FR-015, FR-016, FR-022, FR-037, FR-042)

| Columna | Tipo | Reglas |
|---|---|---|
| id | INTEGER PK | |
| plan_id | INTEGER NOT NULL FK→plans | `UNIQUE(plan_id, date)` |
| user_id | INTEGER NOT NULL FK→users | Copia del dueño del plan, para chequear propiedad rápido (AC-37) |
| date | TEXT NOT NULL | Dentro de `[plan.start_date, domingo]` |
| title | TEXT NOT NULL | Etiqueta corta propuesta por el modelo (p. ej. "Intervalos") |
| reclassified | INTEGER NOT NULL DEFAULT 0 | Convertida a suave por FR-042 |
| system_status | TEXT NULL | `postponed_weather` o NULL |
| postponed_reason | TEXT NULL | Motivo climático, cuando la sesión está pospuesta |

**Tipo derivado** (no se guarda): `quality` si algún bloque `run` tiene `target_pace_s`; si no, `easy` (R-12).

**Volumen de la sesión** (derivado): suma de `distance_hm` de los bloques `run`.

**Transiciones del estado del sistema**:
`NULL` → `postponed_weather` (FR-037, solo a la hora de envío del día de la sesión). Es terminal: no se puede registrar
ni volver atrás.

## blocks — Bloque / Tramo (FR-015, FR-024, FR-026)

| Columna | Tipo | Reglas |
|---|---|---|
| id | INTEGER PK | |
| session_id | INTEGER NOT NULL FK→sessions ON DELETE CASCADE | |
| position | INTEGER NOT NULL | 0..n-1; `UNIQUE(session_id, position)` |
| kind | TEXT NOT NULL | `walk` \| `run` |
| distance_hm | INTEGER NOT NULL | ≥ 0 (puede quedar en 0 después de un recorte, R-07); > 0 en la propuesta |
| target_pace_s | INTEGER NULL | Solo en `run`; si está presente, el bloque es un tramo de calidad |
| target_time_s | INTEGER NULL | `round_half_up(distance_hm × target_pace_s ÷ 100)`; lo calcula el sistema |
| recovery_after_s | INTEGER NULL | Recuperación posterior al tramo, en tiempo (≥ 0); no tiene km |

## session_results — Registro de resultado (FR-040, FR-041)

| Columna | Tipo | Reglas |
|---|---|---|
| session_id | INTEGER PK FK→sessions ON DELETE CASCADE | Un registro por sesión (AC-33) |
| user_id | INTEGER NOT NULL FK→users | |
| status | TEXT NOT NULL | `completed` \| `partial` \| `skipped` |
| rpe | INTEGER NULL | 1..10; obligatorio si el estado es `completed` o `partial`; NULL si es `skipped` |
| notes | TEXT NULL | Opcional, hasta 500 caracteres |
| recorded_at | TEXT NOT NULL | |

Solo se acepta si `sessions.date == hoy` (AC-69) y `system_status IS NULL` (AC-81). "Sin registrar" no se guarda:
es la ausencia de fila en una sesión pasada (AC-36).

Etiquetas para la API y el bot: `completed` → "Completada", `partial` → "Parcial/Cortada", `skipped` → "Salteada".

## pending_reclassifications — Reclasificación pendiente (FR-042)

| Columna | Tipo | Reglas |
|---|---|---|
| user_id | INTEGER PK FK→users | |
| remaining | INTEGER NOT NULL | 1 o 2; se borra la fila al consumirse |

Si hay un registro nuevo mientras existe un pendiente, se toma `max(remaining actual, faltantes nuevos)`.

## daily_dispatches — Envío diario (FR-029..FR-039)

Una fila por usuario y día con sesión. Es el estado del flujo de la hora de envío.

| Columna | Tipo | Reglas |
|---|---|---|
| id | INTEGER PK | |
| user_id | INTEGER NOT NULL FK→users | `UNIQUE(user_id, date)` |
| session_id | INTEGER NOT NULL FK→sessions | |
| date | TEXT NOT NULL | |
| state | TEXT NOT NULL | `awaiting_fatigue` \| `sent` \| `postponed_sent` |
| weather_json | TEXT NULL | Evaluación climática hecha a la hora de envío (alerta, motivo, alternativa, no disponible) |
| asked_at | TEXT NULL | Primera pregunta de fatiga (inicio de la ventana de 2 h, AC-75) |
| fatigue | INTEGER NULL | 1..10 |
| sent_at | TEXT NULL | Confirmación de entrega de Telegram |
| delivered | INTEGER NULL | 1 si Telegram confirmó el mensaje final o el aviso de posposición; 0 si falló (SC-002). Sin reintentos |
| used_template | INTEGER NULL | 1 si se envió la plantilla (AC-78, AC-79) |

**Transiciones**:

```text
(sin fila) ──hora de envío, extremo sin alternativa──▶ postponed_sent   (sesión → postponed_weather; mensaje AC-68)
(sin fila) ──hora de envío, otro caso──▶ awaiting_fatigue                 (pregunta de fatiga)
awaiting_fatigue ──respuesta 1..10 dentro de 2 h──▶ sent                  (mensaje con ajuste FR-030)
awaiting_fatigue ──respuesta inválida──▶ awaiting_fatigue                 (vuelve a preguntar; asked_at no cambia)
awaiting_fatigue ──now ≥ asked_at + 2 h──▶ sent                           (mensaje sin ajuste)
sent / postponed_sent: terminales (una respuesta tardía se ignora)
```

## weekly_generation_runs — Corrida del lunes (FR-014, R-03)

| Columna | Tipo | Reglas |
|---|---|---|
| user_id | INTEGER FK→users | PK compuesta `(user_id, week_start)` |
| week_start | TEXT | |
| outcome | TEXT NOT NULL | `generated` \| `fallback` \| `failed_no_previous` \| `skipped_existing` \| `skipped_incomplete` \| `error` |
| ran_at | TEXT NOT NULL | |

---

## Entidades de dominio sin tabla

- **WeekSummary** (`domain/summaries.py`): `week_start`, `has_plan`, `is_full`, `is_deload`, `planned_volume_hm`,
  `completed_count`, `has_partial_rpe7`, `profile_snapshot`. Se deriva de `plans`, `sessions` y `session_results`.
  Es lo único del historial que llega a `app/ai/`, y solo con los campos numéricos (FR-028).
- **GuardrailContext**: `level`, `frequency`, `target_distance_hm`, `current_pace_s`, `start_date`, `week_start`,
  `is_full`, `is_deload` (bool), `is_post_deload` (bool), `initial_caps` (bool), `base_10_hm | None`, `no_increase_hm | None`, `deload_v4_hm | None`,
  `post_deload_target_hm | None`, `floor_prev_hm | None`, `novice_quality_allowed`, `pending_reclass`.
  Lo construye `summaries.build_context(...)` según R-11.
- **GuardrailEvent**: `rule`, `scope` (`session` | `week`), `session_date`, `before`, `after`.
- **WeatherAssessment** (`domain/weather_rules.py`): `available`, `unfavorable`, `extreme`, `reasons[]`,
  `alternative_date | None`, `postpone` (bool).
- **DailyMessageData** (`domain/models.py`, pydantic; campos en [contracts/ai-module.md](./contracts/ai-module.md); `app/ai/schemas.py` lo reexporta).
- **Evento de auditoría**: no se guarda en SQLite; es una línea JSON en stdout (R-18).

## Relaciones

```text
users 1─1 profiles
users 1─0..1 telegram_links
users 1─* one_time_codes
users 1─* plans 1─* sessions 1─* blocks
sessions 1─0..1 session_results
sessions 1─0..1 daily_dispatches
users 1─0..1 pending_reclassifications
users 1─* weekly_generation_runs
```
