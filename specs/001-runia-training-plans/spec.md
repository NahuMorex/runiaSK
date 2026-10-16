# Feature Specification: Runia — Planes de entrenamiento para running

**Feature Branch**: `main` (sin rama dedicada; directorio de la spec: `specs/001-runia-training-plans`)

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "Generá el spec a partir del PRD @PRD.md" (fuente: `PRD.md`, PRD-001)

## Alcance de esta especificación

Esta spec cubre el PRD-001, salvo lo indicado abajo como fuera de esta iteración. Cada requerimiento funcional traza a uno o más RF/RNF y AC del PRD
(principio III de la constitución). Los códigos de respuesta exactos, rutas y textos de los AC del PRD
siguen vigentes y se referencian por su ID; esta spec describe el comportamiento en términos del usuario.

**Fuera de esta iteración** (limitaciones aceptadas en "Riesgos y Dependencias" del PRD):

- RF-20 / AC-54: restricción del cambio de nivel de novato a intermedio o avanzado. Cualquier cambio de nivel válido se acepta.
- Confirmación de RF-07a / AC-25 y reprogramación de RF-07b / AC-26: ante una alerta climática, el mensaje diario solo informa el motivo y el día alternativo; no pide confirmación y la sesión original sigue ejecutable.

El registro de sesiones (RF-09a) **sí** se incluye, porque la descarga, la calidad para novatos, la
reclasificación por RPE, el historial y la meta de 70% dependen de él.

## Clarifications

### Session 2026-10-15

- Q: Los riesgos del PRD declaran no implementados RF-09a, RF-20, AC-25 y AC-26. ¿Qué entra en esta spec? → A: Se incluye RF-09a; RF-20, la confirmación de RF-07a (AC-25) y RF-07b (AC-26) quedan fuera como limitaciones aceptadas.
- Q: ¿El plan semanal se envía por Telegram cuando se genera? → A: Solo el plan generado automáticamente el lunes (incluido el adoptado por AC-16) se envía por Telegram, como resumen con día, tipo y km de trote de cada sesión; el plan pedido a demanda se devuelve solo en la respuesta de la API.
- Q: ¿Cuántas sesiones lleva un plan parcial (generado a mitad de semana)? → A: Exactamente min(frecuencia, días restantes hasta el domingo, incluido el día de generación), una por día.
- Q: Con fatiga ≥ 8 y una sesión de calidad hoy, ¿cómo queda la sesión suave? → A: Igual que la conversión de FR-023: un único bloque de trote con los mismos km de trote totales, sin tramos, recuperaciones ni ritmo objetivo; solo en el mensaje del día.
- Q: Si los 2 días de entrenamiento siguientes a una Parcial/Cortada con RPE ≥ 7 caen en una semana sin plan todavía, ¿qué pasa? → A: La reclasificación queda pendiente y se aplica a las primeras sesiones del plan siguiente al generarse, hasta completar 2 sesiones entre ambas semanas.
- Q: ¿Se puede registrar un resultado para una sesión "Pospuesta por clima"? → A: No; el registro se rechaza sin guardar y la sesión conserva su estado.
- Q: ¿El último plan válido adoptado por falla del modelo (AC-16) pasa por los guardarraíles de la semana actual? → A: Sí; se adoptan los mismos días y sesiones, pero antes de entregarlo se aplican todos los guardarraíles de la semana actual (FR-018 a FR-026 y la reclasificación pendiente de FR-042), lo que puede recortar km.
- Q: Si la propuesta queda por debajo de un piso de volumen (AC-66, mínimo de la descarga, vuelta tras la descarga), ¿qué se hace? → A: Se escala al piso multiplicando los bloques de trote por piso ÷ volumen y redondeando hacia abajo a 0,01 km; ningún escalado supera un tope vigente (los topes prevalecen sobre los pisos) y el piso se considera cumplido con una tolerancia de 0,01 km por bloque de trote.
- Q: ¿Cómo se clasifica una sesión como de calidad, si el rango de FR-024 incluye el ritmo actual y un novato puede no tener ritmo? → A: Es de calidad toda sesión con al menos un tramo con ritmo objetivo; es suave la que no tiene ninguno. El rango de FR-024 no cambia.
- Q: ¿Qué se hace si una sesión de calidad permitida trae un ritmo objetivo fuera del rango de FR-024? → A: Se acota cada tramo al límite más cercano del rango (el límite rápido se redondea al segundo hacia el lado más lento) y se recalcula su tiempo objetivo; los km no cambian.
- Q: ¿Qué se hace si la propuesta del modelo es estructuralmente inválida? → A: Se trata como falla del modelo (FR-027): a demanda, "No es posible generar un plan en este momento."; el lunes, el plan de respaldo de AC-16. Se registra el motivo.

### Session 2026-10-16

- Q: Si el plan se crea después de la hora de envío del día, o la sesión de hoy ya tiene resultado registrado, ¿qué pasa con el mensaje diario? → A: El flujo diario arranca en el minuto siguiente para la sesión de hoy; si la sesión ya tiene resultado registrado, no se envía nada.
- Q: ¿Qué es la "primera semana" de un novato (FR-015, AC-14)? → A: Todo plan de un novato hasta su primer plan de semana completa como novato, inclusive; solo cuentan los planes cuyo snapshot de perfil es novato.
- Q: ¿Cómo se cumple FR-033 (sin consejo médico ni de lesiones)? → A: Con la prohibición explícita en los prompts del plan y del mensaje diario, verificada por test; el riesgo residual en el texto libre del modelo es una limitación aceptada del PRD.
- Q: ¿Qué exige "progresivo según el nivel" (FR-015) más allá de la primera semana de un novato? → A: Se cumple con los guardarraíles (piso de AC-66 y topes); después de la primera semana, el modelo decide si un novato sigue alternando caminata y trote, sin validación estructural extra.
- Q: ¿Qué pasa si un recorte deja un bloque de trote en 0,00 km? → A: El bloque se conserva con 0,00 km; no se agrega un mínimo ni se elimina el bloque o la sesión.
- Q: ¿Cuándo cierra una semana y cómo cuenta una semana sin plan para la racha, la calidad de novatos y FR-020? → A: Una semana cierra al terminar el domingo (23:59:59, Buenos Aires); una semana cerrada sin plan cuenta como semana sin Completada y corta la racha; un novato con menos de 3 semanas cerradas con plan no es elegible para calidad.
- Q: ¿El volumen incluye km implícitos (entrada en calor, vuelta a la calma)? → A: No; el volumen es solo la suma de los km de los bloques y tramos de trote explícitos; una entrada en calor o vuelta a la calma debe venir como bloque de trote (cuenta) o de caminata (no cuenta).
- Q: ¿Qué reglas verifica SC-001 sobre cada plan entregado? → A: Una lista cerrada: topes (FR-018, FR-019, FR-020, tope de descarga de FR-021, FR-025), calidad (FR-022, FR-023), ritmo (FR-024), reclasificación pendiente (FR-042) y pisos (AC-66, piso y vuelta de la descarga) con la tolerancia de FR-026, salvo que un tope vigente impida alcanzarlos.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Crear cuenta y cargar perfil de corredor (Priority: P1)

