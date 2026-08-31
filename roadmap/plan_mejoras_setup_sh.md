# Plan de Mejoras, Resiliencia y Diseño Elegante para `setup.sh`

**Estado:** Aprobado / Listo para ejecución  
**Disparador del Plan:** Solicitar al agente el prompt:  
> *"Por favor hacé lo que dice el roadmap sobre mejoras de setup.sh"*

---

## 1. Objetivo General

Transformar `setup.sh` en una consola interactiva resiliente, de alta estética visual y 100% autónoma. Cada opción del menú debe **verificar proactivamente el entorno**, **informar el estado mediante barras de progreso estilizadas**, e **instalar automáticamente cualquier dependencia faltante** sin interrumpir la consola ni fallar abruptamente. Toda salida técnica seria se acompañará a la derecha de referencias temáticas en tono secundario basadas en *The Hitchhiker's Guide to the Galaxy*.

---

## 2. Invariantes Técnicas y Reglas del Proyecto

1. **Cumplimiento de `AGENTS.md` y `lessons-learned.md`:**
   * `setup.sh` es una consola para colaboradores/desarrolladores en macOS/Linux.
   * **No es un supervisor de daemons:** No usa `nohup`, archivos `.pid`, ni directorios de logs globales. Los comandos interactivos (`serve`, `demo`) se ejecutan en primer plano (*foreground*).
   * **Sincronización `uv` estricta:** Utiliza exclusivamente `uv sync` o `uv sync --group dev`. **Nunca** ejecuta `uv sync --all-extras` (lección #5 de `lessons-learned.md`).
2. **Jerarquía Visual y Atribución:**
   * Cada opción muestra primero la acción técnica seria en negrita y a la derecha la cita temática entre paréntesis en tono atenazado (`C_DIM`).
   * Atribución de copyright y mensajes respetan los estándares del repositorio (`hbauzan`).
3. **Manejo de Errores y Auto-Healing (Autocuración):**
   * Ninguna opción debe cortarse con un error no atrapado si falta un componente.
   * Si falta una herramienta (`uv`, `make`, dependencias Python), el script lo notifica, muestra una barra de progreso de instalación/sincronización y reintenta la acción automáticamente.

---

## 3. Especificación de Diseño Visual y Paleta de Colores

### Paleta ANSI Elegante
* **Bordes y Cajas (`C_BLUE` / `C_CYAN`):** `\033[1;34m` y `\033[1;36m` para marcos y encabezados.
* **Acción Principal (`C_WHITE_BOLD`):** `\033[1;37m` para el texto técnico principal.
* **Citas de Hitchhiker (`C_DIM`):** `\033[2m` para las referencias secundarias a la derecha.
* **Estados:**
  * `[ OK ]` → `\033[1;32m` (Verde esmeralda)
  * `[INFO]` → `\033[1;36m` (Cian brillante)
  * `[WARN]` → `\033[1;33m` (Amarillo cálido)
  * `[FAIL]` → `\033[1;31m` (Rojo carmesí)
  * `[BUSY]` → `\033[1;35m` (Magenta elegante para operaciones en progreso)

### Barra de Progreso Nactiva (ANSI Output)
Formato de barra de progreso nativa en Bash (sin dependencias de paquetes externos):
```text
[BUSY] Sincronizando entorno de desarrollo... [████████████░░░░░░░░] 60%  (Don't Panic)
```

---

## 4. Matriz de Opciones y Comportamiento Autocurativo

| Opción | Acción Técnica | Cita Hitchhiker (Dim a la derecha) | Verificación y Auto-Healing |
| :--- | :--- | :--- | :--- |
| **`[1]`** | Detectar e instalar `uv`, luego ejecutar `uv sync --group dev` | *(Infinite Improbability Drive)* | Verifica `uv`. Si falta, descarga e instala `uv` oficial. Ejecuta `uv sync --group dev` con barra de progreso. |
| **`[2]`** | Ejecutar la suite completa de calidad `make verify` | *(The mice would like a word)* | Verifica `make` y `uv`. Si el entorno Python no está sincronizado, ejecuta `uv sync` automáticamente antes de correr `make verify`. |
| **`[3]`** | Ejecutar auditoría sintética de demostración en terminal | *(Forty-two)* | Verifica que el paquete `vhecfsck` esté instalado en `.venv`. Si no, ejecuta `uv sync`. Corre `uv run vhecfsck demo`. |
| **`[4]`** | Levantar WebGUI 3D interactiva en el puerto 8765 | *(Heart of Gold)* | Verifica dependencias web/server (`fastapi`, `uvicorn`). Si faltan, ejecuta `uv sync --group dev`. Lanza `uv run vhecfsck serve` e informa la URL `http://127.0.0.1:8765`. |
| **`[5]`** | Limpiar procesos pytest u orquestadores huérfanos | *(Point-of-View Gun)* | Escanea PIDs de pytest acotados únicamente al checkout actual (lección #38) y los finaliza de forma segura. |
| **`[0]`** | Salir del panel de control | *(So long, and thanks for all the fish)* | Cierra la sesión limpiamente. |

---

## 5. Plan de Implementación Paso a Paso (Para el Agente Ejecutor)

Cuando el usuario invoque la ejecución de este plan, el agente debe seguir estos pasos en orden:

### Paso 1: Crear la rama de trabajo
```bash
git checkout main
git checkout -b feat/setup-sh-improvements
```

### Paso 2: Refactorizar `setup.sh`
1. **Actualizar la paleta de colores y funciones de formateo:**
   * Agregar helper `draw_box` para encabezados y banners.
   * Agregar función `show_progress_bar(percent, title, quote)` que renderice barras ANSI limpias.
2. **Implementar verificadores autocurativos (`ensure_prereqs`):**
   * `ensure_uv()`: Verifica `uv` en PATH o rutas estándar (`~/.local/bin`, `/opt/homebrew/bin`). Si falta, lo instala mediante `curl -LsSf https://astral.sh/uv/install.sh | sh` notificando el progreso.
   * `ensure_env_synced()`: Corre `uv sync --group dev` si `.venv` no existe o no tiene las dependencias instaladas.
3. **Refactorizar los comandos de las opciones:**
   * `cmd_sync()`: Muestra barra de progreso durante la sincronización de dependencias.
   * `cmd_verify()`: Auto-cura el entorno antes de invocar `make verify`.
   * `cmd_demo()`: Ejecuta `uv run vhecfsck demo` e informa claramente el significado de la salida del diagnóstico en terminal.
   * `cmd_serve()`: Auto-instala requisitos de servidor si faltan, inicia `uv run vhecfsck serve` en puerto `8765` e informa la URL directa `http://127.0.0.1:8765`.
   * `cmd_clean()`: Aplica filtrado por ruta de checkout (`SETUP_SH_IN_TEST=1` friendly).

### Paso 3: Verificar y Auditar
1. Ejecutar sintaxis check de Bash: `bash -n setup.sh`
2. Correr la suite de pruebas unitarias existente: `uv run pytest tests/unit/test_setup_sh.py -v` (o los tests de setup).
3. Ejecutar el gate de calidad único del proyecto: `make verify`

### Paso 4: Documentación y Entrega
1. Actualizar `CHANGELOG.md` en la sección `[Unreleased]`.
2. Presentar los cambios al usuario en el **Approval Gate** antes de commitear y fusionar a `main`.

---

## 6. Prompt Canónico de Activación

Para activar la ejecución de este plan en cualquier momento, la frase de activación es:

> **`Por favor hacé lo que dice el roadmap sobre mejoras de setup.sh`**
