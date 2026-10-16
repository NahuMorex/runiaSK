# Contrato: Bot de Telegram

**Librería**: `python-telegram-bot` en modo polling, en el mismo proceso que la API (`app/bot/handlers.py`).
**Idioma**: español. **Formato**: texto plano, sin `parse_mode` y sin markdown.

El bot solo se inicia si existe `TELEGRAM_BOT_TOKEN`. Los envíos salientes pasan por `services/notifier.py::Notifier`
(`async send_message(chat_id, text) -> bool`), que en los tests se reemplaza por un doble.

## Comandos entrantes

| Comando | Comportamiento | Respuestas | RF / AC |
|---|---|---|---|
| `/start` | Explica cómo vincular la cuenta | `"Hola, soy Runia. Para vincular tu cuenta, generá un código en la API y enviá /vincular <código>."` | RF-14 |
| `/vincular <código>` | Valida el código (`purpose=link`, menos de 15 min, sin usar) y crea el vínculo con el `chat_id` en la misma transacción | ✔ `"Listo: tu cuenta quedó vinculada a este chat."` · ✖ código inválido, usado o vencido: `"El código no es válido o ya venció."` · ✖ el chat ya está vinculado o la cuenta ya tiene un chat: `"Este chat o tu cuenta ya tienen un vínculo y no se puede modificar."` (el código **no** se consume) | RF-14 · AC-44, AC-45, AC-46 |
| `/registrar <estado> [rpe] [notas…]` | `estado` ∈ `completada` \| `parcial` \| `salteada` (sin distinguir mayúsculas). Resuelve la sesión de **hoy** del usuario vinculado al chat y llama a `services/results.register_result` (R-08) | ✔ `"Registré tu sesión de hoy como {Estado}."` y, si hubo reclasificación, `" Las próximas {n} sesiones pasan a suave/recuperación."` · ✖ chat no vinculado: `"Este chat no está vinculado a ninguna cuenta."` · ✖ no hay sesión hoy: `"No tenés una sesión planificada para hoy."` · ✖ pospuesta: `"La sesión de hoy fue pospuesta por clima y no admite registro."` · ✖ ya registrada: `"La sesión de hoy ya tiene un resultado registrado."` · ✖ falta el RPE o está fuera de rango: `"Indicá un RPE entero de 1 a 10. Ejemplo: /registrar completada 6"` · ✖ estado inválido: `"Estados válidos: completada, parcial, salteada."` | RF-09a..c, RF-12 · AC-29..AC-34, AC-38, AC-39, AC-69, AC-81 |
| `/restablecer` | Genera un código `purpose=reset` (30 min) para el usuario vinculado al chat | ✔ `"Tu código para restablecer la contraseña es {CÓDIGO}. Vence en 30 minutos. Envialo a POST /auth/password-reset junto con tu nueva contraseña."` · ✖ chat no vinculado: `"Este chat no está vinculado a ninguna cuenta."` | RF-17 · AC-49 |
| Texto libre | Si el usuario tiene un `daily_dispatch` de hoy en `awaiting_fatigue` y la ventana de 2 h sigue abierta, el texto se interpreta como fatiga | Entero de 1 a 10: arma y envía el mensaje diario · Otro valor: `"Respondé con un número entero del 1 al 10."`, sin enviar el mensaje y sin reiniciar la ventana · Sin una pregunta pendiente: no hace nada | RF-15, RF-16, RF-16b · AC-47, AC-48, AC-75, AC-80 |

**Aislamiento** (AC-38): el bot nunca acepta un `session_id` ni un email del usuario. Todo se resuelve desde el
`chat_id` vinculado, y los errores de servicio (`Forbidden`, `NotFound`) se responden con un texto genérico que no
revela datos de terceros.

## Mensajes salientes

### Resumen del plan del lunes (FR-014, AC-59, AC-16)

```text
Tu plan de la semana del 12/10:
- Lunes: suave, 3,00 km de trote
- Miércoles: calidad, 4,50 km de trote
- Sábado: suave, 5,00 km de trote
```

Si el plan se adoptó por falla del modelo, va precedido por la línea:
`Generación de un nuevo plan no disponible: te enviamos tu último plan válido.`

Si falla la generación y no hay un plan previo (AC-17b), se envía solo: `No es posible generar un plan en este momento.`

> El resumen es una lista de texto plano generada por el sistema, no por el modelo; la prohibición de markdown de AC-78
> aplica solo al mensaje diario redactado por Gemini.

### Pregunta de fatiga (FR-029, AC-47)

`¿Cómo está tu fatiga hoy del 1 al 10? Respondé con un número.`

### Mensaje diario (FR-031, FR-032)

Lo redacta Gemini y se valida según R-17; si no pasa la validación, se usa la plantilla. Ejemplo de plantilla:

```text
Hoy: calidad (Intervalos). Horario sugerido: 07:00–09:00.
Secuencia: trote 1,50 km; trote 1,00 km a 5:45 min/km (5:45), recuperación 2:00; trote 1,00 km a 5:45 min/km (5:45); caminata 0,50 km.
Ritmo objetivo: 5:45 min/km.
Alerta climática: lluvia probable (70%). Día alternativo: viernes.
```

Variantes que pueden aparecer:

- Sin alternativa: `No hay una alternativa disponible esta semana`.
- Clima no disponible: `Clima no disponible: seguí las pautas base de ritmo e hidratación.`
- Fatiga ≥ 8 con una sesión que ya era suave: `La sesión se mantiene suave por la fatiga.`
- Fatiga ≥ 8 con una sesión de calidad: el tipo pasa a `suave/recuperación` y la secuencia queda como un único bloque de trote.

### Mensaje de posposición (FR-038, AC-68, AC-43)

`Tu sesión de hoy quedó pospuesta por clima: {motivo}. No hay un día alternativo libre de condiciones desfavorables esta semana.`
Si la semana tiene 2 o más sesiones pospuestas, se agrega: ` Esta semana ya tenés {n} sesiones pospuestas por clima.`
Este mensaje no va precedido por la pregunta de fatiga.

### Motivos climáticos (texto)

- `lluvia probable ({p}%)` si p > 60
- `calor extremo ({t} °C)` si t > 32, donde t es la temperatura máxima redondeada al entero
- `tormenta eléctrica`

Si hay varios motivos, se unen con `" y "`.