Milena, Mich o Pepe se registran con email y contraseña, inician sesión y cargan su perfil: nivel
(novato, intermedio o avanzado), frecuencia semanal, distancia objetivo, ritmo actual, ciudad, rango
horario preferido y hora de envío del mensaje diario. El sistema valida cada dato y rechaza lo que esté
fuera de rango sin guardar nada.

**Why this priority**: sin cuenta ni perfil válido no existe ningún cálculo de entrenamiento posible; es
la base de todas las demás historias y donde se aplica la regla de no inventar datos.

**Independent Test**: registrar una cuenta, iniciar sesión, cargar un perfil válido, consultarlo y
verificar que devuelve los valores guardados; enviar datos inválidos y verificar que se rechazan sin
cambios.

**Acceptance Scenarios**:

1. **Given** un email no registrado con formato válido y una contraseña de 8 a 128 caracteres, **When** el usuario se registra, **Then** la cuenta se crea (AC-01).
2. **Given** un email ya registrado, **When** alguien intenta registrarse con él, **Then** se rechaza como conflicto sin crear otra cuenta (AC-02).
3. **Given** un email con formato inválido o una contraseña fuera de 8-128 caracteres, **When** el usuario se registra, **Then** se rechaza por datos inválidos sin crear la cuenta (AC-72).
4. **Given** credenciales correctas, **When** el usuario inicia sesión, **Then** recibe un token de sesión que vence a las 2 horas (AC-03); con credenciales incorrectas no recibe token (AC-04).
5. **Given** un token vigente emitido hace menos de 7 días desde el login, **When** hace una operación autenticada, **Then** recibe un token renovado por 2 horas más; si el login original tiene 7 días o más, se le niega el acceso (AC-05).
6. **Given** una operación autenticada sin token, con token inválido o vencido, **When** llega al sistema, **Then** se rechaza como no autenticada sin devolver datos (AC-73).
7. **Given** un usuario autenticado, **When** carga datos de perfil válidos, **Then** se guardan y una consulta posterior devuelve los valores nuevos (AC-06, AC-51).
8. **Given** un usuario autenticado, **When** envía algún dato de perfil fuera de los rangos o formatos definidos, **Then** se rechaza sin guardar ningún cambio (AC-07).

---

### User Story 2 - Vincular la cuenta con Telegram (Priority: P1)

El usuario pide un código de vinculación de un solo uso y lo envía al bot de Telegram. A partir de ahí,
ese chat queda asociado a su cuenta y es el canal por el que recibe planes y mensajes diarios.

**Why this priority**: Telegram es el único canal de entrega del producto; sin vínculo no se genera plan
ni se envían mensajes.

**Independent Test**: generar un código, enviarlo al bot dentro de los 15 minutos y verificar el
vínculo; reintentar con el mismo código, con uno vencido y con un segundo chat, y verificar los rechazos.

**Acceptance Scenarios**:

1. **Given** un código de vinculación generado hace menos de 15 minutos, **When** el usuario lo envía al bot, **Then** el chat queda asociado a su cuenta y el código no puede volver a usarse (AC-44).
2. **Given** un código inválido, ya usado o con más de 15 minutos, **When** se envía al bot, **Then** se rechaza sin asociar ningún chat (AC-45).
3. **Given** un chat ya vinculado a una cuenta, o una cuenta que ya tiene chat, **When** se intenta un segundo vínculo con un código válido, **Then** se rechaza sin modificar el vínculo existente (AC-46).

---

### User Story 3 - Recibir un plan semanal seguro y progresivo (Priority: P1)

Con el perfil completo y Telegram vinculado, el usuario obtiene su plan de la semana (lunes a domingo):
lo pide cuando no tiene uno para la semana en curso, o el sistema lo genera automáticamente cada lunes.
El plan lo propone un modelo de lenguaje y, antes de entregarse, pasa siempre por guardarraíles
deterministas de carga: topes iniciales, tope de aumento del 10%, semana de descarga, límite de sesiones
de calidad, límite de ritmo y límite por distancia objetivo.

**Why this priority**: es el valor central del producto (resolver "qué hacer, cuándo y cómo" sin riesgo
de lesión) y donde se mide la meta de 100% de planes dentro de los guardarraíles.

**Independent Test**: con un perfil completo, pedir el plan y verificar que cada sesión y el total semanal
respetan los topes; con un doble del modelo que proponga cargas excesivas, verificar que el plan
entregado queda recortado según las reglas.

**Acceptance Scenarios**:

