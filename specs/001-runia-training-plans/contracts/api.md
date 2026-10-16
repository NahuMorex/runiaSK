# Contrato: API REST

**Base**: `http://localhost:8000` · **Formato**: JSON UTF-8 · **Zona horaria**: `America/Argentina/Buenos_Aires`

## Convenciones

- **Autenticación**: header `Authorization: Bearer <jwt>`. Todos los endpoints la requieren salvo los de `/auth/*`.
- **Renovación** (AC-05, R-15): toda respuesta exitosa de un endpoint autenticado incluye el header
  `X-Session-Token` con un JWT nuevo de 2 h, que conserva el `auth_time` del login.
- **401** (AC-73, AC-05, AC-53): falta el token, el token es inválido, está vencido, pasaron ≥ 7 días desde
  `auth_time` o el usuario no existe. El cuerpo es `{"detail": "No autenticado"}` y no se devuelven datos.
- **Errores**: cuerpo `{"detail": "<mensaje>"}`. Los 422 de validación de FastAPI conservan su formato
  `detail: [...]`, salvo los mensajes fijos del PRD, que se devuelven como string.
- **Formatos**: el ritmo es `"m:ss"` o `"mm:ss"` (p. ej. `"6:00"`); las horas son `"HH:MM"`; las distancias se
  expresan en km como número con hasta 2 decimales (internamente, centésimas; ver data-model).

---

## POST /auth/register — RF-01 · AC-01, AC-02, AC-72

Request `{"email": "milena@example.com", "password": "********"}`

| Caso | Código | Cuerpo |
|---|---|---|
| Cuenta creada | 201 | `{"id": 1, "email": "milena@example.com"}` |
| Email ya registrado (sin distinguir mayúsculas) | 409 | `{"detail": "El email ya está registrado"}` |
| Email con formato inválido, o contraseña con <8 o >128 caracteres | 422 | validación |

## POST /auth/login — RF-02a · AC-03, AC-04

Request `{"email": "...", "password": "..."}`

| Caso | Código | Cuerpo |
|---|---|---|
| Credenciales correctas | 200 | `{"access_token": "<jwt>", "token_type": "bearer", "expires_at": "2026-10-15T12:00:00-03:00"}` |
| Email o contraseña incorrectos, o cuenta eliminada | 401 | `{"detail": "Credenciales inválidas"}` |

## POST /auth/password-reset — RF-17 · AC-49, AC-50

No requiere autenticación. El código se pide desde el bot con `/restablecer` (ver telegram-bot.md).

Request `{"code": "ABCD234XYZ", "new_password": "********"}`

| Caso | Código | Cuerpo |
|---|---|---|
| Código vigente y no usado, contraseña de 8 a 128 caracteres | 200 | `{"detail": "Contraseña actualizada"}` |
| Código inválido, usado o con más de 30 min | 400 | `{"detail": "Código inválido o vencido"}` |
| `new_password` fuera de 8-128 caracteres | 422 | validación (el código no se consume) |

## GET /profile — RF-18a · AC-51

200 → `Profile`:

```json
{
  "level": "intermedio",
  "frequency": 4,
  "target_distance_km": 10.0,
  "current_pace": "6:00",
  "city": "Rosario",
  "preferred_range": {"start": "07:00", "end": "09:00"},
  "send_time": "06:00",
  "telegram_linked": true
}
```

Los campos que todavía no se cargaron vuelven como `null`.

## PUT /profile — RF-03a..g, RF-18a..c · AC-06, AC-07, AC-55, AC-70, AC-71

Request: cualquier subconjunto de `level`, `frequency`, `target_distance_km`, `current_pace` (acepta `null`),
`city` y `preferred_range` (objeto completo `{start, end}`) o `send_time`. Se combina con el perfil guardado
y se valida el resultado (R-20).

