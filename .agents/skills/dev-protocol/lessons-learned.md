# LESSONS LEARNED & ARCHITECTURAL INVARIANTS

**Este archivo es la memoria de handoff entre agentes.** Registra lo que una IA aprendió y que la siguiente necesita saber sin haber estado ahí: invariantes de arquitectura, patrones de rendimiento y decisiones que ya se probaron y no hay que volver a probar. Sobrevive a la sesión, a la compactación de contexto y al cambio de modelo — es lo único del proyecto que lo hace.

De ahí salen sus dos reglas, que están en el §5 del final y son las mismas que en [SKILL.md](./SKILL.md): se **lee** cuando entrás en frío o cuando una decisión concreta depende de una invariante, y se **escribe** cuando el usuario pide un handoff. Ninguna de las dos por reflejo.

---

## 0. Estado

Sin invariantes de producto todavía. Este repo arranca limpio: las lecciones del proyecto anterior **no** aplican acá. Cuando el usuario pida un handoff, agregá secciones numeradas debajo de este bloque (problema → solución → invariante).

---

## 5. Protocolo de Mantenimiento de Lecciones Aprendidas

Este archivo es caro de leer y fácil de arruinar. Si se lee por reflejo, se paga en cada sesión; si se escribe por reflejo, se llena de ruido y deja de servir para lo único que sirve: que la próxima IA arranque donde terminó la anterior.

### 5.1. Cuándo se LEE
El agente **DEBE** leerlo en estos tres casos, y no por defecto en el resto:
1. **Entrás en frío.** Sesión nueva sobre trabajo que no hiciste vos, retomada después de un handoff, o continuación después de compactar contexto. Es literalmente para lo que existe.
2. **Vas a diseñar algo nuevo.** Feature, módulo o build desde cero: leelo antes de decidir la forma, no después.
3. **Estás en la Fase 3 de un debug** ([debugging.md](./debugging.md)). Buena parte de los bugs son invariantes re-rotas; si una cubre el área, es una hipótesis que ya viene con evidencia y con fix conocido.

No hace falta para reviews, commits, sync de docs ni ediciones triviales.

### 5.2. Cuándo se ESCRIBE
**Solo cuando el usuario lo pide** — típicamente al preparar un handoff. Si descubriste una invariante durable, **proponéla en el reporte de entrega** y dejá que el usuario decida si entra. El criterio de admisión es alto: una invariante que un agente futuro no debe re-romper, en pocas líneas. Las tablas de mediciones y los hilos abiertos van a `current-research/` (si el repo lo usa), no acá.

### 5.3. Cuándo una lección ya no alcanza
Si un bug reincide sobre una invariante **que ya estaba escrita acá**, el problema no es de documentación: la prosa no enforcea nada. Esa invariante se ganó un guard estático o un test de regresión ([guardrails.md](./guardrails.md) §5). Anotarlo dos veces no la va a hacer cumplir.