1. **Given** un usuario de nivel intermedio o avanzado sin ritmo actual, **When** pide un plan, **Then** se rechaza con "No hay datos sobre tu ritmo cargados en tu perfil" sin crear plan (AC-08).
2. **Given** un usuario al que le falta nivel, frecuencia, distancia objetivo, ciudad, rango horario u hora de envío, **When** pide un plan, **Then** se rechaza con "No hay datos sobre tu {campo} cargados en tu perfil" sin crear plan (AC-09).
3. **Given** un novato sin ritmo actual con el resto del perfil completo, **When** pide un plan, **Then** el plan se genera sin exigir ritmo (AC-10).
4. **Given** un usuario sin chat de Telegram vinculado, **When** pide un plan, **Then** se rechaza con "Tu cuenta no tiene un chat de Telegram vinculado" sin crear plan (AC-11).
5. **Given** un usuario con perfil completo, chat vinculado y sin plan para la semana en curso, **When** pide un plan, **Then** se crea (AC-56); si lo pide a mitad de semana, el plan cubre desde ese día hasta el domingo (AC-57).
6. **Given** un usuario que ya tiene plan para la semana en curso, **When** pide otro, **Then** se rechaza como conflicto sin generar uno nuevo (AC-58).
7. **Given** una corredora novata, **When** se genera su plan, **Then** cada sesión de la primera semana explicita bloques alternados de caminata y trote con la distancia en km de cada bloque (AC-14).
8. **Given** un perfil intermedio o avanzado, **When** se genera una sesión de calidad, **Then** el plan explicita el tiempo objetivo por tramo y el tiempo de recuperación entre tramos (AC-15).
9. **Given** un usuario con frecuencia N, **When** se genera un plan de semana completa, **Then** tiene exactamente N sesiones en días distintos (AC-65).
10. **Given** un usuario que no tuvo plan la semana anterior, **When** se genera el plan, **Then** ninguna sesión supera el tope inicial de su nivel (novato 2 km, intermedio 5 km, avanzado 10 km de trote) y el total semanal no supera ese tope × frecuencia (AC-61).
11. **Given** un plan propuesto que aumenta el volumen más de 10% sobre el volumen planificado de la semana anterior, **When** se aplican los guardarraíles, **Then** el plan se recorta al tope del 10% sin ningún piso que lo supere; solo cuentan los km de trote (AC-18).
12. **Given** un usuario con perfil sin cambios cuya semana anterior fue completa, no de descarga y con al menos 1 sesión Completada, **When** se genera un plan que no es de descarga, **Then** el volumen es mayor o igual al de la semana anterior y no lo supera en más de 10% (AC-66).
13. **Given** un usuario cuya semana anterior no tuvo ninguna sesión Completada, **When** se genera el plan, **Then** el volumen no supera el planificado de esa semana (AC-63).
14. **Given** un usuario cuyo plan anterior fue parcial y sin ninguna semana completa previa, **When** se genera el plan siguiente, **Then** aplica el tope inicial y no el del 10% (AC-62); si tiene una semana completa previa, el tope del 10% se calcula sobre su última semana completa (AC-74).
15. **Given** 4 semanas consecutivas con al menos 1 sesión Completada en cada una, **When** se genera la semana 5, **Then** el volumen baja entre 20% y 30% respecto del planificado en la semana 4 (AC-19a); en la semana 6 el volumen vuelve a igualar el de la semana 4, exento del tope del 10%, salvo que la semana de descarga no haya tenido ninguna sesión Completada (AC-19d).
16. **Given** una racha de semanas con sesiones Completadas, **When** cierra una semana sin ninguna, **Then** la racha vuelve a 0 (AC-19b); tras una descarga, el conteo reinicia desde la semana siguiente (AC-19c).
17. **Given** un novato sin ritmo actual, o con alguna de sus últimas 3 semanas cerradas sin sesión Completada o con una sesión Parcial/Cortada de RPE ≥ 7, **When** se genera su plan, **Then** no incluye sesiones de calidad (AC-20).
18. **Given** cualquier perfil, **When** se genera el plan, **Then** incluye como máximo una sesión de calidad por semana (AC-21), y toda sesión de calidad no permitida se convierte en suave con un único bloque de trote con los mismos km de trote totales, sin tramos, recuperaciones ni ritmo objetivo (AC-77).
19. **Given** un ritmo actual cargado, **When** se genera una sesión de calidad, **Then** su ritmo objetivo está entre el ritmo actual y ese ritmo reducido un 5,6% (p. ej., con 6:00 min/km, entre 6:00 y 5:40) (AC-22).
20. **Given** una distancia objetivo D, **When** se genera el plan, **Then** ninguna sesión supera D km de trote (AC-67).
21. **Given** una sesión propuesta de 8 km con tope por sesión de 5 km y un total semanal sobre su tope, **When** se aplican los guardarraíles, **Then** primero se multiplica cada bloque de trote de esa sesión por 5/8, luego todos los bloques de trote por el factor semanal calculado sobre el volumen ya recortado, redondeando hacia abajo a 0,01 km, sin cambiar caminata, recuperaciones ni ritmo, y recalculando el tiempo de cada tramo (AC-76).
22. **Given** un usuario con perfil completo y chat vinculado, **When** llega el lunes, **Then** su plan se genera antes de su hora de envío y se le envía por Telegram un resumen con día, tipo y km de trote de cada sesión (AC-59); con perfil incompleto o sin chat no se genera ninguno (AC-60).
23. **Given** que el modelo falla, no responde en 20 segundos o devuelve una propuesta estructuralmente inválida, **When** el usuario pide el plan, **Then** se le informa "No es posible generar un plan en este momento." sin crear plan (AC-17); en la generación automática del lunes, si tiene plan previo se adopta su último plan válido (mismos días y sesiones), se le aplican los guardarraíles de la semana actual, y se entrega con el aviso "Generación de un nuevo plan no disponible: te enviamos tu último plan válido." (AC-16), y si no tiene, se le envía "No es posible generar un plan en este momento." (AC-17b).

---

### User Story 4 - Recibir el mensaje diario ajustado por fatiga (Priority: P1)

Los días con sesión, a la hora elegida, el bot le pregunta al usuario su fatiga (1-10). Con la respuesta
(o tras 2 horas sin ella), le envía un mensaje breve con la sesión del día: tipo, horario sugerido, ritmo
objetivo si es de calidad y secuencia de caminata/trote si aplica. Si reporta fatiga alta, la sesión del
día se vuelve suave.

**Why this priority**: es el punto de contacto diario y donde se mide la meta de 90% de mensajes
entregados; convierte el plan en una acción concreta para el día.

**Independent Test**: con un plan vigente y una sesión hoy, simular la llegada de la hora de envío,
responder la fatiga y verificar el contenido, la extensión y el tiempo de entrega del mensaje.

**Acceptance Scenarios**:

1. **Given** una sesión planificada hoy que no está "Pospuesta por clima", **When** llega la hora de envío, **Then** el bot pregunta la fatiga (1-10) y no envía el mensaje hasta recibirla, esperando como máximo 2 horas; luego envía la sesión sin ajuste por fatiga (AC-47).
2. **Given** una respuesta de fatiga que no es un entero de 1 a 10, **When** llega al bot, **Then** vuelve a preguntar sin enviar el mensaje, y la espera de 2 horas sigue contando desde la primera pregunta (AC-75).
3. **Given** una fatiga ≥ 8, **When** se define la sesión del día, **Then** la sesión es de intensidad "suave/recuperación" (si era de calidad, queda un único bloque de trote con los mismos km, sin ritmo objetivo) (AC-48); si ya era suave, conserva sus bloques y km y el mensaje indica que se mantiene suave por la fatiga (AC-80).
4. **Given** una sesión del día, **When** se emite el mensaje, **Then** tiene 150 palabras o menos (AC-27) e incluye tipo de sesión y un rango horario dentro del preferido; si es de calidad, el ritmo objetivo; si tiene caminata y trote, la secuencia (AC-28).
5. **Given** un texto redactado por el modelo que está vacío, supera 150 palabras, omite algún dato obligatorio, contiene números ajenos a la sesión, preguntas o formato markdown, **When** se valida, **Then** se descarta y se envía el mensaje de plantilla (AC-78).
6. **Given** que el modelo falla o no responde en 5 segundos, **When** se emite el mensaje, **Then** se envía el de plantilla (que cumple AC-27 y AC-28) y se registra el fallo (AC-79).

---

### User Story 5 - Adaptar la sesión al clima (Priority: P2)

Pepe recibe, junto con su sesión, una alerta si dentro de su rango horario preferido se esperan lluvia
probable o calor extremo, con un día alternativo dentro de la semana. Si el clima es extremo y no hay
alternativa, la sesión queda "Pospuesta por clima" y se le informa sin preguntarle la fatiga.

**Why this priority**: diferencia el producto frente a un plan estático y evita salir a correr en
condiciones riesgosas, pero el plan y el mensaje diario aportan valor aun sin él.

**Independent Test**: con un doble del servicio de pronóstico, simular días con lluvia > 60%,
temperatura > 32 °C, condiciones extremas y fallas del servicio, y verificar alertas, alternativas,
posposiciones y mensajes.

**Acceptance Scenarios**:

