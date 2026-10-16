# Guardarraíles de carga Checklist: Runia — Planes de entrenamiento para running

**Purpose**: Evaluar si los requerimientos de guardarraíles de carga (topes, descarga, calidad, ritmo, recorte, rachas y semanas parciales) están completos, claros, consistentes y verificables antes de `/speckit-plan`.
**Created**: 2026-10-15
**Feature**: [spec.md](../spec.md)

**Note**: Generado por `/speckit-checklist`. Evalúa la calidad de lo escrito en la spec, no la implementación. Foco: guardarraíles de carga · Profundidad: gate previo al plan · Audiencia: autor.

## Completitud de requerimientos

- [ ] CHK001 - ¿Está definido el orden de aplicación entre todos los guardarraíles (conversión de calidad, ritmo, topes por sesión, topes semanales, descarga, reclasificación pendiente) y no solo "topes por sesión antes que semanales"? [Gap, Spec §FR-017, §FR-026]
- [ ] CHK002 - ¿Se especifica qué hace el sistema cuando el ritmo objetivo propuesto para una sesión de calidad está fuera del rango permitido (acotarlo, convertir la sesión en suave o rechazar el plan)? [Gap, Spec §FR-024]
- [ ] CHK003 - ¿Se especifica cómo se recalcula el tiempo objetivo de los tramos cuando se ajusta el ritmo, y no solo cuando se recorta la distancia? [Gap, Spec §FR-024, §FR-026]
- [ ] CHK004 - ¿Existe un requerimiento para cuando el plan propuesto queda por debajo de un piso (volumen menor al de la semana anterior en AC-66, o reducción de descarga mayor al 30%), dado que el recorte de FR-026 solo reduce? [Gap, Spec §FR-019, §FR-021]
- [ ] CHK005 - ¿Se define qué pasa cuando la propuesta del modelo es estructuralmente inválida (cantidad de sesiones distinta de la exigida, dos sesiones el mismo día, días fuera del rango del plan parcial, bloques sin km, distancias negativas)? ¿Se trata como falla del modelo (FR-027) o se corrige? [Gap, Spec §FR-016, §FR-027]
- [ ] CHK006 - ¿Se especifica si los topes semanales de un plan parcial que sigue a una semana completa se prorratean por los días restantes o se aplican completos? [Gap, Spec §FR-018, §FR-019]
- [ ] CHK007 - ¿Se define si un plan parcial puede ser semana de descarga y cómo se calcula su reducción? [Gap, Spec §FR-021]
- [ ] CHK008 - ¿Se define la progresión de los bloques de caminata y trote de los novatos después de la primera semana? [Gap, Spec §FR-015]
- [ ] CHK009 - ¿Se especifica si la reclasificación pendiente de FR-042 también se aplica a un plan adoptado por falla del modelo (AC-16)? [Gap, Spec §FR-027, §FR-042]
- [ ] CHK010 - ¿Se documenta qué datos registra cada evento de guardarraíl (qué regla, sesión o semana afectada, valores antes y después) con suficiente detalle para auditar SC-001? [Completeness, Spec §FR-045]

## Claridad de requerimientos

- [ ] CHK011 - ¿Es "progresivo según el nivel" medible más allá del piso de AC-66, o queda como adjetivo sin criterio? [Ambiguity, Spec §FR-015]
- [ ] CHK012 - ¿Se aclara cómo se redondea el ritmo objetivo reducido un 5,6% (al segundo, hacia arriba o hacia abajo), dado que 6:00 → 5:40 es en realidad una reducción del 5,56%? [Clarity, Spec §FR-024]
- [ ] CHK013 - ¿Se define la precisión del tiempo objetivo recalculado (segundos enteros, redondeo)? [Clarity, Spec §FR-026]
- [ ] CHK014 - ¿Está claro si las recuperaciones entre tramos son solo de tiempo o si incluyen km de trote que cuentan para el volumen? [Clarity, Spec §FR-019, §FR-026]
- [ ] CHK015 - ¿Se aclara si la conversión a suave de FR-023 conserva o elimina los bloques de caminata de la sesión original? [Ambiguity, Spec §FR-023]
- [ ] CHK016 - Cuando aplican dos topes por sesión a la vez (tope inicial y distancia objetivo), ¿está claro que el factor de recorte usa el menor de ambos? [Clarity, Spec §FR-018, §FR-025, §FR-026]
- [ ] CHK017 - ¿Se define qué es una "semana cerrada" (incluye semanas sin plan, cierre el domingo a medianoche de Buenos Aires)? [Clarity, Spec §FR-022]
- [ ] CHK018 - ¿Se especifica cómo se evalúa "las últimas 3 semanas cerradas" cuando el usuario tiene menos de 3 semanas de historia? [Ambiguity, Spec §FR-022]
- [ ] CHK019 - ¿Está explícito que una semana sin plan corta la racha de descarga? [Clarity, Spec §FR-021]
- [ ] CHK020 - ¿Se define el "volumen planificado" de un plan adoptado por falla del modelo (AC-16) como base del tope de la semana siguiente? [Clarity, Spec §FR-019, §FR-027]

