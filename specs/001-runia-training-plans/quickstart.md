# Quickstart: validación end-to-end de Runia

**Plan**: [plan.md](./plan.md) · **Contratos**: [api](./contracts/api.md), [bot](./contracts/telegram-bot.md), [IA](./contracts/ai-module.md) · **Datos**: [data-model.md](./data-model.md)

Esta guía sirve para comprobar que la feature funciona. No es una guía de implementación.

## Requisitos previos

- `uv` instalado. Python 3.12 lo resuelve uv a partir de `.python-version`; no se usa el 3.14 del sistema.
- Un archivo `.env` en la raíz del repo, que **no se commitea** (ya está en `.gitignore`), con:
  `GOOGLE_API_KEY`, `TELEGRAM_BOT_TOKEN`, `OPENWEATHER_API_KEY`, `JWT_SECRET` y, opcionalmente, `RUNIA_DB_PATH`.
- Un bot de Telegram creado con @BotFather y una cuenta de Telegram para probarlo.

## 1. Tests automáticos (sin servicios externos)

```bash
uv sync
uv run pytest                      # toda la suite; IA, clima, Telegram y reloj son dobles
uv run pytest tests/unit/test_guardrails.py   # solo los guardarraíles
```

Resultado esperado: todo en verde, sin llamadas de red. Si se corre la suite sin `.env`, debe pasar igual,
porque los tests inyectan valores falsos.

## 2. Verificación de secretos (SC-009, principio II)

```bash
git grep -nE "AIza[0-9A-Za-z_-]{20,}|[0-9]{8,10}:[A-Za-z0-9_-]{35}" -- . ':!*.md' || echo "OK: sin credenciales"
git check-ignore .env && echo "OK: .env ignorado"
grep -rn "google.genai\|from google import genai" app/ | grep -v "^app/ai/" || echo "OK: SDK aislado en app/ai"
```

## 3. Levantar API + bot

```bash
uv run --env-file .env uvicorn app.main:app --reload
```

Resultado esperado: en los logs JSON aparecen el arranque de la API, el bot y el scheduler. Si se lanza sin
`TELEGRAM_BOT_TOKEN`, la API arranca sin el bot ni el scheduler.

## 4. Flujo principal (US1 → US2 → US3)

Con `curl` o en `/docs`:

1. `POST /auth/register` → **201**. Si se repite → **409**. Con una contraseña de 7 caracteres → **422**.
2. `POST /auth/login` → **200** con `access_token`. Con una contraseña incorrecta → **401**.
3. `PUT /profile` con un nivel `intermedio` sin ritmo, más frecuencia, distancia, ciudad, rango y hora de envío → **200**.
   Probar `send_time` ≥ fin del rango → **422**, y verificar con `GET /profile` que no cambió nada.
   Verificar también que cada respuesta autenticada trae el header `X-Session-Token`.
4. `POST /plan` → **422** "No hay datos sobre tu ritmo cargados en tu perfil".
5. `PUT /profile` con `current_pace: "6:00"` y después `POST /plan` → **422** "Tu cuenta no tiene un chat de Telegram vinculado".
6. `POST /telegram/link-code` → **201** con un código. En Telegram, enviar `/vincular <código>` → "Listo…".
   Repetir con el mismo código → "El código no es válido o ya venció."
7. `POST /plan` → **201**. Comprobar en la respuesta: tantas sesiones como `min(frecuencia, días hasta el domingo)`
   (AC-57); ninguna sesión por encima de 5 km de trote ni de la distancia objetivo (AC-61, AC-67); como máximo una
   sesión `calidad`, con ritmos entre 5:40 y 6:00, `target_time` y `recovery_after` (AC-15, AC-21, AC-22).
   Repetir `POST /plan` → **409**. Por Telegram **no** debe llegar nada (AC-56).
8. Verificar en los logs los eventos `llm_call`, `guardrail` (si hubo recortes) y `plan_generation`, sin tokens ni contraseñas.

## 5. Mensaje diario (US4, US5)

1. Con `PUT /profile`, poner `send_time` 2 minutos en el futuro (y dejar el rango posterior a esa hora), y tener una sesión hoy.
2. A la hora de envío, el bot pregunta la fatiga. Responder `abc` → vuelve a preguntar. Responder `9`.
3. Resultado esperado: un mensaje de ≤ 150 palabras, sin markdown ni preguntas, con el tipo, el rango horario y, si
   corresponde, el ritmo o la secuencia, llegado en ≤ 10 s. Con fatiga 9 y una sesión de calidad, el mensaje dice `suave/recuperación`.
4. Para probar la falla del clima, reiniciar con `OPENWEATHER_API_KEY=invalida` y repetir. El mensaje incluye
   "Clima no disponible: seguí las pautas base de ritmo e hidratación." y en los logs aparece `external_error`.

Los escenarios de alerta, alternativa, posposición, plantilla de respaldo y espera de 2 h están cubiertos por
`tests/integration/test_daily_flow.py`, con dobles de clima, IA y reloj.

## 6. Registro, cronograma e historial (US6, US7)

1. En Telegram: `/registrar completada` → pide el RPE. `/registrar completada 6 buenas piernas` → "Registré…".
   Repetir → "ya tiene un resultado registrado".
2. `GET /history` → la sesión de hoy aparece como "Completada", con RPE 6 y las notas.
3. `GET /schedule` → las sesiones pasadas sin registrar aparecen como "Sin registrar" y las futuras como "Proyectada".
4. Con otro usuario B: `POST /sessions/{id de A}/result` con el token de B → **403** (AC-37).

## 7. Cuenta (US8)

1. En Telegram: `/restablecer` → llega un código. `POST /auth/password-reset` con el código y una contraseña nueva → **200**.
   Reutilizar el código → **400**.
2. `DELETE /profile` → **400** con la advertencia. `DELETE /profile?confirm=true` → **204**.
   Después, `POST /auth/login` → **401** y un request con el token anterior → **401**.

## 8. Generación automática del lunes (US3)

La cubre `tests/integration/test_weekly_job.py`, que llama a `scheduler.tick(now)` con un reloj fijo en un lunes a las 00:01.
Verifica AC-59, AC-60, AC-16, AC-17b y que un segundo tick no genere un plan duplicado.