1. **Given** un pronóstico con máximo de lluvia > 60% o temperatura > 32 °C dentro del rango preferido del día, **When** se evalúa la sesión a la hora de envío (antes de preguntar la fatiga), **Then** el mensaje incluye una alerta con el motivo climático (AC-23) y como alternativa el primer día dentro de los 3 siguientes, sin pasar del domingo, sin condición desfavorable; si no hay, dice "No hay una alternativa disponible esta semana" (AC-24).
2. **Given** condición desfavorable sin día alternativo, **When** se emite el mensaje, **Then** no se ofrece reprogramar y la sesión sigue siendo ejecutable (AC-64).
3. **Given** condición desfavorable con día alternativo, **When** se emite el mensaje, **Then** el mensaje informa el motivo y el día alternativo sin pedir confirmación ni ofrecer reprogramar, y la sesión original sigue ejecutable (limitación aceptada; AC-25 y AC-26 fuera de esta iteración).
4. **Given** un día con condición extrema (> 38 °C, tormenta eléctrica o lluvia > 80% en el rango preferido) y sin alternativa libre de condición desfavorable, **When** se evalúa a la hora de envío, **Then** la sesión queda "Pospuesta por clima" y no se ofrece como ejecutable (AC-40).
5. **Given** una sesión "Pospuesta por clima", **When** llega la hora de envío, **Then** se envía un único mensaje de 150 palabras o menos con la posposición y su motivo, sin preguntar la fatiga (AC-68); si en la semana hay 2 o más pospuestas, el mensaje informa la cantidad (AC-43).
6. **Given** una sesión "Pospuesta por clima", **When** se evalúa la reclasificación por RPE o se genera el plan siguiente, **Then** no dispara reclasificación (AC-41), no se recupera su volumen y la base del tope del 10% no la descuenta (AC-42).
7. **Given** una falla del servicio de pronóstico (timeout, límite de uso o error del servidor), **When** se prepara la sesión diaria, **Then** se registra el fallo (AC-12) y el mensaje se envía sin ajuste climático e incluye "Clima no disponible: seguí las pautas base de ritmo e hidratación." (AC-13).

---

### User Story 6 - Registrar cómo salió la sesión (Priority: P2)

Después de entrenar, el usuario registra desde el chat de Telegram el estado de la sesión del día
(Completada, Parcial/Cortada o Salteada), su esfuerzo percibido (RPE 1-10, salvo si la salteó) y notas
opcionales. Si la cortó con RPE ≥ 7, las dos sesiones siguientes pasan a ser suaves.

**Why this priority**: alimenta la adaptación del plan (descarga, progresión, calidad para novatos) y la
meta de 70% de semanas con al menos una sesión registrada.

**Independent Test**: con una sesión hoy, registrar cada estado con y sin RPE/notas y verificar lo que se
guarda, los rechazos y la reclasificación de las dos sesiones siguientes.

**Acceptance Scenarios**:

1. **Given** una sesión planificada hoy, **When** el usuario la registra como Completada o Parcial/Cortada con RPE de 1 a 10, **Then** se guarda y aparece en su historial (AC-29); como Salteada sin RPE, también (AC-30).
2. **Given** un registro Completada o Parcial/Cortada sin RPE, o con RPE fuera de 1-10, **When** se valida, **Then** se rechaza sin guardar (AC-31, AC-32).
3. **Given** una sesión que ya tiene resultado, **When** se intenta registrar otro, **Then** se rechaza como conflicto sin modificar el existente (AC-33).
4. **Given** un registro con o sin notas, **When** se guarda, **Then** se acepta en ambos casos y las notas aparecen en el historial (AC-34).
5. **Given** una sesión cuya fecha no es hoy, **When** el usuario intenta registrarla, **Then** se rechaza sin guardar (AC-69); lo mismo ocurre con una sesión "Pospuesta por clima", que conserva su estado (AC-81).
6. **Given** un chat vinculado al usuario X, **When** intenta registrar una sesión del usuario Y, **Then** el bot lo rechaza sin revelar ni modificar datos de Y (AC-38).
7. **Given** un registro Parcial/Cortada con RPE ≥ 7, **When** se definen las sesiones de los dos días de entrenamiento siguientes, **Then** pasan a "suave/recuperación", eliminando cualquier sesión de calidad en ese rango (AC-39).

---

### User Story 7 - Ver el cronograma de la semana y el historial (Priority: P3)

El usuario consulta su semana en curso (sesiones pasadas, de hoy y próximas) y el historial completo de
sus sesiones con estado, RPE y notas.

**Why this priority**: da visibilidad y motivación, pero el producto funciona aunque el usuario solo use
los mensajes diarios.

**Independent Test**: con un plan y sesiones registradas, sin registrar y pospuestas, consultar el
cronograma y el historial y verificar estados y datos mostrados.

**Acceptance Scenarios**:

1. **Given** un plan semanal activo, **When** el usuario consulta su cronograma, **Then** ve las sesiones de lunes a domingo (pasadas, hoy y proyectadas), y las pasadas sin resultado aparecen como "Sin registrar" (AC-35).
2. **Given** al menos una sesión pasada, **When** consulta su historial, **Then** ve todas sus sesiones anteriores con estado (Completada, Parcial/Cortada, Salteada o Pospuesta por clima), RPE y notas cuando existan; las no registradas figuran como "Sin registrar", que cuenta como no Completada (AC-36).

---

### User Story 8 - Administrar la cuenta (Priority: P3)

El usuario edita su perfil sabiendo cuándo se aplica cada cambio, restablece su contraseña con un código
que le llega por Telegram y puede eliminar definitivamente su cuenta y todos sus datos.

**Why this priority**: necesario para operar a lo largo del tiempo y para el control de los datos
propios, pero no bloquea el flujo principal.

**Independent Test**: editar cada grupo de datos y verificar desde cuándo rigen; restablecer la
contraseña con códigos válidos, vencidos y reutilizados; eliminar la cuenta con y sin confirmación.

**Acceptance Scenarios**:

1. **Given** un plan vigente, **When** el usuario cambia nivel, frecuencia, distancia objetivo o ritmo, **Then** el plan vigente no cambia y el próximo plan usa los valores nuevos (AC-70).
2. **Given** un cambio de ciudad, rango horario u hora de envío, **When** se emite el siguiente mensaje diario, **Then** usa los valores nuevos (AC-71).
3. **Given** un usuario de nivel intermedio o avanzado, **When** cambia su nivel a novato, **Then** el cambio se guarda (AC-55); el cambio de novato a un nivel superior también se acepta sin restricciones en esta iteración (RF-20 fuera de alcance).
4. **Given** un usuario con Telegram vinculado que pide restablecer su contraseña desde el bot, **When** envía el código recibido junto con una contraseña nueva de 8 a 128 caracteres dentro de los 30 minutos, **Then** la contraseña se actualiza y el código no puede reutilizarse (AC-49); con código inválido, usado o vencido, no se modifica (AC-50).
5. **Given** un pedido de eliminación sin confirmación explícita, **When** se recibe, **Then** se responde con una advertencia de que la eliminación es definitiva, sin borrar nada (AC-52).
6. **Given** un pedido de eliminación confirmado, **When** se procesa, **Then** se borran perfil, planes, historial y vínculo de Telegram, y tanto un nuevo login con esas credenciales como un token aún vigente son rechazados (AC-53).

---

### Edge Cases