## Consistencia de requerimientos

- [ ] CHK021 - ¿Es consistente la definición de sesión de calidad ("tramos más rápidos que el ritmo actual") con el rango de FR-024, cuyo límite inferior es igual al ritmo actual? Una sesión a ritmo igual al actual quedaría fuera de la definición. [Conflict, Spec §FR-022, §FR-024]
- [ ] CHK022 - ¿Cómo se clasifica como de calidad o suave una sesión con ritmo objetivo de un novato sin ritmo actual, si la definición depende de ese ritmo? [Ambiguity, Spec §FR-022]
- [ ] CHK023 - ¿Es compatible la entrega del último plan válido sin pasar por los guardarraíles de la semana actual (AC-16) con "ningún plan se entrega sin pasar por ellos" y con SC-001 al 100%? El PRD solo acepta como riesgo la descarga salteada y el perfil desactualizado, no FR-020. [Conflict, Spec §FR-017, §FR-027, §SC-001]
- [ ] CHK024 - ¿Es alcanzable "igualar" el volumen de la semana previa a la descarga (FR-021) cuando cada bloque se redondea hacia abajo a 0,01 km? ¿Hay tolerancia definida? [Conflict, Spec §FR-021, §FR-026]
- [ ] CHK025 - ¿Está definida la precedencia cuando un piso (AC-66 o la vuelta tras la descarga) entra en conflicto con un tope que sigue vigente (distancia objetivo, FR-020)? [Conflict, Spec §FR-019, §FR-020, §FR-021, §FR-025]
- [ ] CHK026 - ¿Son consistentes las condiciones de "semana anterior" entre FR-018 (sin plan o parcial sin semana completa previa), FR-019 (parcial → última semana completa) y FR-020 (sin sesión Completada) cuando se dan varias a la vez? [Consistency, Spec §FR-018, §FR-019, §FR-020]

## Calidad de los criterios de aceptación

- [ ] CHK027 - ¿Es SC-001 verificable de forma objetiva, con una lista cerrada de reglas que un plan entregado debe cumplir, pisos incluidos? [Measurability, Spec §SC-001]
- [ ] CHK028 - ¿Tiene la reducción de descarga del 20% al 30% un valor objetivo o un criterio de elección dentro del rango que se pueda testear de forma determinista? [Measurability, Spec §FR-021]
- [ ] CHK029 - ¿Cubre el escenario de recorte de AC-76 (US3-21) el caso en que la sesión recortada también lleva tramos de calidad con tiempos y recuperaciones? [Acceptance Criteria, Spec §US3]

## Cobertura de escenarios y casos borde

- [ ] CHK030 - ¿Se especifica qué pasa cuando el redondeo hacia abajo deja un bloque o una sesión en 0,00 km de trote (sesión vacía, eliminación, mínimo)? [Edge Case, Gap, Spec §FR-026]
- [ ] CHK031 - ¿Se cubre la reducción de la distancia objetivo por debajo de la longitud de las sesiones vigentes en el plan siguiente (interacción con la base del 10%)? [Coverage, Spec §FR-007, §FR-025]
- [ ] CHK032 - ¿Se cubre el cambio de nivel de novato a intermedio o avanzado en cuanto a qué guardarraíles dejan de aplicar y desde qué plan, ahora que RF-20 está fuera de alcance? [Coverage, Spec §FR-008, Edge Cases]
- [ ] CHK033 - ¿Se define el comportamiento cuando el plan de la semana 5 (descarga) se genera por fallback (AC-16) y luego la semana 6 debe "igualar" la semana 4? [Edge Case, Spec §FR-021, §FR-027]
- [ ] CHK034 - ¿Se cubre el caso de una semana de 4 en racha que fue parcial (base de la reducción de descarga)? [Edge Case, Gap, Spec §FR-021]

## Dependencias y supuestos

- [ ] CHK035 - ¿Se documenta que los guardarraíles se calculan sobre los datos guardados (planes, registros) y no sobre los resúmenes semanales que recibe el modelo, de modo que FR-028 no limite el cálculo? [Assumption, Spec §FR-028]
- [ ] CHK036 - ¿Está documentado el supuesto de que los km por bloque de la propuesta del modelo son la única fuente del volumen, sin km implícitos (entrada en calor, vuelta a la calma)? [Assumption, Gap]

## Notes

- Check items off as completed: `[x]`
- Los ítems con [Conflict] (CHK021, CHK023, CHK024, CHK025) son los de mayor riesgo: pueden hacer imposible cumplir SC-001 tal como está escrito.
- Varios ítems tocan reglas que vienen del PRD (AC-16, AC-19d, AC-22); resolverlos puede requerir actualizar `PRD.md` antes que la spec (principio III de la constitución).
