# Plan de Integridad Matemática

Auditoría de la matemática de `vhecfsck` contra la literatura publicada y contra la
evidencia que el propio repo produce. **No se tocó una línea de código de métricas.** Los
tickets viven en la sección MI de [`backlog.md`](backlog.md).

**Estado:** MI-01 y MI-02 entregados (`inject_hubs` concentra masa; `hubby` mide FAIL en
hubness). MI-03, MI-04 y MI-06 ya estaban. **Siguiente: MI-07, después MI-05** — cola en
[`next-ticket.md`](next-ticket.md). No reabrir MI-03/04/06.

## Resumen

No se encontró **ninguna fórmula inventada ni mal implementada**. `recall_id`,
`partition_size_cv` (CV poblacional, `ddof=0`, Fixture C verificada a mano), el Gini,
`dfi` (acuñado y declarado como tal), el clamp de L2 antes del `sqrt` y la PCA a 3D están
bien. El problema es de otro tipo, y en dos ejes:

1. **Atribución sin fuente.** Umbrales presentados como "de la literatura" que la
   literatura no publica, y una definición correcta presentada como invención propia
   cuando en realidad está publicada y se puede citar.
2. **Validación faltante.** Una patología sintética que no mueve la métrica que dice
   inducir, con el suite fijando esa no-detección como comportamiento esperado.

Los cinco hallazgos de abajo son mediciones, no opiniones. Cada uno dice contra qué se
midió.

---

## MI-01 — `inject_hubs` es un no-op sobre la métrica que gatea

**Medido.** Barrido de `n_hubs` de 8 a 800 sobre el mismo corpus base:
`hub_share_top1pct` va de `0.0882` a `0.0864` — es decir, **baja**. El corpus sin inyectar
nada da `0.0882`; el escenario `hubby` tal como se envía da `0.0877`.

**Por qué.** La aritmética lo explica sin misterio: `total_slots = 8028 x 10 = 80.280`, y
los 81 vectores del top-1% ya absorben unos 7.000 slots de forma natural. Agregar unos
pocos atractores no mueve una fracción que ya está dominada por el bulto de la muestra.

**El agravante.** [`vhecfsck/synthetic/scenarios.py:284-294`](../vhecfsck/synthetic/scenarios.py)
asserta `METRIC_HUB_SHARE: "OK"` y `METRIC_ANTIHUB_FRACTION: "OK"` para el escenario
documentado como *"hubness: cannibalising hubs + isolated anti-hubs in high-d space"*. El
suite no está tolerando la no-detección: la está fijando como contrato.

Esto viola el invariante de [`lessons-learned.md`](lessons-learned.md) §21 — *"Pathology
operators must induce the claimed geometry; tests verify by brute force, not by trusting
placement labels"*. La lección se escribió por el caso L2/top-10 y se cumple ahí; lo que
nunca se verificó es que el operador moviera **la métrica gateada**.

## MI-02 — La métrica sí funciona; lo que falta es la fixture

**Medido.** Un atractor real —1% del corpus concentrado, el resto difuso— da
`hub_share = 0.9670 FAIL` y `antihub_fraction = 0.7772 FAIL`.

O sea: `compute_hubness` detecta hubness cuando la geometría es de verdad hubby. Lo que no
existe es un generador que produzca esa geometría. MI-01 y MI-02 son el mismo ticket visto
de los dos lados: hay que reescribir `inject_hubs`
([`vhecfsck/synthetic/pathologies.py:214`](../vhecfsck/synthetic/pathologies.py)) para que
concentre masa de verdad, y recién entonces corregir la expectativa de `hubby`.

**Orden obligatorio:** primero el operador, después la expectativa. Cambiar
`scenarios.py` para que espere `FAIL` sin arreglar el generador sería debilitar el test al
revés.

**MI-01 entrega un test, no una lección.** §21 ya exige que el operador induzca la
geometría, y `inject_hubs` la cumple. Lo que falta es el escalón de arriba: que mueva la
métrica gateada. Por §5.3, una invariante que se rompe dos veces se ganó un guard, no otro
párrafo. El criterio de aceptación de MI-01 es un test que afirme que cada operador de
patología mueve la métrica que le da nombre. **Entregado:** ese test existe y está verde
(`tests/property/test_hubness_props.py`, `tests/unit/test_partitions.py`,
`tests/unit/test_scenarios.py`). Hubness es self-query sobre `S`; samplear `ids[:n]`
después del append dejaba los hubs afuera. Drifted congela centroides de fit para que
`open_scenario` no refitee IVF.