- Plan pedido un domingo: cubre solo ese día (AC-57); el plan del lunes siguiente lo trata como semana parcial (AC-62/AC-74).
- Plan parcial con menos días restantes que la frecuencia: tiene una sesión en cada día restante, aunque queden en días consecutivos (FR-016).
- Recorte por topes que deja bloques muy chicos: no hay piso mínimo; se redondea hacia abajo a 0,01 km (AC-18, AC-76). Si un bloque de trote queda en 0,00 km, se conserva así, sin eliminar el bloque ni la sesión (FR-026). La invalidez por km ≤ 0 de FR-027 aplica solo a la propuesta del modelo, no al plan recortado.
- Piso que choca con un tope (p. ej., igualar la semana 4 tras bajar la distancia objetivo): prevalece el tope y el plan queda por debajo del piso (FR-026).
- Novato con ritmo cargado y 3 semanas cerradas que cumplen la condición: puede recibir una sesión de calidad, con ritmo objetivo acotado (AC-20, AC-22).
- Usuario que reduce su frecuencia (p. ej., de 6 a 2): el volumen se mantiene y cada sesión se alarga; el único tope por sesión después de la primera semana es la distancia objetivo (riesgo aceptado en el PRD).
- Semana de descarga sin ninguna sesión Completada: la semana 6 no supera el volumen de la semana 5 (AC-19d, AC-63).
- Semana de descarga, o semana posterior a ella, generada como plan parcial: se aplican los topes pero no los pisos, así que puede bajar más del 30% o quedar por debajo de V4 (FR-021, FR-026).
- Plan adoptado por falla del modelo (AC-16): pasa por los guardarraíles de la semana actual, pero conserva la estructura (días, cantidad de sesiones, tipos) del plan original, que puede reflejar datos de perfil anteriores a una edición (riesgo aceptado).
- Parcial/Cortada con RPE ≥ 7 registrada el sábado o el domingo: las sesiones que falten para completar 2 se reclasifican en el plan de la semana siguiente al generarse (FR-042).
- Respuesta de fatiga que llega pasadas las 2 horas: el mensaje ya se envió sin ajuste; no se reenvía.
- Plan pedido después de la hora de envío con una sesión hoy: la pregunta de fatiga llega en el minuto siguiente. Sesión de hoy ya registrada antes de la hora de envío: no se envía mensaje diario (FR-029).
- Clima evaluado a la hora de envío: el mensaje puede usar un pronóstico de hasta 2 horas antes (riesgo aceptado).
- Usuario que corrió igual una sesión "Pospuesta por clima": no puede registrarla; la sesión no cuenta como Completada para la racha ni para la calidad de novatos.
- Dos sesiones "Pospuesta por clima" en la misma semana: el mensaje de posposición informa la cantidad (AC-43).
- Día alternativo informado que ya tiene sesión: no hay movimiento de sesiones; el día alternativo es solo informativo.
- Novato cuyo primer plan es parcial, o intermedio/avanzado que baja a novato: sus planes alternan caminata y trote hasta su primer plan de semana completa como novato, inclusive (FR-015).
- Novato que sube de nivel por edición del perfil: deja de aplicar los guardarraíles de novato (calidad y tope inicial de 2 km) desde el próximo plan (riesgo aceptado en el PRD).
- Acceso a recursos de otro usuario: se deniega como prohibido sin revelar datos (AC-37, AC-38).
- Usuario que elimina su perfil: sus semanas dejan de contar como "semanas con plan vigente" para la métrica de registro.
- Hora de envío igual o posterior al fin del rango horario preferido, o rango menor a 1 hora: se rechaza al cargar el perfil (AC-07).

## Requirements *(mandatory)*

### Functional Requirements

**Cuenta y sesión**

- **FR-001**: El sistema MUST permitir registrarse con email de formato válido y contraseña de 8 a 128 caracteres, rechazando emails ya registrados y datos inválidos sin crear cuenta (RF-01; AC-01, AC-02, AC-72).
- **FR-002**: El sistema MUST autenticar con email y contraseña emitiendo un token de sesión que vence a las 2 horas, sin emitir token ante credenciales incorrectas (RF-02a; AC-03, AC-04).
- **FR-003**: El sistema MUST entregar un token renovado (2 horas desde ese momento) en cada operación autenticada válida, hasta 7 días desde el login original; pasado ese límite, o sin token o con token inválido o vencido, MUST rechazar la operación sin devolver datos (RF-02b; AC-05, AC-73).
- **FR-004**: El sistema MUST almacenar las contraseñas solo como hash Argon2id con parámetros mínimos m=19456 KiB, t=2, p=1 (RNF-03).

**Perfil**

- **FR-005**: El sistema MUST permitir cargar y editar: nivel (novato, intermedio, avanzado, autodeclarado); frecuencia (entero 1-7); distancia objetivo (1 a 42,2 km); ritmo actual (mm:ss por km, entre 3:00 y 10:00); ciudad (texto no vacío de hasta 100 caracteres); rango horario preferido (HH:MM inicio < fin, duración mínima 1 hora); y hora de envío (HH:MM, anterior al fin del rango); todos los horarios en zona horaria de Buenos Aires (RF-03a a RF-03g, RF-18a; AC-06, AC-51).
- **FR-006**: El sistema MUST rechazar una edición de perfil con cualquier dato fuera de rango o formato sin persistir ningún cambio (AC-07).
- **FR-007**: El sistema MUST aplicar los cambios de nivel, frecuencia, distancia objetivo y ritmo recién en el próximo plan generado, sin modificar el vigente (RF-18b; AC-70), y los de ciudad, rango horario y hora de envío desde el siguiente mensaje diario (RF-18c; AC-71).
- **FR-008**: El sistema MUST aceptar cualquier cambio de nivel válido, incluido el de novato a intermedio o avanzado; la restricción de RF-20 / AC-54 queda fuera de esta iteración como limitación aceptada (AC-55; Riesgos del PRD).
- **FR-009**: El sistema MUST permitir eliminar definitivamente el perfil y todos los datos del usuario (perfil, planes, historial, vínculo de Telegram) solo con confirmación explícita, advirtiendo que la acción no se puede deshacer; tras eliminarlo, las credenciales y los tokens vigentes de ese usuario dejan de ser válidos (RF-19; AC-52, AC-53).
- **FR-010**: El sistema MUST permitir restablecer la contraseña mediante un código de un solo uso enviado por el bot vinculado, válido por 30 minutos, que se presenta junto con una contraseña nueva de 8 a 128 caracteres; códigos inválidos, usados o vencidos no modifican la contraseña (RF-17; AC-49, AC-50).

**Telegram**

- **FR-011**: El sistema MUST vincular una cuenta con un chat de Telegram mediante un código de un solo uso válido por 15 minutos, con relación uno a uno entre cuenta y chat y sin desvinculación; rechaza códigos inválidos, usados o vencidos y segundos vínculos sin alterar el existente (RF-14; AC-44, AC-45, AC-46).

**Generación del plan**

