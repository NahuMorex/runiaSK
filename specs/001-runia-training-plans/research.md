# Research: Runia — Planes de entrenamiento para running

**Fase**: 0 · **Fecha**: 2026-10-15 · **Plan**: [plan.md](./plan.md)

El Technical Context no dejó ningún `NEEDS CLARIFICATION` abierto: el stack lo fijan AGENTS.md y la
constitución. Este documento registra las decisiones técnicas y las de interpretación que la spec deja
al diseño, incluidas las respuestas a los ítems abiertos de `checklists/guardrails.md` (CHK…).

---

## R-01 · Dependencias

- **Decisión**: runtime: `fastapi`, `uvicorn`, `google-genai`, `python-telegram-bot`, `argon2-cffi`, `pyjwt`,
  `httpx`, `email-validator`, `tzdata`. Dev: `pytest`. Python `==3.12.*` en `pyproject.toml` y `.python-version`.
- **Rationale**: todas trazan a un RF. httpx sirve para OpenWeatherMap (RF-05) y ya lo requiere `TestClient`;
  `email-validator` lo exige `EmailStr` para validar el formato del email (RF-01, AC-72); `tzdata` garantiza
  `America/Argentina/Buenos_Aires` aunque el sistema no tenga la base de zonas (RF-03f). Los tests async usan
  el plugin de pytest de anyio, que ya viene con FastAPI, así que no hace falta `pytest-asyncio`.
- **Alternativas**: `requests`, descartada porque es síncrona y bloquearía el event loop del bot.
  `passlib`, descartada porque es menos mantenida que `argon2-cffi`. `pytest-asyncio`, descartada por innecesaria.

## R-02 · Aislamiento de la IA y uso de Gemini

- **Decisión**: `app/ai/gemini.py` es el único archivo que importa `google.genai`. Usa `genai.Client(api_key=config.google_api_key())`
  con `client.aio.models.generate_content(model="gemini-3.5-flash-lite", contents=…, config=GenerateContentConfig(
  system_instruction=…, response_mime_type="application/json", response_schema=WeekPlanProposal))` y lo envuelve
  en `asyncio.wait_for(…, 20)` para el plan y `asyncio.wait_for(…, 5)` para el mensaje. Cualquier excepción del SDK,
  el timeout o una respuesta que no parsea con el esquema se traducen a `AIUnavailableError(reason)`.
  **No se usa function calling**: la orquestación determinista consulta el clima y lee los resúmenes semanales,
  y se los pasa al modelo como datos de entrada.
- **Rationale**: principio I (el módulo de IA no toca DB ni Telegram) y AGENTS.md (sin frameworks de agentes).
  Con function calling el modelo decidiría cuándo leer datos, y eso obligaría a que `ai/` accediera a servicios.
  La salida estructurada con pydantic reduce las respuestas mal formadas, aunque igual se validan (R-05).
- **Alternativas**: el SDK `google-generativeai`, descartado por obsoleto y fuera del stack; llamadas REST a mano,
  descartadas porque duplican lo que ya hace el SDK.

## R-03 · Scheduler (generación del lunes y mensaje diario)

- **Decisión**: en el `lifespan` de FastAPI, si hay `TELEGRAM_BOT_TOKEN`, se arranca el bot (`Application.initialize/start`,
  `updater.start_polling()`) y una tarea `asyncio` que llama a `scheduler.tick(clock.now())` cada 60 s.
  `tick` es idempotente gracias a filas de control en SQLite (`weekly_generation_runs`, `daily_dispatches`)
  y ejecuta, en orden: (1) la generación del lunes para los usuarios elegibles que todavía no tienen corrida
  para esa semana; (2) los envíos cuya hora de envío ya llegó y que no tienen dispatch; (3) el cierre de las
  esperas de fatiga que superaron las 2 h.
- **Rationale**: `tick(now)` es una función pura respecto del reloj y se testea sin esperar tiempo real.
  No suma dependencias (el `JobQueue` de PTB necesita el extra `job-queue` con APScheduler). Si el proceso
  estuvo caído, el siguiente tick pone al día lo pendiente del mismo día.
- **Alternativas**: el JobQueue de PTB o APScheduler, descartados por sumar una dependencia y estado en memoria
  difícil de reconstruir; cron externo, descartado porque AGENTS.md pide un solo proceso.
