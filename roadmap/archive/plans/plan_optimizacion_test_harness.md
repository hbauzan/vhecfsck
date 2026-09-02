# Plan de Optimización del Test Harness

Documento de seguimiento de los tiempos del gate (`make verify` / `make verify-full`).

**Máquina de referencia** para todo lo que sigue: Apple Silicon, macOS, Python 3.11.15,
numpy 2.4.6 (Accelerate), coverage 7.16.0, `OMP_NUM_THREADS=1` y sus cuatro hermanos
fijados por [`tests/conftest.py`](../../../tests/conftest.py). Ningún número de este documento
es una estimación: todos salen de `/usr/bin/time -p` o de instrumentación explícita.

---

## 1. Dónde estaba el tiempo

### 1.1. El gate es pytest, y nada más

Cadena completa de `make verify`, medida paso por paso:

| Paso | Tiempo |
| :--- | ---: |
| `ruff check .` | 0.06 s |
| `ruff format --check .` | 0.05 s |
| `mypy vhecfsck` | 0.56 s en caliente · 2.4 s en frío |
| `lint-imports` | 0.08 s |
| `scripts/check_readonly.py` | 0.02 s |
| `scripts/clean_orphans.py` | 0.02 s |
| **Subtotal no-pytest** | **< 4 s** |
| `pytest --cov` | 488.66 s |

Cualquier optimización que no toque pytest pelea por menos del 1% del gate.

### 1.2. El 63% del suite era un k-means en Python puro

Baseline pre-cambio, sobre este checkout:

| Corrida | Tiempo | Resultado |
| :--- | ---: | :--- |
| `pytest -m "not (slow or integration or perf)" --no-cov` | 284.59 s | 825 passed |
| lo mismo con `--cov=vhecfsck` (el gate) | 488.66 s | coverage 88.59% |
| **impuesto de coverage** | **+204.07 s (+72%)** | |

Instrumentando `_fit_ivf` durante el suite completo:

```text
calls=90  total_kmeans_seconds=180.30      <-- 63% de los 284.59 s
  n= 8000 d=16 n_lists=32 : calls=21  total=104.68s  mean=4.985s   (healthy)
  n= 8000 d=16 n_lists=16 : calls=16  total= 41.17s  mean=2.573s   (tombstoned)
  n=12701 d=16 n_lists=16 : calls= 8  total= 32.38s  mean=4.047s   (drifted)
  todo el resto junto:                       2.07s
```

45 de esas 90 llamadas son tres fixtures deterministas idénticas, reconstruidas de cero
cada vez.

Reparto dentro de un test típico: `open_scenario("healthy", "small")` = **4.789 s (84%)**,
`run_audit(...)` sobre ese adapter = **0.892 s (16%)**. Las cinco métricas sobre 8.000
vectores tardan menos de un segundo. Lo caro era fabricar el índice.

cProfile de un solo build: **3.072.000** llamadas a `_distance`
(12 iters x 8.000 filas x 32 listas), 24,8 millones de llamadas a función en total.

---

## 2. Qué se hizo (TH-05, entregado)

`_fit_ivf` vectorizado con broadcasting por bandas de filas, `np.argmin` para la
asignación y `np.bincount` + `np.add.at` para el update de centroides. **Bit-exacto**: la
salida es byte-idéntica a la del loop que reemplazó, así que no hubo que regenerar ningún
golden JSON.

La exactitud no es un accidente feliz, es frágil y depende de tres decisiones concretas:

| Forma | ¿Bit-exacta? | Por qué |
| :--- | :--- | :--- |
| `np.sqrt(np.sum(diff*diff, axis=2, dtype=np.float32))` | **sí** | misma reducción float32 que el escalar |
| identidad GEMM `\|q\|² + \|c\|² − 2qc` | **no** | error máximo 1.95e-3 |
| `np.argmin` | **sí** | reproduce el tie-break "gana el primer mínimo" |
| `np.bincount` + `np.add.at` | **sí** | acumulación sin buffer, en orden de fila |
| `vectors[assignment == c].sum(axis=0)` | **no** | numpy usa suma pairwise |

La identidad GEMM era justo lo que proponía el TH-01 original. Está descartada y el motivo
está anotado en el docstring de `_distance_panel` para que nadie la reintroduzca.

El refactor está clavado por [`tests/oracle/test_ivf_build.py`](../../../tests/oracle/test_ivf_build.py),
que compara contra la implementación loop-based movida a
[`tests/oracle/reference_ivf.py`](../../../tests/oracle/reference_ivf.py) y afirma igualdad **de
bytes** en `centroids`, `assignment` y cada array de `lists`, en L2/COSINE/DOT, incluyendo
el caso `n < n_lists` (padding de centroides) y la invariancia al tamaño de banda.

Además, `SyntheticAdapter.from_npz` ya no paga el k-means completo para después
descartarlo: el build persistido entra por el parámetro `prebuilt_ivf` en vez de
sobrescribir atributos privados después del fit.

### Resultado medido

| Corrida | Antes | Después | Delta |
| :--- | ---: | ---: | ---: |
| `pytest --no-cov` | 284.59 s | 76.99 s | **−207.6 s (−73%, 3.7x)** |
| `make verify` (coverage = el suite) | 488.66 s | 132.68 s | **−356.0 s (−73%, 3.7x)** |