- **FR-012**: Antes de cualquier cálculo de entrenamiento, el sistema MUST verificar que el perfil tenga nivel, frecuencia, distancia objetivo, ciudad, rango horario, hora de envío, chat de Telegram vinculado y, si el nivel no es novato, ritmo actual; si falta alguno MUST rechazar la solicitud con el mensaje correspondiente, sin inventar datos ni crear plan (RF-04; AC-08, AC-09, AC-10, AC-11).
- **FR-013**: El sistema MUST generar a pedido del usuario el plan de la semana en curso cuando no tenga uno, rechazando como conflicto un segundo pedido para la misma semana; si se genera a mitad de semana, cubre desde ese día hasta el domingo (RF-21; AC-56, AC-57, AC-58).
- **FR-014**: El sistema MUST generar automáticamente cada lunes, antes de la hora de envío de cada usuario, el plan de la semana para quienes tengan perfil completo y chat vinculado, y ninguno para el resto; el plan generado automáticamente (o adoptado por FR-027) MUST enviarse por Telegram como resumen con día, tipo y km de trote de cada sesión. El plan pedido a demanda (FR-013) se devuelve solo en la respuesta y no se envía por Telegram (RF-22; AC-16, AC-59, AC-60).
- **FR-015**: El plan MUST ser progresivo según el nivel, lo que se cumple con los guardarraíles de FR-018 a FR-026 (en particular el piso de AC-66) sin otra regla de progresión; después de la primera semana de un novato, alternar caminata y trote queda a criterio del modelo y no se valida; para novatos, cada sesión de la primera semana (todo plan de un novato hasta su primer plan de semana completa como novato, inclusive; solo cuentan los planes cuyo perfil al generarse era novato) MUST explicitar bloques alternados de caminata y trote con km por bloque; cada sesión de calidad MUST explicitar tiempo objetivo por tramo y tiempo de recuperación entre tramos (RF-06a; AC-14, AC-15).
- **FR-016**: Un plan de semana completa MUST tener exactamente tantas sesiones como la frecuencia cargada, cada una en un día distinto (AC-65); un plan parcial MUST tener exactamente min(frecuencia, días restantes hasta el domingo, incluido el de generación) sesiones, una por día (AC-57). Excepción: el plan adoptado por FR-027 conserva los días y la cantidad de sesiones del plan original (riesgo aceptado en el PRD).
- **FR-017**: El sistema MUST aplicar, de forma determinista y antes de entregar cualquier plan, todos los guardarraíles de carga de FR-018 a FR-025; ningún plan se entrega sin pasar por ellos (RF-06b a RF-06k; Qué NO hacer).
- **FR-018**: **Tope inicial**: si el usuario no tuvo plan la semana anterior, o ese plan fue parcial y no tiene ninguna semana completa previa, cada sesión MUST tener como máximo 2 km (novato), 5 km (intermedio) o 10 km (avanzado) de trote, y el total semanal como máximo ese tope × frecuencia (RF-06g; AC-61, AC-62).
- **FR-019**: **Tope del 10%**: el volumen semanal (suma de los km de los bloques y tramos de trote explícitos de las sesiones; la caminata no cuenta y no hay km implícitos: una entrada en calor o vuelta a la calma cuenta solo si viene como bloque de trote) MUST no superar en más de 10% el volumen planificado de la semana anterior, tomado del plan tal como se generó; si esa semana fue parcial, la base es la última semana completa; no hay piso mínimo que lo supere; las semanas van de lunes a domingo (RF-06b; AC-18, AC-74). Si la semana anterior fue completa, no de descarga, tuvo al menos 1 sesión Completada y el perfil no cambió, el volumen de un plan que no es de descarga MUST además ser mayor o igual al de esa semana (AC-66).
- **FR-019a**: **Semana cerrada**: una semana (lunes 00:00 a domingo 23:59:59, Buenos Aires) está cerrada cuando terminó su domingo. Para la racha de FR-021 y la elegibilidad de FR-022, una semana cerrada sin plan cuenta como semana sin ninguna sesión Completada (RF-06c, RF-06d; AC-19b, AC-20).
- **FR-020**: **Sin aumento tras semana vacía**: si la semana anterior no tuvo ninguna sesión Completada, el volumen semanal MUST no superar el planificado de esa semana (RF-06h; AC-63).
- **FR-021**: **Descarga**: tras 4 semanas consecutivas con al menos 1 sesión Completada cada una (la primera semana, aunque sea parcial, cuenta si tiene una), la semana siguiente MUST reducir el volumen entre 20% y 30% respecto de la cuarta; la racha vuelve a 0 al cerrar una semana sin sesión Completada, incluida una semana sin plan (FR-019a), y reinicia tras la descarga; la semana posterior a la descarga MUST igualar el volumen de la semana previa a la descarga (con la tolerancia de FR-026), exenta del tope del 10%, salvo que la descarga no haya tenido ninguna sesión Completada, en cuyo caso rige FR-020 (RF-06c; AC-19a a AC-19d). Los pisos de esta regla (reducción máxima del 30% e igualación de la semana posterior) aplican solo a planes de semana completa; un plan parcial de descarga respeta solo el tope de reducción mínima del 20% y uno parcial posterior a la descarga, solo los topes vigentes (FR-026).
- **FR-022**: **Calidad para novatos**: un novato MUST no recibir sesiones de calidad salvo que tenga ritmo actual cargado y cada una de sus últimas 3 semanas cerradas (FR-019a) tenga plan, al menos 1 sesión Completada y ninguna Parcial/Cortada con RPE ≥ 7; con menos de 3 semanas cerradas con plan no es elegible. Sesión de calidad = toda sesión con al menos un tramo con ritmo objetivo (ritmo, velocidad o intervalos), cuyo ritmo está acotado por FR-024; sesión suave = toda sesión sin ningún tramo con ritmo objetivo. La clasificación es estructural y no depende de que el perfil tenga ritmo actual (RF-06d; AC-20).
- **FR-023**: **Máximo una de calidad**: todo plan MUST tener como máximo 1 sesión de calidad por semana; las sesiones de calidad no permitidas (por FR-022 o posteriores a la primera de la semana) MUST convertirse en suaves con un único bloque de trote con los mismos km de trote totales, sin recuperaciones ni ritmo objetivo (RF-06e, RF-06k; AC-21, AC-77).
- **FR-024**: **Ritmo de calidad**: el ritmo objetivo de cada tramo de una sesión de calidad MUST estar entre el ritmo actual y ese ritmo reducido un 5,6%, con el límite rápido redondeado al segundo hacia el lado más lento (p. ej., 6:00 → 360 s × 0,944 = 339,84 s → 5:40). Un tramo fuera del rango MUST acotarse al límite más cercano, recalculando su tiempo objetivo como distancia × ritmo nuevo, sin cambiar sus km (RF-06f; AC-22, AC-83).
- **FR-025**: **Tope por distancia objetivo**: ninguna sesión MUST superar en km de trote la distancia objetivo del usuario (RF-06i; AC-67).
- **FR-026**: **Recorte**: cuando una sesión o un plan supera un tope, el sistema MUST multiplicar cada bloque o tramo de trote por un mismo factor (tope ÷ km de la sesión, o tope ÷ volumen semanal), redondeando cada distancia hacia abajo a 0,01 km, sin modificar caminata, recuperaciones ni ritmo objetivo, y recalculando el tiempo objetivo de cada tramo como distancia nueva × ritmo objetivo; los topes por sesión se aplican antes que los semanales (RF-06j; AC-76). Un bloque o tramo que queda en 0,00 km se conserva, sin mínimo y sin eliminar bloques ni sesiones. **Escalado a pisos**: los pisos aplican solo a planes de semana completa; en un plan parcial rigen únicamente los topes. Si el volumen queda por debajo de un piso (FR-019 respecto de la semana anterior, 70% de la semana base en la descarga, o el volumen a igualar tras la descarga en FR-021), el sistema MUST multiplicar todos los bloques y tramos de trote por piso ÷ volumen con las mismas reglas de redondeo y recálculo; el escalado MUST NOT superar ningún tope vigente (por sesión ni semanal): si un tope impide llegar al piso, prevalece el tope. Un piso se considera cumplido si el volumen queda por debajo de él como máximo 0,01 km por bloque o tramo de trote del plan (RF-06l; AC-19a, AC-19d, AC-66, AC-82).
- **FR-027**: Si el modelo de lenguaje falla, no responde en 20 segundos o devuelve una propuesta estructuralmente inválida (cantidad de sesiones distinta de la exigida por FR-016, dos sesiones el mismo día, días fuera del rango del plan, sesiones sin bloques de trote, bloques sin km o con km ≤ 0, ritmo objetivo fuera de 1:00–20:00 min/km, recuperación negativa, una sesión con 2 o más tramos con ritmo a la que le falta la recuperación entre tramos (FR-015), o, en la primera semana de un novato, una sesión que no alterna caminata y trote o que tiene algún tramo con ritmo objetivo (FR-015, FR-022)), registrando el motivo: ante un pedido del usuario, el sistema MUST responder "No es posible generar un plan en este momento." sin crear plan (AC-17); en la generación automática del lunes, MUST adoptar el último plan válido del usuario (mismos días y sesiones), aplicarle todos los guardarraíles de la semana actual (FR-018 a FR-026 y la reclasificación pendiente de FR-042; RF-06a a RF-06l) y avisarle "Generación de un nuevo plan no disponible: te enviamos tu último plan válido." (AC-16), o enviarle "No es posible generar un plan en este momento." si no tiene plan previo (AC-17b).
- **FR-028**: La información del historial que se use para generar planes MUST limitarse a resúmenes semanales, nunca sesiones individuales ni historiales completos (Riesgos del PRD; Qué NO hacer).

