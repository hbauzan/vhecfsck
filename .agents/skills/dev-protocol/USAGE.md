# CÓMO USAR `dev-protocol` (instalación y portabilidad)

Guía de uso de la skill: cómo encajan los archivos entre sí, cómo instalarla en Claude Code, y cómo portarla a otros IDEs/IAs (Cursor, Gemini, OpenCode, etc.) que **no** tienen el mecanismo de skills.

> ⚠️ **Distinción clave**: el **auto-trigger** y la **disclosure progresiva** (cargar un módulo solo cuando hace falta) son **nativos de Claude Code**. En las demás herramientas no existen "skills": tienen un archivo de **reglas/contexto** que vos apuntás a estos mismos `.md`. El contenido del protocolo es portable; el mecanismo de carga, no.

---

## 1. Cómo encajan las piezas (entre ellas)

```
dev-protocol/
├─ SKILL.md            ← ENTRADA. Router liviano. Se lee SIEMPRE primero.
│                        (rol, CUSTOMIZACIÓN ELETOR, §3 entorno, §0 flujo, higiene, bootstrap)
│
│  ─── se leen SOLO cuando la tarea lo pide, por ruta relativa desde SKILL.md ───
├─ code-design.md      ← módulos profundos, TDD, taxonomía de errores y exit codes
├─ debugging.md        ← loop de 6 fases
├─ guardrails.md       ← el gate único, prohibiciones duras, definition of done,
│                        guards estáticos, y de dónde sale el AGENTS.md de la raíz
├─ qa-review.md        ← review de dos ejes + issues
├─ git-workflow.md     ← commits, pre-commit, entrega
├─ documentation.md    ← doc-sync manifest/spec (o el equivalente del repo)
├─ lessons-learned.template.md
│                      ← protocolo de la memoria de handoff (cuándo leer/escribir).
│                        La memoria del producto vive FUERA del pack
│                        (default: roadmap/lessons-learned.md)
│
├─ templates/          ← copy-to-root (destino de cada uno abajo)
├─ Por acá va la bocha.md  ← puntero a SKILL.md §2 (CUSTOMIZACIÓN ELETOR)
└─ USAGE.md            ← este archivo
```

Destino de cada template al adoptar la skill en un repo:

| Template | Va a | Para qué |
| :--- | :--- | :--- |
| `Makefile` | raíz | `make verify`, el gate único |
| `.pre-commit-config.yaml` | raíz | hooks de commit |
| `.env.example` | raíz | variables documentadas, sin valores |
| `.importlinter` | raíz | contratos de capas |
| `ci.yml` | `.github/workflows/` | matriz de CI + drift de SDKs (GitHub-specific) |
| `check_provider_seam.py` | `scripts/` | guard AST del seam de proveedor |
| `sync_agents_md.py` | `scripts/` | genera y verifica el `AGENTS.md` de la raíz |

