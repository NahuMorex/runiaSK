<!--
Sync Impact Report
==================
Version change: (plantilla sin versión) → 1.0.0
Principios modificados: ninguno (ratificación inicial)
Secciones agregadas:
  - Core Principles: I. Lógica de IA aislada; II. Sin secretos en el código;
    III. Alcance limitado al PRD vigente
  - Restricciones técnicas
  - Flujo de desarrollo
  - Governance
Secciones eliminadas:
  - Principios 4 y 5 de la plantilla (el proyecto define tres principios)
Plantillas:
  - ✅ .specify/templates/plan-template.md (Constitution Check con los tres gates)
  - ✅ .specify/templates/spec-template.md (sin cambios necesarios)
  - ✅ .specify/templates/tasks-template.md (sin cambios necesarios)
  - ✅ .specify/templates/checklist-template.md (sin cambios necesarios)
  - N/A .specify/templates/commands/ (no existe)
  - ✅ AGENTS.md / CLAUDE.md (consistentes; sin cambios)
TODOs diferidos: ninguno
-->

# Runia Constitution

## Core Principles

### I. Lógica de IA aislada

Toda la lógica de IA MUST vivir en un único módulo dedicado, separado de la lógica de negocio.

- El SDK del modelo (`google-genai`) MUST importarse solo dentro de ese módulo; ningún otro
  módulo (API, bot, persistencia, guardarraíles) lo importa ni construye prompts.
- El módulo de IA MUST exponer funciones con entradas y salidas tipadas; el resto del sistema
  lo consume solo por esa interfaz.
- Las reglas de negocio (validación de perfil, guardarraíles de carga, reglas de clima, estados
  de sesión) MUST implementarse como código determinista fuera del módulo de IA y aplicarse
  sobre su salida, nunca delegarse al modelo.
- El módulo de IA MUST NOT acceder a la base de datos ni a Telegram directamente.

**Rationale**: la salida del modelo no es confiable por sí sola. Mantenerla aislada permite
testear la lógica de negocio sin llamar al modelo, garantizar que ningún plan se entregue sin
pasar por los guardarraíles y reemplazar el modelo o el proveedor tocando un solo módulo.

### II. Sin secretos en el código

Ningún secreto MUST aparecer en el código ni en el repositorio; las credenciales se leen
únicamente de variables de entorno.

- `GOOGLE_API_KEY`, `TELEGRAM_BOT_TOKEN`, `OPENWEATHER_API_KEY` y `JWT_SECRET` MUST leerse del
  entorno en tiempo de ejecución, sin valores por defecto en el código.
- El archivo `.env` MUST estar en `.gitignore` y MUST NOT commitearse; tampoco se commitean
  secretos en tests, fixtures, ejemplos ni documentación.
- Los logs MUST NOT contener contraseñas, tokens ni API keys.
- Si falta una credencial obligatoria, el componente que la necesita MUST fallar con un error
  explícito en lugar de usar un valor de reemplazo.

**Rationale**: un secreto commiteado queda en el historial de git aunque se borre después y
obliga a rotarlo. Leerlo del entorno mantiene el repositorio publicable y cumple RNF-04.

### III. Alcance limitado al PRD vigente

No se agregan features fuera del PRD vigente (`PRD.md`).

- Toda spec, plan y tarea MUST trazar a al menos un requerimiento (RF/RNF) o criterio de
  aceptación (AC) del PRD vigente.
- Lo listado en "Fuera de Alcance" del PRD MUST NOT implementarse.
- Una funcionalidad nueva MUST incorporarse primero al PRD; recién después puede especificarse
  e implementarse.
- Código, endpoints, comandos del bot o dependencias sin requerimiento que los respalde MUST
  eliminarse o justificarse en "Complexity Tracking" del plan.

**Rationale**: el PRD es la única fuente de verdad del alcance. Cada feature no pedida agrega
superficie a mantener y a testear, y desvía el producto de sus metas medibles.

## Restricciones técnicas

- Python 3.12 gestionado con uv; FastAPI + uvicorn; SQLite mediante `sqlite3` de la stdlib.
- Modelo `gemini-3.5-flash-lite` vía el SDK oficial `google-genai`, sin frameworks de agentes.
- Bot con `python-telegram-bot` en modo polling, dentro del mismo proceso que la API.
- Contraseñas con hash Argon2id; sesión con token JWT.
- Tests con pytest.
- Cambiar cualquier elemento de este stack requiere actualizar `AGENTS.md` y esta sección.

## Flujo de desarrollo

- El trabajo sigue el flujo de Spec Kit: spec → plan → tasks → implementación.
- Todo plan MUST pasar el "Constitution Check" con los tres principios antes de la fase de
  investigación y volver a verificarse después del diseño.
- `uv run pytest` MUST pasar antes de dar por terminada una tarea.
- La lógica de negocio MUST poder testearse sin llamadas reales al modelo ni a servicios
  externos; el módulo de IA se reemplaza por un doble de prueba.
- `AGENTS.md` es la guía operativa de desarrollo (comandos, stack, prohibiciones).

## Governance

Esta constitución prevalece sobre cualquier otra práctica o documento del proyecto. Ante un
conflicto con `AGENTS.md`, una spec o un plan, se corrige el documento en conflicto.

- **Enmiendas**: toda enmienda se hace editando este archivo, con el Sync Impact Report
  actualizado, la revisión de las plantillas dependientes en `.specify/templates/` y la
  aprobación del responsable del proyecto.
- **Versionado**: semántico. MAJOR para eliminar o redefinir un principio de forma
  incompatible; MINOR para agregar un principio o sección o ampliar materialmente una guía;
  PATCH para aclaraciones y correcciones de redacción.
- **Cumplimiento**: cada plan verifica los principios en su "Constitution Check" y cada
  revisión de código confirma que el cambio los respeta. Toda excepción MUST quedar
  documentada y justificada en "Complexity Tracking" del plan; una excepción sin justificar
  bloquea el cambio.

**Version**: 1.0.0 | **Ratified**: 2026-10-13 | **Last Amended**: 2026-10-13