| Caso | Código | Cuerpo |
|---|---|---|
| Datos válidos | 200 | `Profile` actualizado |
| Algún valor fuera de rango o formato, inicio ≥ fin, rango < 1 h, envío ≥ fin, ciudad vacía o > 100 caracteres, nivel desconocido, `null` en un campo que no lo admite | 422 | validación; no se persiste nada |

Los cambios no tocan el plan vigente (AC-70). Cualquier cambio de nivel válido se acepta (FR-008).

## DELETE /profile — RF-19 · AC-52, AC-53

| Caso | Código | Cuerpo |
|---|---|---|
| Sin `confirm=true` (ausente u otro valor) | 400 | `{"detail": "La eliminación es definitiva y no se puede deshacer. Repetí la solicitud con confirm=true para confirmar."}` |
| `?confirm=true` | 204 | sin cuerpo; borra el usuario y todos sus datos en cascada. No incluye `X-Session-Token` |

## POST /telegram/link-code — RF-14 · AC-44..AC-46

| Caso | Código | Cuerpo |
|---|---|---|
| Cuenta sin chat vinculado | 201 | `{"code": "K7P2QX9M", "expires_at": "...", "instructions": "Enviá /vincular K7P2QX9M al bot dentro de los 15 minutos."}` |
| Cuenta que ya tiene un chat vinculado | 409 | `{"detail": "Tu cuenta ya tiene un chat de Telegram vinculado"}` |

## POST /plan — RF-04, RF-06a..l, RF-21 · AC-08..AC-11, AC-14, AC-15, AC-17, AC-56..AC-58, AC-61..AC-67, AC-76, AC-77, AC-82, AC-83

Sin cuerpo. Genera el plan de la semana en curso, completo si es lunes y parcial en otro caso. No envía nada por Telegram.

Precedencia de los errores: primero el perfil incompleto, después la falta de Telegram, después el conflicto y por último la IA.

| Caso | Código | Cuerpo |
|---|---|---|
| Plan creado | 201 | `Plan` |
| Intermedio o avanzado sin ritmo | 422 | `{"detail": "No hay datos sobre tu ritmo cargados en tu perfil"}` |
| Falta otro campo | 422 | `{"detail": "No hay datos sobre tu {campo} cargados en tu perfil"}` (nombres en data-model) |
| Sin chat vinculado | 422 | `{"detail": "Tu cuenta no tiene un chat de Telegram vinculado"}` |
| Ya hay plan para la semana | 409 | `{"detail": "Ya tenés un plan para la semana en curso"}` |
| Gemini falla, tarda más de 20 s o devuelve una propuesta inválida | 503 | `{"detail": "No es posible generar un plan en este momento."}` |

`Plan`:

```json
{
  "id": 12,
  "week_start": "2026-10-12",
  "start_date": "2026-10-15",
  "is_full": false,
  "is_deload": false,
  "planned_volume_km": 14.5,
  "sessions": [
    {
      "id": 40,
      "date": "2026-10-15",
      "weekday": "jueves",
      "title": "Intervalos",
      "type": "calidad",
      "run_km": 5.0,
      "status": "Hoy",
      "blocks": [
        {"kind": "trote", "distance_km": 1.5},
        {"kind": "trote", "distance_km": 1.0, "target_pace": "5:45", "target_time": "5:45", "recovery_after": "2:00"},
        {"kind": "trote", "distance_km": 1.0, "target_pace": "5:45", "target_time": "5:45"},
        {"kind": "caminata", "distance_km": 0.5}
      ]
    }
  ]
}
```

- `type` es `"calidad"` o `"suave"`. `kind` es `"trote"` o `"caminata"`.
- `target_time` y `recovery_after` usan el formato `m:ss`, o `h:mm:ss` si superan la hora.
- `status` es uno de: `"Completada"`, `"Parcial/Cortada"`, `"Salteada"`, `"Pospuesta por clima"`, `"Sin registrar"`, `"Hoy"` o `"Proyectada"`.

## GET /schedule — RF-10 · AC-35