- **Nota**: la generación del lunes corre desde las 00:00 del lunes (hora de Buenos Aires), así que siempre
  ocurre antes de la hora de envío de cualquier usuario (AC-59). Cada usuario se procesa una sola vez por semana:
  un fallo con AC-17b no se reintenta, para no repetir el mensaje.

## R-04 · Clima (OpenWeatherMap)

- **Decisión**: se usa el endpoint `GET https://api.openweathermap.org/data/2.5/forecast?q={ciudad},AR&units=metric&appid=…`
  (5 días en intervalos de 3 h), con timeout de 5 s. Para cada intervalo se toma `dt` (UTC, convertido a
  Buenos Aires), `pop` (0-1), `main.temp` (°C) y `weather[].id` (los ids 200-232 son tormenta eléctrica).
  Las condiciones de un día se calculan con los intervalos `[dt, dt+3h)` que se solapan con el rango preferido:
  lluvia = máximo `pop` × 100, temperatura = máximo `temp`, y tormenta si algún intervalo la indica.
  Los timeouts, el HTTP 429, los 5xx, los errores de red y el JSON inválido se traducen a `WeatherUnavailableError`.
  Un 404 (ciudad desconocida) se trata igual y se registra con su motivo.
- **Rationale**: es la API gratuita que cubre los 3 días siguientes que pide la búsqueda de alternativa
  (AC-24, AC-40) con una sola llamada por evaluación. Un día sin intervalos que lo cubran no puede ser
  alternativa, porque no se inventan datos.
- **Alternativas**: One Call 3.0, descartada porque requiere suscripción aparte; consultar día por día,
  descartado por hacer más llamadas sin ganar precisión.

## R-05 · Validación estructural de la propuesta (FR-027, CHK005)

- **Decisión**: `domain/structure.py` rechaza la propuesta y la trata como falla del modelo (FR-027) si:
  la cantidad de sesiones no es la de FR-016; hay dos sesiones el mismo día; hay días fuera de `[start_date, domingo]`;
  hay una sesión sin bloques de trote; hay un bloque sin km o con km ≤ 0; hay un ritmo fuera de 1:00–20:00 min/km
  o una recuperación negativa. Además, para no inventar datos que exige FR-015: (a) en la **primera semana de un novato**
  (todo plan de un novato hasta su primer plan de semana completa como novato, inclusive; FR-015), si una sesión no alterna caminata y trote (al menos un bloque de cada tipo, sin dos
  consecutivos del mismo tipo); (b) si una sesión con ≥ 2 tramos con ritmo no tiene `recovery_after_s` en cada
  tramo con ritmo salvo el último; (c) en la **primera semana de un novato**, si algún bloque tiene `target_pace_s`:
  un novato en su primera semana nunca es elegible para calidad (FR-022), y convertir la sesión a suave eliminaría
  la caminata que exige AC-14.
- **Título**: `title` se normaliza, no se rechaza. Si está vacío, supera 40 caracteres o contiene dígitos, se
  reemplaza por el título fijo de su tipo (`"Calidad"` o `"Trote suave"`). Cuando una sesión de calidad se convierte
  a suave (FR-022, FR-023, FR-030, FR-042), su título pasa a `"Trote suave"`, porque el del modelo describe la sesión
  original.
- **Rationale**: (a), (b) y (c) son la única forma de garantizar AC-14 y AC-15 sin que el código invente bloques o
  recuperaciones (AGENTS.md: "No inventar datos"). Una propuesta que no los trae no se puede completar en forma
  determinista y es, en la práctica, estructuralmente inválida para ese perfil. El tiempo objetivo por tramo
  (AC-15) no se le pide al modelo: lo calcula el sistema (R-07).
- **Alternativas**: autocompletar la estructura, descartado por inventar un plan; reintentar al modelo dentro
  de los 20 s, descartado porque no está en la spec y complica la medición del timeout.

## R-06 · Orden del pipeline de guardarraíles (CHK001, CHK016, CHK025, CHK026)

