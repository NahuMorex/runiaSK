# Contrato: Módulo de IA (`app/ai/`)

**Principio I de la constitución**: este paquete es el único que importa `google-genai` y arma prompts. No accede a
SQLite, a Telegram ni al clima. El resto del sistema importa solo lo que expone `app/ai/__init__.py`.

## Interfaz pública

```python
# app/ai/__init__.py
from app.ai.schemas import PlanRequest, WeekPlanProposal, DailyMessageData
from app.ai.gemini import propose_week_plan, draft_daily_message, AIUnavailableError

async def propose_week_plan(req: PlanRequest) -> WeekPlanProposal: ...
    # Timeout de 20 s. Lanza AIUnavailableError(reason) ante una excepción del SDK, un timeout,
    # una respuesta vacía o un JSON que no valida contra WeekPlanProposal.

async def draft_daily_message(data: DailyMessageData) -> str: ...
    # Timeout de 5 s. Lanza AIUnavailableError(reason). No valida AC-78: eso lo hace domain/daily_message.py.
    # daily_service.compose_and_send también aplica asyncio.wait_for(…, 5), así el timeout vale con cualquier writer inyectado.

class AIUnavailableError(Exception):
    reason: str  # "timeout" | "rate_limit" | "server_error" | "invalid_response" | "invalid_structure" | "error"
                 # "invalid_structure": la propuesta no pasa validate_proposal (lo lanza plan_service)
```

Los servicios reciben estas funciones como dependencias inyectables (un protocolo `Planner` o `Writer`
en `app/services/`), así que los tests las reemplazan por dobles sin llamar al modelo (Flujo de desarrollo de la constitución).

Cada llamada emite `audit.event("llm_call", operation, prompt_summary, response_summary, duration_ms, outcome)`.
`app/audit.py` no depende de `services/` ni de `db`, así que importarlo desde `ai/` no rompe el principio I.

## Esquemas (pydantic v2)

```python
class WeekSummaryIn(BaseModel):          # FR-028: solo agregados, nunca sesiones individuales
    week_start: date
    is_full: bool
    is_deload: bool
    planned_volume_km: float
    completed_sessions: int
    partial_rpe7: bool

class PlanRequest(BaseModel):
    level: Literal["novato", "intermedio", "avanzado"]
    frequency: int                       # 1..7
    target_distance_km: float
    current_pace_s: int | None           # s/km
    week_start: date
    allowed_dates: list[date]            # días que puede usar el plan (desde start_date hasta el domingo)
    sessions_required: int               # FR-016
    first_week_novice: bool              # exige alternar caminata y trote (AC-14)
    quality_allowed: bool                # FR-022 (el pipeline lo vuelve a aplicar igual)
    target_volume_km: float | None       # orientación: tope semanal o 0,75×V4 en la descarga; no es vinculante
    max_session_km: float | None         # orientación: tope por sesión vigente
    is_deload: bool
    recent_weeks: list[WeekSummaryIn]    # hasta 4 semanas cerradas

class BlockOut(BaseModel):
    kind: Literal["walk", "run"]
    distance_km: float                   # > 0 (validado en domain/structure.py)
    target_pace_s: int | None = None     # solo en run; si está, el bloque es un tramo de calidad
    recovery_after_s: int | None = None  # recuperación en tiempo después del tramo

class SessionOut(BaseModel):
    date: date
    title: str                           # ≤ 40 caracteres
    blocks: list[BlockOut]

class WeekPlanProposal(BaseModel):
    sessions: list[SessionOut]

# Definido en app/domain/models.py (domain no puede importar app.ai) y reexportado acá:
# from app.domain.models import DailyMessageData
class DailyMessageData(BaseModel):       # datos ya decididos por el código determinista
    session_type_label: str              # "calidad" | "suave" | "suave/recuperación"
    title: str
    suggested_range: str                 # "07:00–09:00"
    target_pace: str | None              # "5:45 min/km"
    sequence: str | None                 # secuencia renderizada de caminata y trote o de tramos
    weather_alert: str | None            # "Alerta climática: lluvia probable (70%)."
    alternative_day: str | None          # "viernes"
    no_alternative_text: str | None      # "No hay una alternativa disponible esta semana"
    weather_unavailable_text: str | None # "Clima no disponible: seguí las pautas base de ritmo e hidratación."
    fatigue_kept_easy_text: str | None   # "La sesión se mantiene suave por la fatiga."
```

`WeekPlanProposal` se pasa como `response_schema` y la respuesta se parsea con `WeekPlanProposal.model_validate_json`.
Los tiempos objetivo **no** forman parte del esquema: los calcula el sistema (R-07).

## Reglas de los prompts (`app/ai/prompts.py`)

- **Plan**: sistema en español. Debe proponer exactamente `sessions_required` sesiones en fechas distintas de `allowed_dates`.
  En la primera semana de un novato, cada sesión alterna bloques `walk` y `run` con km. Un tramo con `target_pace_s` solo aparece
  si `quality_allowed`, y como máximo una sesión de calidad por semana. Cada tramo de calidad salvo el último lleva
  `recovery_after_s`. Debe respetar `max_session_km` y `target_volume_km` como orientación. No da consejo médico ni de lesiones.
- **Mensaje diario**: como máximo 120 palabras (margen frente al límite de 150), en texto plano, sin preguntas ni markdown,
  sin números distintos de los recibidos, con todos los campos no nulos de `DailyMessageData` escritos literalmente,
  y sin consejo médico ni de lesiones.
- Ningún prompt incluye datos de identificación (email, chat_id) ni historiales completos.