**Segunda instancia, encontrada al escribir MI-04.** No es solo hubness. `synthetic-drifted`
—el escenario nombrado por `lance#4164`, appends dentro de celdas IVF existentes sin refit de
centroides— reporta `partition_size_cv = 1.0342 OK`, y
[`scenarios.py:199-203`](../vhecfsck/synthetic/scenarios.py) asserta `OK` para las cinco
métricas. O sea: **tres de las cinco métricas no tienen un solo positivo patológico en toda
la calibración de referencia**, porque ningún operador de patología las mueve. El test de
MI-01 tiene que cubrir a los dos operadores, no solo a `inject_hubs`.

## MI-03 — ADR-0006 atribuye 0.25/0.40 a "la literatura de hubness" · **ENTREGADO**

> Entregado: ADR-0006 lleva un bloque de corrección en el encabezado, la frase sobre "the
> hubness literature" está tachada en su lugar con la cita real de Radovanović et al., y el
> status declara que la justificación de los umbrales quedó superada por ADR-0011 / P8-02.
> La decisión sobre el régimen de sampleo —el tema real del ADR— no se tocó.

**La afirmación.** [`adr/0006-hubness-sampling-regime.md`](adr/0006-hubness-sampling-regime.md)
§Context dice: *"Warn `0.25` / fail `0.40` are recognisable values from the hubness
literature"*. Sin cita.

**La fuente real.** Radovanović, Nanopoulos e Ivanović, *Hubs in Space: Popular Nearest
Neighbors in High-Dimensional Data*, JMLR 11:2487–2531 (2010) — el paper fundacional de
hubness — mide hubness como la **asimetría de `N_k`** (tercer momento estandarizado,
`S_Nk`) y define antihubs como los puntos con `N_k = 0`. No publica los umbrales 0.25/0.40,
y "top-1% hub share" no aparece en ese cuerpo de trabajo.

**Medido, y por eso importa.** Barrido propio sobre gaussianas isotrópicas sanas:

| d | `hub_share_top1pct` | estado | nota |
| ---: | ---: | :--- | :--- |
| 16 | 0.0495 | OK | |
| 64 | 0.1466 | OK | |
| 128 | 0.1870 | OK | `antihub` 0.2585 → WARN |
| 384 | 0.2305 | WARN | |
| 768 | 0.2520 | WARN | |