El gate quedó verde con coverage global 89% (piso 80) y `core/` 95% (piso 90).

Diferencia de conteo: 827 → 864 tests. Los 37 nuevos son el test diferencial y los dos de
`from_npz`; el precio del oráculo en el suite por defecto es ~2,7 s, y el caso de 8.000
filas —el único caro, porque la referencia naive lo tiene que construir a mano— vive detrás
de `@pytest.mark.slow`.

**Trampa de entorno, anotada para el próximo:** `tests/unit/test_clean_orphans.py` falla con
`PermissionError: [Errno 1] Operation not permitted: 'ps'` cuando el suite corre dentro de
un sandbox que bloquea la ejecución de `ps`. No es un fallo del repo — fuera del sandbox los
tres tests pasan en 0.48 s. Si aparecen esos dos rojos, verificá el sandbox antes de tocar
nada.

---

## 3. Diagnóstico anterior: qué era falso

Las §2 y §3 de la versión previa de este documento no sobrevivieron a la medición. Se
dejan anotadas porque el error es reutilizable.

**TH-02 (forzar el C-tracer de `coverage.py`) — el problema no existía.** Medido:
`coverage 7.16.0`, `CTracer available: YES`. Ya estaba activo; no había fallback a
`PyTracer` que arreglar. Lo que **sí** es cierto es que Python 3.11 no tiene
`sys.monitoring`, así que `COVERAGE_CORE=sysmon` no está disponible. Ese es un lever real,
pero requiere subir el intérprete de desarrollo y quedó fuera de alcance.

**TH-03 (bajar fixtures a `size="tiny"`) — está prohibido.**
[`lessons-learned.md`](../../lessons-learned.md) §37 dice literal *"Do not shrink P1-08 verdict
fixtures to `tiny`"*. A n=80 el guard `|S| < 1000` manda hubness a `UNAVAILABLE`, los
veredictos FAIL/OK se caen y hay que regenerar 4 goldens. Es debilitar tests para que
corran rápido, o sea guardrail 1 de [`AGENTS.md`](../../../AGENTS.md).

**TH-01 sobre `count_nk_from_neighbour_ids` — irrelevante.** Medido en 0.06 s, el 0,02%
del suite.

**TH-01 sobre `exact_knn` "sin BLAS" — ya usa BLAS.** `_score_block` hace
`queries @ block.T`. El cuello real es otro y sigue abierto: ver TH-06.

**`pytest-xdist` — innecesario.** [`tests/conftest.py`](../../../tests/conftest.py) ya fija
`OMP_NUM_THREADS=1` y sus cuatro hermanos, así que la contención de hilos que se temía no
aplica. El suite es secuencial por decisión, no por accidente.

---

## 4. Tickets

| ID | Título | Size | Depende de | Estado |
| :--- | :--- | :--- | :--- | :--- |
| TH-01 | ~~BLAS GEMM para `exact_knn` y `compute_hubness`~~ | — | — | `cancelled` |
| TH-02 | ~~Forzar el C-tracer de `coverage.py`~~ | — | — | `cancelled` |
| TH-03 | ~~Bajar fixtures a `size="tiny"`~~ | — | — | `cancelled` |
| TH-04 | Cachear el coverage o desacoplarlo del gate local | M | P0-04 | `todo` |
| TH-05 | Vectorizar el k-means IVF sintético (bit-exacto) | M | P1-05 | `done` |
| TH-06 | `_merge_query_topk` domina `exact_knn` con Q grande | M | P2-04 | `done` |
| TH-07 | Reusar los tres builds IVF deterministas entre tests | S | TH-05 | `todo` |
| TH-08 | Evaluar `COVERAGE_CORE=sysmon` subiendo el intérprete de dev | S | TH-04 | `todo` |

**TH-01/02/03 se cancelan**, no quedan en `todo`: uno apunta a un problema inexistente,
otro a una optimización irrelevante, y el tercero viola un guardrail. Dejarlos abiertos
invita a que alguien los implemente.

**TH-06** es el hallazgo que sobrevivió de TH-01, y es un problema del **producto a escala
real, no del gate**: con Q grande (hubness a S=20.000) el panel de scores fuerza 6 bloques.
Entregado: merge y block top-k batched, bit-exactos contra el loop en
`tests/oracle/reference_merge.py`. Medido en Apple Silicon arm64 / Python 3.11.15 /
numpy 2.4.6, Q=N=20_000, D=32, k=10, `working_set_mb=256`: `exact_knn` mediana
**4.210 s → 3.360 s**. Split instrumentado: merge 0.732 s (120_000 calls) → 0.164 s
(6 calls); block top-k 3.069 s (120_000 calls) → 2.641 s (6 calls). La cifra original
1.88 s / 2.53 s estaba stale en esta máquina. `_score_block` no se tocó (sin identidad
GEMM).

**TH-07** ataca lo que queda: 45 de las 90 llamadas eran tres fixtures idénticas. Después
de TH-05 el build cuesta ~0,05 s, así que el techo del ticket es ~2 s. Drifted ya congela
centroides (MI-01); este ticket cachea el k-means, no achica N.

**Orden de ejecución** (no es paralelo): TH-06 → TH-07 → TH-04 → TH-08. Cola y contratos
en [`next-ticket.md`](../../next-ticket.md). TH-01/02/03 siguen `cancelled`.