| Caso | Código | Cuerpo |
|---|---|---|
| Hay plan para la semana en curso | 200 | `Plan`; las sesiones van de lunes a domingo (solo las que existen), con `status` según R-19 y `result` (`{status, rpe, notes}` o `null`) |
| No hay plan | 404 | `{"detail": "No tenés un plan para la semana en curso"}` |

## GET /history — RF-11 · AC-29, AC-30, AC-34, AC-36

200 → `{"sessions": [HistoryItem, ...]}`, ordenado por fecha descendente. Incluye las sesiones con fecha anterior
a hoy y la de hoy si ya tiene resultado (R-19).

`HistoryItem`: `{"session_id", "date", "title", "type", "run_km", "status", "rpe": int|null, "notes": str|null}`.
`status` toma uno de estos valores: `"Completada"`, `"Parcial/Cortada"`, `"Salteada"`, `"Pospuesta por clima"`, `"Sin registrar"`.

## POST /sessions/{session_id}/result — RF-09a..c, RF-12, RF-13b · AC-29..AC-34, AC-37, AC-39, AC-69, AC-81

Request `{"status": "completed" | "partial" | "skipped", "rpe": 1-10 | null, "notes": "texto opcional ≤500"}`

Orden de las validaciones: la sesión existe → el usuario es su dueño → no está pospuesta → la fecha es hoy → no tiene registro previo → el RPE es válido.

| Caso | Código | Cuerpo |
|---|---|---|
| Registro guardado | 201 | `{"session_id", "status", "rpe", "notes", "reclassified_sessions": [ids], "pending_reclassification": 0..2}` |
| La sesión no existe | 404 | `{"detail": "Sesión no encontrada"}` |
| La sesión es de otro usuario | 403 | `{"detail": "Acceso denegado"}`; no revela datos (AC-37) |
| Sesión "Pospuesta por clima" | 422 | `{"detail": "La sesión fue pospuesta por clima y no admite registro"}` |
| La fecha de la sesión no es hoy | 422 | `{"detail": "Solo podés registrar la sesión del día"}` |
| Ya tiene un registro | 409 | `{"detail": "La sesión ya tiene un resultado registrado"}` |
| `completed`/`partial` sin RPE, RPE fuera de 1-10, `skipped` con RPE | 422 | validación |

Si se registra `partial` con RPE ≥ 7, se dispara la reclasificación de FR-042.

---

## Aislamiento entre usuarios (FR-044, AC-37)

Los recursos de perfil, plan, cronograma e historial se resuelven **siempre** desde el usuario del token: no aceptan
un ID de usuario, así que no pueden devolver datos de otro. El único recurso con un ID de otra entidad en la ruta es
`/sessions/{session_id}/result`, y si esa sesión pertenece a otro usuario responde 403.

## Trazabilidad

| Endpoint | RF / AC |
|---|---|
| POST /auth/register | RF-01 · AC-01, AC-02, AC-72 |
| POST /auth/login | RF-02a · AC-03, AC-04 |
| (todas las autenticadas) | RF-02b · AC-05, AC-73 |
| POST /auth/password-reset | RF-17 · AC-49, AC-50 |
| GET/PUT /profile | RF-03a..g, RF-18a..c · AC-06, AC-07, AC-51, AC-55, AC-70, AC-71 |
| DELETE /profile | RF-19 · AC-52, AC-53 |
| POST /telegram/link-code | RF-14 · AC-44 |
| POST /plan | RF-04, RF-06a..l, RF-21 · AC-08..AC-11, AC-14, AC-15, AC-17, AC-56..AC-58, AC-61..AC-67, AC-76, AC-77, AC-82, AC-83 |
| GET /schedule | RF-10 · AC-35 |
| GET /history | RF-11 · AC-36 |
| POST /sessions/{id}/result | RF-09a..c, RF-12, RF-13b · AC-29..AC-34, AC-37, AC-39, AC-69, AC-81 |