- **`SKILL.md` es el único archivo "siempre cargado".** Es un índice/router: no duplica el contenido de los módulos, los referencia. Eso es lo que ahorra tokens.
- **Los módulos son auto-contenidos** y se cruzan entre sí con rutas relativas (`./debugging.md`, etc.). No usan rutas absolutas → la carpeta funciona en cualquier repo.
- **Archivos de referencia en la raíz del repo** (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`) son **punteros versionados** a esta skill. Sobreviven a `git clone` y garantizan que cada agente aplique el protocolo apuntando a `.agents/skills/dev-protocol/SKILL.md`.
- **Excepción deliberada: las prohibiciones van inline en `AGENTS.md`.** Un puntero solo funciona si el agente lo sigue, y seguirlo es una decisión suya, no un mecanismo — fuera de Claude Code no hay disclosure progresiva. Un *procedimiento* lo consultás cuando sabés que lo necesitás; una *prohibición* te hace falta justo cuando no sabés que te hace falta. Y el costo de fallar es asimétrico: saltear `code-design.md` es diseñar peor, saltear "nunca debilites un test" es un assert borrado y un reporte en verde.
- **`AGENTS.md` tiene dos modos** ([guardrails.md](./guardrails.md) §6). **Generado:** `scripts/sync_agents_md.py` proyecta los bloques `agents-md:` más un overlay de producto opcional (`AGENTS.overlay.md`) que el generador no pisa. **Opt-out:** el repo mantiene `AGENTS.md` a mano (playbook / reglas de producto) y **no** cablea `--check`. Este workspace es opt-out. No regeneres `AGENTS.md` acá.

---

## 2. Claude Code (nativo — auto-trigger + disclosure progresiva)

### Cómo se invoca
- **Auto (description)**: el frontmatter dispara la skill cuando la tarea es del stack (Python/`uv` + LLM). Requiere que Claude Code la descubra → necesita el symlink en `.claude/skills/` (ver install).
- **Explícito**: `/dev-protocol` (también requiere el symlink).
- **Garantía sin symlink**: `CLAUDE.md` (versionado, siempre cargado) referencia `SKILL.md`, así el protocolo se aplica aunque el symlink no exista todavía en ese clon.
- **Frase canónica**: `Usando dev-protocol, <qué hacer / mejorar / arreglar>`.

### Instalar — opción A: per-repo (convención)
En el destino final `.agents/` **está versionado** (no en `.gitignore`), así que el contenido de la skill viaja con `git clone`. Lo que **no** viaja es el symlink de descubrimiento de Claude Code, porque `.claude/skills/` suele estar gitignored. Por eso el único paso de install por clon es recrear ese symlink:
```bash
# desde la raíz del repo, una vez por clon
mkdir -p .claude/skills
ln -sfn ../../.agents/skills/dev-protocol .claude/skills/dev-protocol
```
> El protocolo igual se aplica sin ese paso vía `CLAUDE.md`/`AGENTS.md`/`GEMINI.md` (versionados). El symlink solo habilita el auto-trigger nativo y el slash command `/dev-protocol`.
>
> Para llevar la skill a **otro** repo desde cero: `cp -R /ruta/a/dev-protocol .agents/skills/dev-protocol` y luego el `ln -s` de arriba.

### Instalar — opción B: global (disponible en TODOS tus proyectos)
```bash
cp -R /ruta/a/dev-protocol ~/.claude/skills/dev-protocol
```

---

## 3. Otros IDEs / IAs (sin mecanismo de skills)

La estrategia es siempre la misma en dos pasos:
1. **Tené la carpeta** `dev-protocol/` en el repo (canónico: `.agents/skills/dev-protocol/`).
2. **Apuntá el archivo de reglas/contexto de la herramienta** a esa `SKILL.md` (y aclarale que lea los módulos bajo demanda).

| Herramienta | Archivo de reglas/contexto | Qué poner adentro |
| :--- | :--- | :--- |
| **Cursor** | `.cursor/rules/dev-protocol.mdc` y/o `AGENTS.md` | Regla que diga: *"Seguí el protocolo en `.agents/skills/dev-protocol/SKILL.md`; leé sus módulos referenciados solo cuando la tarea lo requiera."* |
| **Gemini CLI** | `GEMINI.md` (raíz; soporta jerárquicos) | Bloque: *"Antes de cualquier tarea de código, aplicá `.agents/skills/dev-protocol/SKILL.md`. Los módulos se leen bajo demanda."* |
| **OpenCode** | `AGENTS.md` (o `instructions` en `opencode.json`) | Igual que Gemini: referenciá `SKILL.md` + nota de carga bajo demanda. |
| **GitHub Copilot** | `.github/copilot-instructions.md` | Referenciá `SKILL.md`; Copilot lo inyecta como contexto en chat/edits. |
| **Windsurf** | `.windsurfrules` (o `.windsurf/rules/`) | Referenciá `SKILL.md` + módulos bajo demanda. |
| **Genérico / multi-tool** | `AGENTS.md` (estándar [agents.md](https://agents.md)) | Un solo `AGENTS.md` que muchos agentes leen (Codex, OpenCode, Cursor). |

### Plantilla de regla (pegá esto en el archivo de la herramienta)
```markdown
# Protocolo de desarrollo
Para CUALQUIER tarea de implementación, bug, review o entrega en este repo,
seguí el protocolo en `.agents/skills/dev-protocol/SKILL.md`.
- Leé `SKILL.md` primero (rol, CUSTOMIZACIÓN ELETOR, entorno, flujo idea→entrega con approval gate).
- Leé los módulos SOLO cuando la tarea lo pida:
  diseño/TDD/errores → code-design.md · bug → debugging.md · verificar y cerrar →
  guardrails.md · review → qa-review.md · git/entrega → git-workflow.md ·
  docs → documentation.md · entrar en frío, diseñar desde cero o Fase 3 de un
  debug → lessons-learned del producto (default `roadmap/lessons-learned.md`;
  se escribe solo al hacer handoff).
- Regla dura: dependencias Python con `uv` (nunca `pip` ni venv manual).
- Regla dura: `make verify` verde antes de decir que algo está listo. Sin `--no-verify`.
- Regla dura: nunca debilites un test para que pase (ni tolerancia, ni skip, ni xfail).
- No hagas push/merge sin OK explícito del usuario (approval gate de git-workflow.md §3).
```

> Si el repo ya tiene un `AGENTS.md` (generado **o** opt-out), esta plantilla es redundante para las herramientas que lo leen. Usala para las que no lo leen — `.windsurfrules`, `.github/copilot-instructions.md`.

> **Nota de fidelidad**: como estas herramientas no tienen disclosure progresiva, el agente puede cargar todos los módulos que referencies de una. Si te importa el ahorro de tokens ahí, referenciá en el archivo de reglas **solo** `SKILL.md` y dejá que el agente abra los módulos cuando los necesite.

---

## 4. Una sola fuente de verdad

Mantené **una** copia de `dev-protocol/` por repo y que todos los archivos de reglas (`.cursor/rules`, `GEMINI.md`, `AGENTS.md`, etc.) **la referencien** en vez de copiar el contenido a mano. Así actualizás el protocolo en un solo lugar y todas las herramientas lo ven.

En modo **generado**, la única copia permitida del bloque de prohibiciones es la que produce `scripts/sync_agents_md.py` a partir de `guardrails.md` (+ overlay). En modo **opt-out**, `AGENTS.md` es a mano y el `--check` no corre — no lo regeneres.

> Los nombres de archivo de reglas de cada herramienta evolucionan rápido — si alguno no funciona, verificá la doc oficial vigente de esa herramienta. El patrón ("apuntá su archivo de contexto a `SKILL.md`") se mantiene.

---

## 5. Estado en este workspace

La skill vive versionada en **`.agents/skills/dev-protocol/`**.

Punteros en raíz: `AGENTS.md` (**opt-out**, playbook a mano), `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/dev-protocol.mdc`.

Memoria de handoff de este producto: [`roadmap/lessons-learned.md`](../../../roadmap/lessons-learned.md).

Por clon, recreá el symlink de Claude Code:

```bash
mkdir -p .claude/skills
ln -sfn ../../.agents/skills/dev-protocol .claude/skills/dev-protocol
```

Este repo **no** regenera `AGENTS.md` desde el skill. El script `scripts/sync_agents_md.py` está en modo opt-out: `--check` no falla; escribir el archivo está bloqueado.

**Una skill por repo** (`dev-protocol`). No symlinks masivos a skills globales del IDE: el catálogo hincha tokens antes de leer código.

### Frase canónica
`Usando dev-protocol, <qué hacer / mejorar / arreglar>`