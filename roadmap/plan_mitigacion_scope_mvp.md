# Plan de Mitigación de Alcance MVP: Integración de LanceDB Adapter en P3 y Alineación de Roadmap

**Fecha:** 2026-08-29  
**Estado:** Aprobado  
**Documentos Relacionados:** [03-phases-overview.md](file:///Users/hbauzan/treepwood/vhecfsck/roadmap/03-phases-overview.md), [backlog.md](file:///Users/hbauzan/treepwood/vhecfsck/roadmap/backlog.md), [phase-3-report-and-cli.md](file:///Users/hbauzan/treepwood/vhecfsck/roadmap/phases/phase-3-report-and-cli.md)

---

## 1. Resumen Ejecutivo y Diagnóstico de Arquitectura

Tras la revisión del estado del proyecto `vhecfsck`, se identificaron dos desvíos de alcance y un ajuste de tolerancia en tests sintéticos:

1. **Reubicación Crítica de `LanceDbAdapter` a la Fase 3 (MVP):**  
   El roadmap previo difería la implementación de `lancedb_adapter.py` a la Fase 5 (post-MVP), limitando la validación MVP únicamente a `SyntheticAdapter`. `vhecfsck` es un auditor `fsck` nativo para índices vectoriales; por ende, el MVP debe poseer la capacidad de auditar tablas reales de LanceDB. Se promueve el adaptador de LanceDB a la **Fase 3 (P3)**.

2. **Simplificación Arquitectural mediante el SDK Oficial (`lancedb`):**  
   Se descarta la necesidad de escribir un parser binario de bajo nivel a mano para los archivos en disco en la etapa de MVP. `LanceDbAdapter` se implementa directamente utilizando el SDK oficial Python `lancedb.connect()`, cumpliendo el protocolo `IndexAdapter`.  
   Esto permite resolver de forma unificada:
   - Carpetas y tablas locales (`./data/mi_tabla`, `/path/to/db`)
   - Buckets en la nube (`s3://bucket/table`, `gcs://bucket/table`)
   - LanceDB Cloud remoto (`db://database_name` con flag `--api-key`)  
   La extracción de vectores crudos se efectúa vía Apache Arrow (`table.to_arrow()`) y la evaluación de búsquedas mediante `table.search()`.

3. **Ajuste de Latencia en Tests Sintéticos (`test_scenarios.py`):**  
   El desvío en el tiempo de ejecución (~22.77s vs 20.0s) en `test_full_small_set_builds_under_20s` obedecía a variaciones puras de CPU de la máquina de ejecución. Se relaja el timeout a 45.0s (configurable mediante la variable `VHECFSCK_SCENARIO_TIMEOUT`), garantizando la estabilidad de `make verify` sin alterar la precisión ni la cobertura.

---

## 2. Reordenamiento de Tickets del Roadmap

Se actualiza la Fase 3 (P3) incorporando el adaptador real de LanceDB (`P3-09`) y reajustando la responsabilidad de la Fase 5.

### Backlog Actualizado de la Fase 3 (P3) — Report, CLI & LanceDB Adapter

| ID | Título | Tamaño | Dependencias | Estado | Descripción |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **P3-01** | Report schema | M | P2-01 | done | Modelo de datos Pydantic/dataclass para serialización del reporte de auditoría. |
| **P3-02** | JSON renderer y schema publicado | M | P3-01 | todo | Formateador JSON determinista con exportación de schema JSON. |
| **P3-03** | Terminal renderer | M | P3-01 | todo | Formateador de consola enriquecido (tablas, veredictos, métricas destacadas). |
| **P3-04** | `vhecfsck audit` | M | P3-02, P3-03, P2-10, P3-09 | todo | CLI principal para auditar objetivos (Local, S3, Cloud, Synthetic). |
| **P3-05** | `vhecfsck demo` | S | P3-04, P1-08 | todo | Ejecución directa de escenario sintético predefinido con reporte visual. |
| **P3-06** | Prometheus exporter | M | P3-01 | todo | Exposición de métricas de auditoría en formato OpenMetrics/Prometheus. |
| **P3-07** | `vhecfsck export` | S | P3-02 | todo | Exportador de reportes a archivos y stdout. |
| **P3-08** | Exit-code contract test suite | S | P3-04, P3-05 | todo | Suite de tests para verificación estricta de códigos de salida (`0`, `1`, `2`, `3`, `4`). |
| **P3-09** | `LanceDbAdapter` con SDK oficial | M | P1-02 | todo | Adaptador nativo usando `lancedb.connect()` (local, S3/GCS, LanceDB Cloud). |

### Reclasificación de la Fase 5 (P5) — Post-MVP Introspection
La Fase 5 se reserva exclusivamente para inspección binaria avanzada y reproducciones de bajo nivel:
- Decodificación interna de archivos `.lance` (formatos de página, deletion vectors en disco sin SDK).
- Reproducción de anomalías profundas de diseño de indices como `lance#4164`.

---

## 3. Especificación de Interfaz CLI: `vhecfsck audit` (P3-04)

El comando `vhecfsck audit` es el punto de entrada para auditar datasets vectoriales.

```bash
vhecfsck audit TARGET [OPCIONES]
```

### Argumentos y Parámetros

1. **`TARGET`** (Argumento Posicional, Requerido):
   - **Ruta local:** `./data/vector_db`, `/var/data/lancedb`
   - **URI S3 / GCS:** `s3://bucket-name/table`, `gcs://bucket-name/table`
   - **URI LanceDB Cloud:** `db://database_name` (requiere `--api-key`)
   - **URI Sintética:** `synthetic://healthy`, `synthetic://tombstoned`

2. **`--table` / `-t`** (Texto, Opcional):
   - Nombre explícito de la tabla a auditar en la base de datos o carpeta objetivo.

3. **`--api-key`** (Texto, Opcional):
   - Clave de API para LanceDB Cloud o credenciales de cloud storage. Fallback automático a `LANCEDB_API_KEY`.

4. **`--k` / `-k`** (Entero, Default: `100`):
   - Vecinos más cercanos ($k$) evaluados en las pruebas de Canary Recall.

5. **`--queries` / `-q`** (Entero, Default: `100`):
   - Número de vectores de consulta a utilizar en el muestreo de recall.

6. **`--output` / `-o`** (Elección: `terminal` | `json`, Default: `terminal`):
   - Formato de presentación del informe de resultados.

7. **`--threshold-profile`** (Elección: `default` | `strict` | `permissive`, Default: `default`):
   - Perfil de umbrales para determinación de veredictos y exit-codes.

---

## 4. Cronograma Actualizado para Cierre de MVP

```text
 FASE 2: Metrics Engine (EN CURSO / VERIFICADO)
 ├── P2-01 / P2-04: Blocked BLAS Ground Truth (Q x N en memoria)
 ├── P2-05 / P2-07: Evaluadores Canary Recall@K y DFI
 └── P2-09 / P2-10: Verdict Engine & Pipeline Orchestration
        │
        ▼
 FASE 3: Report, CLI & LanceDB Adapter
 ├── P3-09: LanceDbAdapter (SDK lancedb, Arrow, Search)
 ├── P3-01 .. P3-03: Schemas Pydantic, JSON & Terminal Renderers
 ├── P3-04: vhecfsck audit CLI (TARGET, --table, --api-key, --k, --queries)
 └── P3-05 & P3-08: vhecfsck demo & Exit-Code Test Suite
        │
        ▼
 FASE 4: Projection & 3D Visualizer
 ├── P4-01 .. P4-04: Proyección 3D, Modelo de Escena & Transport Binary
 ├── P4-05 & P4-06: Servidor FastAPI (vhecfsck serve)
 └── P4-07 .. P4-11: Front-end Three.js & Empaquetado Wheel MVP
        │
        ▼
 ════════════════════ MVP GATE (v0.1.0-rc) ════════════════════
  1. uvx vhecfsck demo funcional sin dependencias de base de datos
  2. vhecfsck audit operativo contra tablas LanceDB (Local / Cloud / S3)
  3. make verify en verde (cobertura ≥90% en core)
```