- **Decisión**: `guardrails.apply(proposal, ctx) -> (Plan, list[GuardrailEvent])` es una función pura que corre en este orden:
  1. **Reclasificación pendiente** (FR-042): marca como reclasificadas las primeras `ctx.pending_reclass` sesiones por fecha y convierte a suaves las que son de calidad.
  2. **Calidad para novatos** (FR-022): si el usuario no es elegible, convierte todas las sesiones de calidad.
  3. **Máximo una de calidad** (FR-023): conserva la primera por fecha y convierte las demás.
  4. **Ritmo** (FR-024): acota cada tramo con ritmo al rango y recalcula su tiempo.
  5. **Topes por sesión** (FR-018 por sesión, FR-025): el tope efectivo es el **menor** de los aplicables; el factor es `tope ÷ km de la sesión`.
  6. **Topes semanales**: el tope efectivo es el **menor** entre el tope inicial × frecuencia (FR-018), 1,10 × base (FR-019),
     el planificado de la semana anterior si no tuvo ninguna Completada (FR-020), 0,80 × V4 en la descarga (FR-021, R-09)
     y V4 en la semana posterior a la descarga (FR-021). En esa semana posterior no aplica el 1,10 × base.
  7. **Pisos** (FR-026 escalado, solo en planes de semana completa; ver R-10): el piso efectivo es el **mayor** de los aplicables
     (AC-66, 0,70 × V4 en la descarga, V4 en la semana posterior). El factor es
     `min(piso ÷ volumen, mín_s(tope_sesión_s ÷ km_s), tope_semanal ÷ volumen)`, y solo se aplica si es mayor que 1.
     Así, los topes prevalecen.
  8. **Volumen planificado**: la suma de los km de trote resultantes, que se guarda en `plans.planned_volume_hm`.
  Cada paso que cambia algo emite un `GuardrailEvent(rule, scope, session_date|None, before, after)` para auditoría (FR-045, CHK010).
- **Rationale**: primero van las conversiones estructurales (no cambian km), después el ritmo (no cambia km),
  después los recortes (por sesión antes que semanales, como pide RF-06j) y al final los pisos, que no pueden romper ningún tope.
  Si se combinan varias condiciones de "semana anterior" (CHK026), se toma el más restrictivo de los topes y el mayor de los pisos,
  y un tope siempre gana a un piso.
- **Alternativas**: pedirle al modelo que respete los topes, descartado porque viola el principio I, ya que el
  modelo no es confiable; aplicar los pisos antes que los topes, descartado porque podría superar un tope.

## R-07 · Unidades, redondeos y tiempos (CHK012, CHK013, CHK014, CHK030)

- **Decisión**:
  - Las distancias se guardan como **enteros en centésimas de km** (`*_hm`). La entrada del modelo se convierte con `round(km × 100)`.
  - El recorte y el escalado hacen `floor(d_hm × factor)`, en aritmética `Fraction` para evitar errores de punto flotante.
  - El ritmo se guarda en segundos por km (entero). El límite rápido es `ceil(ritmo × 0,944)`: el resultado
    se redondea al segundo hacia el lado lento (360 → 339,84 → 340 = 5:40).
  - El tiempo objetivo de un tramo es `round_half_up(d_hm × ritmo ÷ 100)` en segundos enteros. Siempre lo calcula
    el sistema y nunca lo toma del modelo.
  - Las recuperaciones son **solo tiempo** (`recovery_after_s`). No tienen km y no cuentan para el volumen.
  - Si un recorte deja un bloque de trote en 0,00 km, el bloque se conserva con 0 km; no se agrega piso ni se borra
    la sesión. FR-026 no define un mínimo y la sesión sigue existiendo, así que se mantiene la cantidad de FR-016.
- **Rationale**: los enteros eliminan las diferencias de redondeo frente a la tolerancia de 0,01 km por bloque (CHK024).
- **Alternativas**: `float`, descartado por sus errores acumulados; `Decimal` en la DB, descartado porque
  SQLite no tiene un tipo decimal nativo.

## R-08 · Registro de resultados desde el bot (RF-09a, AC-38)

