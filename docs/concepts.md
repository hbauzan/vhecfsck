# Concepts & Target Pathologies

`vhecfsck` isolates five primary structural pathologies that cause vector search quality to degrade invisibly in production environments.

---

## 1. Silent Recall Decay

### What it is
Nearest neighbour recall drops while query latency, HTTP response codes (200 OK), and database health endpoints report perfect status.

### Why it is invisible
Standard database monitoring instruments infrastructure metrics (CPU, RAM, QPS, latency) rather than topological search accuracy. An index that returns 10 plausible-looking vectors in 2 ms passes all health checks even if 6 of those 10 vectors are incorrect.

### Primary Drivers
- Unindexed tombstone accumulation after deletion operations.
- Disconnected graph partitions in HNSW layers.
- Out-of-order appends altering IVF partition centroids.

---

## 2. Hubness (Central Point Dominance)

### What it is
A small fraction of corpus vectors ("hubs") appear in the top-k nearest neighbour result sets of an disproportionately high percentage of queries, dominating search results across unrelated queries.

### Why it is invisible
Query responses contain valid vector IDs and correct Euclidean/Cosine distance calculations. Without aggregate statistical sampling across diverse query spaces, hub dominance remains undetected.

---

## 3. Vector Orphaning (Antihub Fraction)

### What it is
Corpus vectors ("antihubs") become topologically unreachable during approximate nearest neighbour graph traversals or IVF candidate list scans, effectively rendering inserted data unsearchable.

### Why it is invisible
Data counts (`SELECT count(*)`) confirm that the vectors exist in storage, but index routing layers fail to navigate to their index nodes.

---

## 4. Deletion Fragmentation (Tombstone Accumulation)

### What it is
Deleted vectors remain present as "tombstones" in HNSW graph nodes or IVF inverted lists, consuming candidate scan budgets during search queries.

### Why it is invisible
Database engines mark rows as deleted in storage metadata but delay expensive index compaction or graph rebuilding. As tombstones accumulate, search precision drops precipitously.

---

## 5. Partition Size Imbalance (Centroid Skew)

### What it is
Inverted file (IVF) index list sizes diverge significantly (high Coefficient of Variation), causing candidate lists to become severely skewed across centroids.

### Why it is invisible
Queries landing in sparse partitions underperform while overall average index build and insert times appear normal.