Datos sanos rompen el umbral desde `d = 128`. Eso es exactamente lo que P8-02 descubrió y
parchó con los perfiles por dimensión ([lección 52](lessons-learned.md#52)). El ADR quedó
falsificado por el propio trabajo posterior del repo y **nunca se anotó como superado**.

**Ticket.** Anotar ADR-0006 como parcialmente superado por ADR-0011 / P8-02, borrar la
atribución a la literatura o reemplazarla por la cita real, y declarar los umbrales por lo
que son: valores calibrados empíricamente en P8-02, no heredados.

## MI-04 — `docs/calibration/` publica tasas de error sin el positivo que las sostiene · **ENTREGADO (retractación)**

> Entregado: `thresholds.md` separa **Measured FPR** de **Measured FNR** en las tres
> métricas afectadas y marca el FNR como no medido, con el escenario que lo demuestra en
> cada caso; el Executive Summary lleva un recuadro que dice qué establece y qué no
> establece esta calibración; y `docs/calibration/README.md` —la portada de la sección en el
> sitio— gana una sección "Known gaps".
>
> **No** se editaron `results.csv` ni `reports/*.md`: los genera `scripts/calibrate.py` y
> una edición a mano se pierde en el próximo `make calibrate`. Regenerarlos es **MI-07**, y
> ese sí espera a MI-02.

**Medido contra el repo.**

[`docs/calibration/thresholds.md`](../docs/calibration/thresholds.md) líneas 70 y 89
publican, para `hub_share_top1pct` y `antihub_fraction`:

> **FPR / FNR:** `0.0%` false positives on isotropic Gaussian controls under per-dimension
> profiling

El número de FPR está respaldado por los controles gaussianos. **El FNR no está respaldado
por nada**: no hay un solo positivo patológico de hubness en la calibración, y por MI-01
tampoco lo habría aunque se corriera el escenario `hubby`. Publicar "FPR / FNR: 0.0%" en un
renglón donde solo se midió el FPR es guardrail 9 de [`AGENTS.md`](../AGENTS.md) — *"Never
write a number into documentation that nobody measured"*.

Para contraste, las dos métricas que sí tienen los dos lados medidos lo dicen con las dos
mitades separadas (`thresholds.md` líneas 25-26 y 34-35: rango sano **y** rango patológico
con el dataset que lo produce).

Además [`docs/calibration/results.csv`](../docs/calibration/results.csv) está generado
**antes** de los perfiles por dimensión, y lo muestra: fila 7 `gaussian-1536
antihub_fraction FAIL 0.43755`, fila 22 `gaussian-768 antihub_fraction FAIL 0.4177`. Son
controles sanos fallando, publicados como resultado de calibración de referencia.

**Ticket.** Regenerar `results.csv` con los perfiles vigentes (**MI-07**, ahora
desbloqueado: `make calibrate`, no editar CSV/MD a mano) y, en `thresholds.md`,
publicar FNR solo para las métricas que el CSV muestre como positivo patológico.
`partition_size_cv` en `synthetic-drifted` sigue debajo del piso WARN (`0.9160 OK`)
salvo que el artefacto nuevo diga otra cosa.

## MI-05 — Falta `S_Nk`, la única medida de hubness que un paper reconocería

El reporte ya expone `max_nk`, `p99_nk`, `median_nk` y el histograma
([`vhecfsck/core/hubness.py:331-333`](../vhecfsck/core/hubness.py)). No expone la asimetría
de `N_k`, que es **la** definición publicada de hubness (Radovanović et al. 2010, §2).

Se calcula en tres líneas sobre un array que ya está en memoria, no requiere una segunda
pasada sobre el corpus y no cambia ningún umbral existente:

```text
S_Nk = mean((N_k - mean(N_k))^3) / std(N_k)^3      # tercer momento estandarizado
```

**Ticket.** Agregar `S_Nk` a `detail` de las métricas de hubness como valor informativo
(sin umbral propio hasta calibrarlo), y citarlo en el spec. Vale la pena por sí solo:
convierte un bloque de estadísticas ad-hoc en algo comparable con la literatura.
Contrato operativo (Fixture B a mano, `ddof=0`, `S_Nk = 0.0` en B, cola):
[`next-ticket.md`](next-ticket.md) § MI-05.

## MI-06 — `recall_dist` está publicada; el spec la presenta como invención propia · **ENTREGADO**

> Entregado: `02-metrics-spec.md` §2.2 cita ANN-Benchmarks con DOI y la fórmula textual, y
> §2.3 paso 5 cita Efron (1979) y **declara la desviación**: el CI se ensancha para contener
> la media, así que ya no es un percentil bootstrap puro. Eso estaba solo en un comentario
> de `canary.py`.

Este es el hallazgo bueno. [`roadmap/02-metrics-spec.md:112`](02-metrics-spec.md) presenta
la recall tolerante a empates como **"[CORRECTION 2]"**, es decir, como una corrección
propia al spec fuente. No lo es: es la definición estándar de ANN-Benchmarks.

> Aumüller, Bernhardsson, Faithfull, *ANN-Benchmarks: A benchmarking tool for approximate
> nearest neighbor algorithms*, **Information Systems** 87 (2019), DOI
> [10.1016/j.is.2019.02.006](https://doi.org/10.1016/j.is.2019.02.006), §2.1:
>
> `recall_ε(π, π*) = |{p ∈ π : dist(p, q) ≤ (1 + ε) · dist(p*_k, q)}| / k`

Es literalmente la fórmula implementada, con `ε = rtol`. Citarla **fortalece** la
herramienta en vez de exponerla: deja de ser "nosotros corregimos el spec" y pasa a ser
"esto es lo que mide el benchmark de referencia del área".

Dos cosas más que conviene declarar en el mismo ticket:

- **Citar Efron (1979)** para el bootstrap percentil del intervalo de confianza.
- **Declarar la desviación de [`vhecfsck/core/canary.py:466`](../vhecfsck/core/canary.py)**:
  el CI se expande para contener la media (`ci_lo = min(ci_lo, mean_dist)`). Está comentada
  en el código, pero no está ni en el spec ni en el JSON del reporte. Un CI que se expande
  para contener el estimador puntual ya no es un percentil bootstrap puro, y un lector
  externo tiene derecho a saberlo por el reporte, no leyendo el fuente.

---

## Lo que está bien y no hay que tocar

Enumerado explícitamente para que nadie lo "arregle" en una pasada futura:

| Ítem | Estado |
| :--- | :--- |
| `recall_id` | correcto |
| `partition_size_cv` | CV poblacional con `ddof=0`; normativo, Fixture C verificada a mano |
| Coeficiente de Gini | forma cerrada estándar, revisado término por término |
| `dfi` | métrica acuñada por el repo **y declarada como tal** — eso es honesto, no un defecto |
| Clamp de L2 antes del `sqrt` | correcto ([lección 28](lessons-learned.md#28)) |
| Proyección PCA a 3D | correcta |