- **Decisión**: `services/results.py::register_result(conn, user_id, session_id, status, rpe, notes, today)` contiene
  todas las reglas: dueño de la sesión (si no lo es, `Forbidden`), que la sesión sea de hoy, que no esté pospuesta,
  que no esté ya registrada, el RPE y la reclasificación. El endpoint `POST /sessions/{session_id}/result` y el comando
  `/registrar` del bot llaman a esta misma función. El bot resuelve `user_id` desde el chat vinculado y `session_id`
  desde la sesión de hoy de ese usuario: nunca acepta un id de otro usuario y, ante `Forbidden` o `NotFound`, responde
  con un texto genérico.
- **Rationale**: API y bot corren en el mismo proceso, y el bot no tiene el JWT del usuario. Compartir la función
  garantiza las mismas validaciones (RF-09a) sin pasar por HTTP.
- **Alternativas**: que el bot llame por HTTP con un JWT emitido para el usuario, descartado porque agrega una
  emisión de tokens interna y una superficie sin requerimiento que la respalde.

## R-09 · Descarga: valor objetivo dentro de 20-30% (CHK028, CHK007, CHK033, CHK034)

- **Decisión**: la semana de descarga tiene **tope 0,80 × V4 y piso 0,70 × V4**, donde V4 es el volumen planificado
  de la cuarta semana de la racha, aunque haya sido parcial (CHK034). Al modelo se le pide un objetivo de 0,75 × V4.
  El test verifica `0,70 × V4 − tolerancia ≤ V5 ≤ 0,80 × V4`.
  - Un plan parcial también puede ser de descarga. Le aplica el tope y no el piso (R-10).
  - Un plan adoptado por falla del modelo (AC-16) en la semana 5 se marca `is_deload` y aplica los mismos topes y pisos.
    La semana 6 iguala a V4 con la regla normal (CHK033).
- **Rationale**: es determinista y testeable, y cualquier volumen dentro de la banda cumple AC-19a.
- **Alternativas**: un 25% fijo exacto, descartado porque el floor por bloque haría casi imposible un valor exacto.

## R-10 · Planes parciales y pisos (CHK006)

- **Decisión**: en los planes parciales los topes semanales **no** se prorratean: se aplican tal como los define el PRD.
  Los **pisos** (AC-66, piso de descarga y vuelta tras la descarga) se aplican **solo a planes de semana completa**.
- **Rationale**: AC-66 y AC-19d hablan de "plan semanal" y comparan volúmenes de semanas completas. Forzar un piso
  semanal sobre pocos días alargaría cada sesión sin respaldo del PRD. El tope por sesión (distancia objetivo, tope inicial)
  sigue protegiendo cada sesión.
- **Alternativas**: prorratear por días, descartado porque no está en el PRD y alteraría la base del 10% de AC-74.

## R-11 · Semanas cerradas, racha y elegibilidad de calidad (CHK017, CHK018, CHK019, CHK035)

- **Decisión**:
  - Una semana va del lunes 00:00 al domingo 23:59:59 en Buenos Aires. Una semana está **cerrada** si su domingo es anterior a la fecha actual.
  - Los resúmenes (`domain/summaries.py`) se calculan desde las tablas guardadas (planes, sesiones, resultados), **no**
    desde lo que recibe el modelo. FR-028 solo limita lo que se envía a `app/ai/` (CHK035).
  - **Racha**: se cuentan hacia atrás las semanas cerradas consecutivas con plan y al menos 1 Completada. Se corta ante
    una semana sin plan (CHK019), una semana con plan sin Completadas o una semana de descarga, porque el conteo
    reinicia después de ella (AC-19c). Si la racha llega a 4, el plan siguiente es de descarga.
  - **Calidad para novatos**: las 3 semanas calendario cerradas inmediatamente anteriores deben tener plan, al menos
    1 Completada y ninguna Parcial/Cortada con RPE ≥ 7. Con menos de 3 semanas de historia, no es elegible (CHK018).
  - **Base de topes**: `prev` es el plan de la semana calendario anterior. Sin `prev` aplica el tope inicial. Si `prev`
    es parcial y no hay ninguna semana completa antes, aplica el tope inicial (AC-62). Si `prev` es parcial y hay una
    semana completa antes, la base del 10% es el volumen de la última semana completa (AC-74). FR-020 usa el volumen
    planificado de `prev`.
  - **Perfil sin cambios** (AC-66): `plans.profile_snapshot` guarda nivel, frecuencia, distancia y ritmo al generarse.
    El piso de AC-66 aplica solo si el snapshot de `prev` es igual al perfil actual.
  - **Semana posterior a la descarga**: `is_post_deload` es verdadero si el plan de la semana anterior tiene `is_deload=1`,
    haya tenido Completadas o no; con eso se omite el 10%. `post_deload_target_hm` = V4 solo si la descarga tuvo alguna
    Completada; si no, aplica `no_increase_hm = V5` (FR-020).
