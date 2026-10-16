"""Prompts del módulo de IA. Ningún prompt incluye email, chat_id ni historiales completos."""

from app.ai.schemas import DailyMessageData, PlanRequest

NO_MEDICAL_RULE = (
    "No des consejo médico ni de lesiones bajo ninguna circunstancia: no diagnostiques, no recomiendes "
    "tratamientos, medicación ni rehabilitación, y no opines sobre dolores o lesiones."
)

PLAN_SYSTEM_PROMPT = f"""Sos un entrenador de running que arma planes semanales para corredores en Argentina.
Respondé solo con JSON que respete el esquema pedido. Reglas:
- Proponé exactamente `sessions_required` sesiones, cada una en una fecha distinta tomada de `allowed_dates`.
- Cada sesión es una lista de bloques `walk` (caminata) o `run` (trote), cada uno con su distancia en km (> 0).
- Todo el trote va en bloques `run` con km. La entrada en calor y la vuelta a la calma, si las proponés, son bloques
  explícitos `run` (cuentan para el volumen) o `walk`; nunca km implícitos en el título ni en el texto.
- Si `first_week_novice` es verdadero, cada sesión alterna bloques `walk` y `run` (sin dos bloques seguidos del
  mismo tipo) y ningún bloque lleva `target_pace_s`.
- Un tramo con `target_pace_s` (segundos por km) solo puede aparecer si `quality_allowed` es verdadero, y como
  máximo en una sesión de la semana. Cada tramo con ritmo, salvo el último de la sesión, lleva `recovery_after_s`.
- Usá `max_session_km` y `target_volume_km` como orientación para la distancia de cada sesión y de la semana.
- Si `is_deload` es verdadero, la semana es de descarga: bajá la carga.
- `title` es una etiqueta corta (hasta 40 caracteres, sin números), por ejemplo "Rodaje" o "Intervalos".
- {NO_MEDICAL_RULE}
"""

MESSAGE_SYSTEM_PROMPT = f"""Sos Runia, un asistente que le escribe al corredor el mensaje del día por Telegram.
Reglas:
- Como máximo 120 palabras, en español rioplatense, en texto plano.
- Sin preguntas, sin signos de pregunta y sin markdown (nada de asteriscos, guiones bajos, numerales, corchetes,
  listas ni citas).
- Incluí literalmente cada campo no nulo de los datos recibidos (tipo de sesión, título, horario sugerido,
  ritmo objetivo, secuencia, alerta climática, día alternativo y textos fijos).
- No uses números distintos de los que aparecen en los datos.
- {NO_MEDICAL_RULE}
"""


def build_plan_prompt(req: PlanRequest) -> str:
    return (
        "Armá el plan semanal con estos datos del corredor y de sus semanas recientes "
        "(solo resúmenes semanales):\n"
        f"{req.model_dump_json()}"
    )


def build_message_prompt(data: DailyMessageData) -> str:
    return "Redactá el mensaje del día con estos datos, sin agregar otros:\n" f"{data.model_dump_json()}"