**Mensaje diario y fatiga**

- **FR-029**: Los días con sesión planificada que no esté "Pospuesta por clima", a la hora de envío, el sistema MUST preguntar por Telegram el nivel de fatiga (1-10) y esperar la respuesta hasta 2 horas desde la primera pregunta, repreguntando ante respuestas que no sean un entero de 1 a 10; sin respuesta a tiempo, envía la sesión sin ajuste por fatiga. Si el plan se crea después de la hora de envío del día, el flujo arranca en el minuto siguiente; si la sesión de hoy ya tiene resultado registrado, no se envía nada (RF-15, RF-08; AC-47, AC-75).
- **FR-030**: Con fatiga ≥ 8, la sesión del día MUST ser "suave/recuperación"; si era de calidad, se convierte como en FR-023 (un único bloque de trote con los mismos km de trote totales, sin tramos, recuperaciones ni ritmo objetivo); si ya era suave, conserva bloques y km y el mensaje indica que se mantiene suave por la fatiga; el ajuste afecta solo el mensaje del día, no el plan guardado (RF-16, RF-16b; AC-48, AC-80).
- **FR-031**: El mensaje diario MUST tener como máximo 150 palabras e incluir tipo de sesión y un rango horario sugerido dentro del preferido; si es de calidad, el ritmo objetivo; si tiene caminata y trote, la secuencia; y, cuando correspondan, la alerta climática, el día alternativo y los textos fijos de clima no disponible o sin alternativa (RF-08; AC-27, AC-28).
- **FR-032**: El mensaje diario MUST redactarse con el modelo de lenguaje a partir de los datos de la sesión, y MUST reemplazarse por un mensaje de plantilla con esos mismos datos cuando el modelo falla, no responde en 5 segundos, o su texto está vacío, supera 150 palabras, omite un dato obligatorio, contiene números ajenos a la sesión, preguntas o formato markdown (RF-08b; AC-78, AC-79).
- **FR-033**: Las instrucciones al modelo de lenguaje para el plan y para el mensaje diario MUST prohibir explícitamente dar consejo médico o de lesiones, y un test MUST verificarlo. El riesgo residual de que el texto libre del modelo lo incluya igual es una limitación aceptada (Qué NO hacer; Fuera de Alcance; Riesgos del PRD).

**Clima**

- **FR-034**: El sistema MUST consultar el pronóstico de la ciudad del usuario a la hora de envío, antes de preguntar la fatiga, y evaluar el máximo pronosticado dentro del rango horario preferido del día de la sesión (RF-05; AC-23).
- **FR-035**: Con probabilidad de lluvia > 60% o temperatura > 32 °C (condición desfavorable), el mensaje MUST incluir una alerta con el motivo y como alternativa el primer día, dentro de los 3 siguientes y sin pasar del domingo, sin condición desfavorable en su rango preferido; si no hay, MUST decir "No hay una alternativa disponible esta semana" y la sesión sigue ejecutable sin ofrecer reprogramar (RF-07a; AC-23, AC-24, AC-64).
- **FR-036**: Con día alternativo disponible, el mensaje MUST solo informar el motivo y el día alternativo, sin pedir confirmación ni reprogramar, y la sesión original MUST seguir ejecutable; la confirmación de RF-07a (AC-25) y la reprogramación de RF-07b (AC-26) quedan fuera de esta iteración como limitación aceptada (RF-07a; Riesgos del PRD).
- **FR-037**: Con condición extrema (> 38 °C, tormenta eléctrica o lluvia > 80% en el rango preferido) y sin alternativa libre de condición desfavorable en los 3 días siguientes (sin pasar del domingo), el sistema MUST asignar el estado "Pospuesta por clima", que no es seleccionable por el usuario ni ejecutable, no recupera su volumen en otro día, no descuenta la base del tope del 10% y no dispara la reclasificación por RPE (RF-13a a RF-13d; AC-40, AC-41, AC-42).
- **FR-038**: El día de una sesión "Pospuesta por clima", a la hora de envío, el sistema MUST enviar un único mensaje de hasta 150 palabras con la posposición y su motivo, sin preguntar la fatiga, indicando la cantidad de pospuestas de la semana cuando sean 2 o más (RF-13e, RF-13f; AC-43, AC-68).
- **FR-039**: Ante una falla del servicio de pronóstico (timeout, límite de uso o error del servidor), el sistema MUST registrar el fallo y enviar la sesión sin ajuste climático con el texto "Clima no disponible: seguí las pautas base de ritmo e hidratación." (AC-12, AC-13).

**Registro de sesiones**