- **Rationale**: son definiciones cerradas y verificables con datos guardados.
- **Alternativas**: considerar elegible a un novato con menos de 3 semanas, descartado porque contradice el sentido protector de RF-06d.

## R-12 · Conversión a suave (CHK015, CHK021, CHK022)

- **Decisión**: una sesión es de **calidad** si tiene al menos un bloque de trote con `target_pace_s`, y es **suave** si no tiene ninguno
  (clarificación de la spec). La conversión de FR-023, FR-030 y FR-042 se aplica **solo a sesiones de calidad** y
  reemplaza todos sus bloques por un único bloque de trote con `distance_hm = suma de los km de trote`, sin ritmo, sin
  tiempo y sin recuperación (se eliminan sus bloques de caminata, porque queda "un único bloque"). Una sesión que ya es
  suave conserva sus bloques y km, incluida la alternancia caminata/trote de un novato (igual que AC-80). FR-042 marca
  `reclassified=1` en ambos casos y modifica la sesión guardada. FR-030 (fatiga) solo cambia el mensaje y no persiste.
- **Rationale**: es lo que dicen literalmente AC-48, AC-77 y RF-06k ("un único bloque de trote").
- **Alternativas**: conservar la caminata al convertir una sesión de calidad, descartado porque contradice "un único bloque". Convertir también las sesiones suaves, descartado porque FR-042 solo convierte las de calidad y a un novato le quitaría la caminata.

## R-13 · Fallback del lunes (AC-16, CHK009, CHK020, CHK023)

- **Decisión**: el "último plan válido" es el plan más reciente del usuario por `week_start`. Sus sesiones se mapean
  **por día de la semana** a las fechas de la semana actual, con los mismos bloques, y pasan por el pipeline completo de R-06
  con el contexto de la semana actual, incluida la reclasificación pendiente. El plan resultante se guarda con
  `source='fallback'`, `adopted_from_plan_id` y su propio `planned_volume_hm`, que es la base para la semana siguiente (CHK020).
- **Rationale**: cumple FR-017 y SC-001, porque ningún plan se entrega sin guardarraíles, y AC-16 ("mismos días y sesiones").

## R-14 · Base de conocimiento `kb.md`

- **Decisión**: no se crea en esta feature. Las pautas que necesita el prompt (progresión, estructura de bloques,
  prohibición de consejo médico) se escriben en `app/ai/prompts.py`.
- **Rationale**: AGENTS.md la menciona como futura y el PRD no la exige (principio III). Si se agrega más adelante,
  se cargaría solo dentro de `app/ai/`.

## R-15 · Autenticación y renovación del token (AC-03, AC-05, AC-53, AC-73)

- **Decisión**: JWT HS256 con claims `sub` (user_id), `iat`, `exp = now + 2h` y `auth_time` (el login original).
  En cada request autenticado: se verifica la firma y `exp`, se verifica que `now − auth_time < 7 días` y que el usuario
  todavía exista. Si algo falla, se responde 401. Si pasa, se emite un token nuevo con el mismo `auth_time` en el header
  de respuesta **`X-Session-Token`**. El login devuelve `{"access_token", "token_type": "bearer", "expires_at"}`.
- **Rationale**: un usuario borrado no existe, así que su token da 401 (AC-53) sin necesidad de una lista de revocación.
- **Alternativas**: devolver el token renovado en el body, descartado porque obligaría a envolver todas las respuestas.

## R-16 · Códigos de un solo uso (FR-010, FR-011)

