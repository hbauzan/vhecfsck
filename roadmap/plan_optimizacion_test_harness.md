# Plan de Optimización del Test Harness y Tiempos de Ejecución

Documento de seguimiento en `roadmap/` para la optimización de los tiempos del gate de verificación (`make verify` y `make verify-full`).

---

## 1. Mediciones Empíricas Registradas (Apple Silicon, macOS, Python 3.11)

Mediciones empíricas tomadas mediante `/usr/bin/time -p`:

| Comando | Tiempo Real (Wall-clock) | Tiempo User | Tiempo Sys | Desglose por Etapas |
| :--- | :--- | :--- | :--- | :--- |
| `make verify` | **474.77 s** (~7m 55s) | 462.71 s | 6.37 s | Ruff + Mypy + `pytest --cov` (827 passed) + Layering + Readonly guard |
| `make verify-full` | **1080.76 s** (~18m 01s) | 1032.25 s | 19.22 s | `make verify` (474.77s) + `pytest -m "slow or integration or perf"` (603.26s) + `mutation` (0.09s) |

---

## 2. Diagnóstico Técnico y Causas Raíz

1. **`pytest-cov` (`sys.settrace`) en Operaciones Matriciales**:
   * `make verify` ejecuta `pytest --cov=vhecfsck` sobre todo el suite.
   * `coverage.py` activa `sys.settrace`, ralentizando la ejecución de código Python denso entre 5x y 10x cuando se calculan distancias matriciales o simulación sintética.
2. **Cálculo de $O(S^2 \cdot d)$ en NumPy sin BLAS Matricial (GEMM)**:
   * `exact_knn` y `compute_hubness` ejecutan distancias L2 sobre $S=20.000, d=768$.
   * Si no se utiliza la descomposición $\|q - c\|^2 = \|q\|^2 + \|c\|^2 - 2(q \cdot c^T)$ delegada directamente a `np.dot` (Accelerate / BLAS en C), la CPU ejecuta iteraciones y deducciones de NumPy penalizadas por `sys.settrace`.
3. **Cardinalidad de Fixtures en Tests Unitarios**:
   * Tests unitarios y de contrato que invocan escenarios de cardinalidad $N \ge 1.000$ (`size="small"`) agregan sobrecarga innecesaria al gate de dev frente a fixtures `size="tiny"` ($N \le 100$).

---

## 3. Acciones a Futuro / TODOs (Harness Optimization Backlog)

| ID | Tarea | Impacto Esperado | Estado |
| :--- | :--- | :--- | :--- |
| **TH-01** | Vectorizar `exact_knn` y `compute_hubness` mediante multiplicación de matrices BLAS GEMM (`q @ c.T`) para delegar el cálculo L2 al framework Accelerate/C-level. | Reducción de 5x a 8x en tiempo de ejecución de kNN denso. | `todo` |
| **TH-02** | Verificar y forzar el uso del C-extension tracer de `coverage.py` en el entorno `.venv` generado por `uv sync`. | Evita fallback a pure-Python tracer (hasta 8x más rápido en coverage). | `todo` |
| **TH-03** | Auditoría de fixtures: asegurar que los tests unitarios y de contrato usen cardinalidad $N \le 100$ (`size="tiny"`) reservando $N \ge 10.000$ únicamente a `@pytest.mark.perf`. | Disminución del tiempo base de pytest en `make verify`. | `todo` |
| **TH-04** | Evaluar desacoplar o paralelizar la recolección de coverage en `make verify` (ej: `pytest-xdist` o coverage condicional en local vs CI) manteniendo la meta de < 30s para dev local. | Reducción del gate local de dev a < 30s. | `todo` |