- **FR-040**: El sistema MUST permitir registrar, solo para la sesión del día actual y una única vez, su estado: Completada, Parcial/Cortada (empezó y la dejó) o Salteada (no la empezó), desde el chat de Telegram; un segundo registro se rechaza como conflicto sin modificar el existente, y el registro de una sesión "Pospuesta por clima" se rechaza sin guardar ni cambiar su estado (RF-09a, RF-13b; AC-29, AC-30, AC-33, AC-69, AC-81).
- **FR-041**: El sistema MUST exigir RPE entero de 1 a 10 para Completada y Parcial/Cortada y no solicitarlo para Salteada, y aceptar notas opcionales (RF-09b, RF-09c; AC-31, AC-32, AC-34).
- **FR-042**: Un registro Parcial/Cortada con RPE ≥ 7 MUST reclasificar a "suave/recuperación" las sesiones guardadas de los dos días de entrenamiento siguientes (los dos próximos días con sesión planificada), convirtiendo las de calidad como en FR-023. Si alguno de esos días cae en una semana cuyo plan todavía no existe, la reclasificación queda pendiente y MUST aplicarse a las primeras sesiones de ese plan al generarse, hasta completar 2 sesiones entre ambas semanas (RF-12; AC-39).

**Consulta**

- **FR-043**: El sistema MUST mostrar el cronograma de la semana en curso (lunes a domingo, pasadas, hoy y proyectadas) y el historial de todas las sesiones anteriores con estado, RPE y notas; las sesiones pasadas sin resultado se muestran como "Sin registrar", que no es un estado guardado y cuenta como no Completada (RF-10, RF-11; AC-35, AC-36).

**Privacidad, auditoría y secretos**

- **FR-044**: El sistema MUST denegar como prohibido cualquier acceso a perfil, plan, historial, cronograma o registro de otro usuario, por la API o por el bot, sin revelar ni modificar sus datos (AC-37, AC-38).
- **FR-045**: El sistema MUST registrar en formato estructurado el 100% de: llamadas al modelo (resumen del prompt y respuesta), herramientas invocadas (clima; almacenamiento: una entrada por cada operación de servicio que modifica datos, más el login, no por cada sentencia SQL), guardarraíles aplicados con valor antes y después, asignaciones de "Pospuesta por clima", errores de servicios externos y decisiones de alerta o alternativa climática; sin contraseñas, tokens ni historiales completos (RNF-02).
- **FR-046**: Las credenciales de servicios externos MUST leerse solo del entorno de ejecución, con 0 apariciones en el código y el repositorio (RNF-04).

### Key Entities *(include if feature involves data)*

- **Usuario**: cuenta identificada por email único, con contraseña hasheada; dueño de todos los demás datos.
- **Perfil**: nivel, frecuencia, distancia objetivo, ritmo actual (opcional para novatos), ciudad, rango horario preferido y hora de envío; uno por usuario.
- **Vínculo de Telegram**: asociación uno a uno entre usuario y chat; permanente.
- **Código de un solo uso**: de vinculación (15 min) o de restablecimiento de contraseña (30 min); se invalida al usarse.
- **Plan semanal**: conjunto de sesiones de una semana (lunes a domingo) de un usuario; completo o parcial; volumen planificado al generarse (base de los topes); marca si es de descarga o si fue adoptado por falla del modelo.
- **Sesión**: día, tipo (calidad si tiene algún tramo con ritmo objetivo; si no, suave), intensidad, secuencia de bloques/tramos, ritmo objetivo (si es de calidad) y estado del sistema ("Pospuesta por clima") cuando corresponda.
- **Bloque / Tramo**: unidad dentro de una sesión: caminata o trote, distancia en km (los de trote son la única fuente del volumen), ritmo y tiempo objetivo (tramos de calidad) y recuperación entre tramos.
- **Registro de resultado**: estado (Completada, Parcial/Cortada, Salteada), RPE y notas; uno por sesión, solo el día de la sesión.
- **Respuesta de fatiga**: valor 1-10 del día; ajusta solo el mensaje del día.
- **Resumen semanal**: agregado por semana (volumen planificado, sesiones Completadas, Parciales con RPE ≥ 7, racha, descarga) usado para generar el plan siguiente.
- **Reclasificación pendiente**: cantidad de sesiones (1 o 2) que el plan siguiente debe reclasificar a suave por FR-042; se consume al generarse ese plan.
- **Evento de auditoría**: registro estructurado de llamadas al modelo, herramientas, guardarraíles, decisiones climáticas y errores externos.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los planes entregados (generados o adoptados por FR-027) cumple esta lista cerrada de reglas, verificable sobre el plan guardado: topes inicial (FR-018), del 10% (FR-019), sin aumento tras semana vacía (FR-020), tope de descarga (FR-021) y distancia objetivo (FR-025); calidad para novatos y máximo una de calidad (FR-022, FR-023); ritmo de calidad (FR-024); reclasificación pendiente (FR-042); y pisos de AC-66, de la descarga y de la vuelta tras la descarga, con la tolerancia de FR-026, salvo que un tope vigente impida alcanzarlos.
- **SC-002**: Al menos el 90% de los mensajes diarios programados se entregan al usuario (entregado = Telegram confirma el envío; se mide sobre las filas de envío diario e incluye los avisos de posposición, que reemplazan al mensaje del día).
- **SC-003**: Al menos el 70% de las semanas con plan vigente (semanas con plan generado cuyo usuario no eliminó su perfil) tienen al menos 1 sesión registrada.
- **SC-004**: En el 95% de los casos, con 10 usuarios simultáneos, el usuario recibe su mensaje diario en 10 segundos o menos desde que responde la pregunta de fatiga.
- **SC-005**: El 100% de los mensajes diarios y de posposición tiene 150 palabras o menos e incluye todos los datos obligatorios de la sesión.
- **SC-006**: El 100% de los días con sesión el usuario recibe un mensaje, aunque fallen el modelo de lenguaje o el servicio de pronóstico.
- **SC-007**: 0 casos en que un usuario obtiene o modifica datos de otro usuario.
- **SC-008**: El 100% de los eventos auditables queda registrado, con 0 contraseñas, tokens o credenciales en los registros.
- **SC-009**: 0 credenciales de servicios externos en el código o el historial del repositorio.

## Assumptions

- El canal de entrega es exclusivamente Telegram, el idioma es solo español y el servicio opera solo en Argentina con zona horaria de Buenos Aires; la ciudad no se valida contra una lista (Fuera de Alcance del PRD).
- El nivel lo declara el usuario y no se verifica ni en el alta ni en cambios posteriores (RF-20 fuera de esta iteración); un usuario nuevo puede declararse intermedio o avanzado (riesgo aceptado en el PRD).
- Los códigos de respuesta, rutas y parámetros exactos de la API (p. ej., confirmación explícita de borrado) son los definidos en los AC del PRD; esta spec los referencia por ID y el plan los fija en los contratos.
- Una respuesta de fatiga recibida después de las 2 horas se ignora; no reenvía el mensaje.
- Fuera de alcance: hardware Bluetooth, diagnóstico médico o de lesiones, apps móviles, nutrición, pagos, otros canales e idiomas, importación desde Garmin o Strava, verificación de email, múltiples objetivos y desvinculación o cambio de chat.
- Dependencias externas: servicio de pronóstico meteorológico (OpenWeatherMap), modelo de lenguaje (Gemini), almacenamiento local y la plataforma de bots de Telegram.