- **Decisión**: el código de vinculación tiene 8 caracteres de `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (sin caracteres
  ambiguos) y lo genera `secrets`. El de restablecimiento tiene 10 caracteres del mismo alfabeto. Ambos se guardan solo como
  SHA-256 en `one_time_codes`, con `purpose`, `expires_at` y `used_at`. El uso es atómico: un `UPDATE … WHERE used_at IS NULL AND expires_at > now`
  dentro de la misma transacción que el efecto (vínculo o cambio de hash).
- **Rationale**: un código filtrado en los logs o en la base no sirve, y la ventana corta con más de 40 bits de entropía
  hace inviable la fuerza bruta.

## R-17 · Mensaje diario: plantilla y validación (FR-031, FR-032, AC-78)

- **Decisión**: `domain/daily_message.py` arma `DailyMessageData` y `render_template(data)`, que garantiza ≤ 150 palabras.
  La validación del texto del modelo: (1) no vacío; (2) `len(text.split()) ≤ 150`; (3) contiene literalmente cada
  dato obligatorio renderizado (etiqueta de tipo, rango `HH:MM–HH:MM`, ritmo `m:ss`, secuencia, motivo de alerta,
  nombre del día alternativo y textos fijos de AC-13 y AC-24); (4) todo número del texto (regex `\d+(?:[.,:]\d+)*`)
  aparece en el conjunto de números de `render_template(data)`; (5) no contiene `?` ni `¿`; (6) no contiene markdown
  (`*`, `_`, `` ` ``, `#`, `[`, `](`, `>` al inicio de línea, ni listas `- `/`1. ` al inicio de línea).
  El rango horario sugerido es el rango preferido completo, que está "dentro" de sí mismo (AC-28).
- **Rationale**: son comprobaciones deterministas y completas de AC-78. El riesgo de consejo médico que queda lo acepta el PRD. La mitigación es la instrucción en ambos prompts (verificada por test, T084) más las reglas (3) y (4), que impiden que el texto agregue datos o números ajenos a la sesión.

## R-18 · Auditoría (FR-045, RNF-02)

- **Decisión**: `app/audit.py` define `audit.event(type, **fields)`, que escribe una línea JSON por evento en el logger
  `runia.audit` (stdout) con `ts`, `type` y los campos. Los tipos son `llm_call` (operación, resumen del prompt ≤ 500
  caracteres, resumen de la respuesta, duración, resultado), `tool_call` (`weather` | `db`), `guardrail` (regla,
  alcance, fecha, antes, después), `session_postponed`, `external_error` (servicio, motivo), `weather_decision`
  (alerta, alternativa, posposición), `message_sent` (plantilla o modelo) y `plan_generation` (fuente, resultado).
  La redacción recursiva reemplaza por `"[redacted]"` los valores de las claves `password`, `token`, `access_token`,
  `api_key`, `authorization`, `code` y `secret`. Los historiales nunca se pasan: solo resúmenes semanales.
  Para `tool_call: db` se registra un evento por operación de servicio (p. ej. `save_plan`, `register_result`),
  no por cada sentencia SQL.
- **Rationale**: cubre la lista cerrada de RNF-02 con un solo punto de salida que se puede testear con `caplog`.

## R-19 · Historial y cronograma (AC-35, AC-36)

- **Decisión**: `GET /schedule` devuelve el plan de la semana en curso. Si no hay plan, responde 404
  "No tenés un plan para la semana en curso". `GET /history` devuelve las sesiones con `date < hoy`, **más** la de hoy
  si ya tiene resultado, para que AC-29 se refleje en el historial el mismo día. El estado mostrado es el resultado
  guardado, "Pospuesta por clima", o "Sin registrar" si la sesión es pasada y no tiene ninguno. A la sesión de hoy sin
  resultado se le muestra "Hoy" y a las futuras "Proyectada", solo en el cronograma.

## R-20 · Perfil: actualización parcial (AC-06, AC-07, AC-09)

- **Decisión**: `PUT /profile` acepta un objeto con todos los campos opcionales. Los omitidos no cambian. Se aplica
  sobre el perfil actual y la validación corre sobre el resultado combinado, incluidas las reglas cruzadas: inicio < fin,
  duración ≥ 1 h y hora de envío < fin. Si algo falla, responde 422 y no guarda nada. `null` solo se acepta en
  `current_pace` (para borrarlo). El ritmo no es obligatorio al guardar el perfil: su ausencia se rechaza recién al
  pedir un plan (AC-08).
- **Rationale**: AC-09 presupone perfiles incompletos, así que el PUT no puede exigir todos los campos.
