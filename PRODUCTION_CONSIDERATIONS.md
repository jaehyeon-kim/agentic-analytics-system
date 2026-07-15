# Production Considerations

This document outlines the critical architectural decisions and safeguards required to take the *Agentic Analytics System* from a local single-instance PoC to a distributed, multi-instance production environment.

## Multi-Instance Deployment & Semantic Memory

In a production environment running multiple Strands Orchestrator replicas, we must solve the concurrent memory storage problem for WrenAI. 

### Concurrency Problem
By default, WrenAI's LanceDB-backed `MemoryStore` uses local disk (`~/.wren/memory`). Even if pointed to an S3 URI, Wren's application-level mutations (like schema reindexing) are not atomic—they often read data, drop the existing table, and recreate it. Concurrent schema updates from multiple instances will cause catastrophic race conditions where one replica drops a table that another is trying to read.

### Shared Reader, Single Writer Architecture
To safely scale, we decouple reads from writes:
* **Stateless Readers:** All Strands Orchestrator replicas act strictly as **readers**. They connect to a shared S3 URI to fetch context and query history.
* **Logical Writer Service:** All semantic mutations (schema reindexing, appending new approved golden queries, or query upserts) must be routed to a single logical writer service via a message queue (e.g., SQS FIFO or Kafka).
* **S3 Optimistic Locking & WrenAI Patch:** S3 conditional writes supply Lance's required atomic commit primitives, protecting individual commits. However, to bypass Wren's local file handling, a small Python patch is required.

*For a comprehensive technical deep-dive on S3 Optimistic Locking, Wren's application-level operations, and the required patching, see **Appendix A: Shared LanceDB Architecture Details** at the end of this document.*

## Multi-Tenancy & Data Isolation

* **Tenant-Specific Semantic Memory:** For multi-tenant B2B deployments, a single LanceDB memory store cannot be shared. The system must dynamically mount tenant-specific S3 prefixes (e.g., `s3://wren-memory/tenant-a/`) into the `WREN_HOME` context for each user session.
* **Trino RBAC & Connection Pooling:** The Strands agent translates natural language into SQL and executes it on the user's behalf. It must not have "God Mode" access. We rely on **Trino's built-in access control** and Iceberg column-level security so that unauthorized queries (e.g., accessing PII) are rejected at the database level. The agent can then appropriately reply, "I don't have permission to view that data."

## Agentic Safety & Guardrails

When building autonomous agents that execute SQL on data warehouses, several practical safeguards must be established.

### Full Table Scan Prevention

Iceberg tables and Trino can scan entire datasets if proper partition or sort key filters are not included in the WHERE clause. This is a critical risk because the Strands agent generates queries autonomously — neither WrenAI cubes nor models enforce mandatory partition filters.

**Cube queries** use a structured `CubeQuery` API with explicit `filters` and `time_dimensions` fields, which at least encourages filtering. However, nothing prevents the agent from querying `cube: daily_revenue, measures: [gross_revenue]` with no date range — causing Trino to scan every partition.

**Model queries** are even more exposed. When the agent falls back from cubes to raw models, it writes freeform SQL via `run_sql`. There is no structural constraint preventing `SELECT * FROM customers` with no WHERE clause, LIMIT, or partition filter.

*For a comprehensive breakdown of mitigation strategies across all four protection layers (prompt, semantic, engine, and storage), see **Appendix B: Query Scan Protection**.*

### Infinite Loop Prevention

The Strands Agent is autonomous. If a query fails validation, it will retry. We must enforce strict `max_steps` or `max_retries` limits in the orchestrator to prevent runaway API token burn.

### Simplifying Complex JOINs with MDL

Writing SQL that joins 5+ tables is a common failure point for LLMs. Instead of forcing the LLM to navigate the raw schema, we map physical Iceberg tables to logical YAML models using **WrenAI's Modeling Definition Language (MDL)**. This flattens the schema and provides explicit business definitions that the LLM cannot hallucinate.

### Governing Business Metrics via Cubes

Rather than asking the LLM to hallucinate complex `GROUP BY` logic, we define standardized metrics (e.g., ARR, WAU) directly within WrenAI **Cubes**.

## Performance & Semantic Caching

* **NL-to-SQL Semantic Caching:** LLM generation and Trino execution are slow and expensive. We should implement a semantic caching layer (e.g., Redis). If a user asks a question semantically identical to a previously approved query, we return the cached Trino result immediately, skipping the LLM and the database entirely.
* **Cost-Aware LLM Routing:** Using LiteLLM, we route simple schema lookups to fast, cheap models (like `gemini-2.5-flash`), and escalate to advanced reasoning models (like `o1` or `gemini-2.5-pro`) only when the semantic mapping or SQL logic is highly complex.

## Observability & User Context

* **OpenTelemetry Instrumentation:** We need to trace every step of the agent's thought process. If the agent hallucinates a tool call, we need distributed tracing (via LangSmith, Arize Phoenix, or Datadog) to debug the exact failure point.
* **Feedback Loop to LanceDB:** When users receive an answer, they should be able to "upvote" or "downvote" it. Upvoted SQL should be pushed into the SQS/Kafka "Single Logical Writer" queue to become a permanent Golden Seed Query in LanceDB, continuously improving the agent's accuracy over time.
* **Pragmatic Ambiguity Resolution:** Terms like "revenue" are ambiguous. The Strands orchestrator handles ambiguity. Once clarified, conversational memory (Mem0 over Qdrant) stores the user's preferences (e.g., "I mean net revenue when I say revenue"). *Note: Mem0 handles user context and preferences; WrenAI handles authoritative semantic truth.*

---

## Appendix A: Shared LanceDB Architecture Details

S3 optimistic locking is helpful, but it should be a safety mechanism—not your primary multi-instance coordination strategy. Your current `orchestrator.py` starts a separate Wren MCP subprocess for each Strands instance and points it at a local `WREN_HOME`. Therefore, multiple orchestrator replicas would currently create independent local Wren/LanceDB instances.

### What S3 Changes

Instead of replicating LanceDB between instances:
```text
Replica A: local LanceDB
Replica B: local LanceDB
Replica C: local LanceDB
```

Use one shared Lance dataset:
```text
Replica A ─┐
Replica B ─┼── s3://wren-memory/project-a/
Replica C ─┘
```

Lance supports S3-backed datasets and accepts `s3://...` URIs with object-store configuration. S3 now supports the atomic primitives Lance needs:
* `If-None-Match: *` — create only if the object does not already exist.
* `If-Match: <ETag>` — update only if the object has not changed.

Competing conditional writes result in one success while later conflicting writes fail with `412 Precondition Failed`. This matches Lance’s transaction protocol. Lance commits new manifest versions using atomic `put-if-not-exists`, and its transaction layer uses optimistic concurrency control, conflict detection and automatic rebasing where possible. 

S3 also provides strong read-after-write and strongly consistent listings, so after a successful commit, S3 itself immediately exposes the new objects.

### Important Wren Limitation

Current Wren cannot simply be configured with `WREN_MEMORY_PATH=s3://bucket/wren-memory`. Its `MemoryStore` converts the path into a `pathlib.Path`, calls `mkdir()`, and then connects LanceDB to that local path. 

You need a small Wren patch along these lines:
```python
if "://" in memory_path:
    resolved = memory_path
else:
    resolved = Path(memory_path).expanduser()
    resolved.mkdir(parents=True, exist_ok=True)

self._db = lancedb.connect(
    str(resolved),
    storage_options=storage_options,
)
```
Conceptually Wren must preserve `s3://` URIs instead of treating them as filesystem paths.

### What Optimistic Locking Does Not Solve

It protects **individual Lance commits**, but Wren has application-level operations composed of several commits.

**`store_query`**
This is a straightforward append: `table.add([record])`. Lance explicitly designs append transactions to coexist with other append transactions. Therefore, concurrent query-history appends are probably the safest Wren operation to distribute. However, Wren does not attach an idempotency key. A message retry can append the same NL→SQL record twice.

**Schema reindex**
Wren’s schema replacement does:
1. `drop schema table`
2. `create schema table`

Two instances doing that concurrently can interfere even when every underlying Lance commit is individually valid.

**Forget, overwrite and upsert**
Wren’s delete implementation:
1. reads the whole query table;
2. removes rows in memory;
3. drops the table;
4. recreates it.

The upsert workflow similarly reads existing data, identifies rows, deletes them and inserts replacements. S3 conditional writes cannot automatically turn that entire sequence into one transaction. Another writer may append between the read and table recreation, causing a lost update.

### Recommended Architecture

```text
                       ┌── Wren reader A
Strands replicas ──────┼── Wren reader B
                       └── Wren reader C
                                │
                                ▼
                  Shared S3-backed LanceDB
                                ▲
                                │
                  Single logical writer
                         SQS FIFO / Kafka
```

Use these rules:

| Operation | Execution |
| :--- | :--- |
| Recall/fetch/search | Any replica |
| Append approved query | Writer service |
| Query upsert/delete | Writer service |
| Schema reindex | Writer service |
| Reset/rebuild | Writer service |
| Compaction/index maintenance | Writer service |

S3 optimistic concurrency then protects you from accidental competing commits and failed leader transitions, but normal application traffic remains serialized through one logical writer.

### Better Schema-Rebuild Pattern

Do not replace the active schema index in place. Build a new immutable version:

```text
s3://wren-memory/project-a/releases/v41/
s3://wren-memory/project-a/releases/v42/
s3://wren-memory/project-a/current.json
```

Workflow:
1. Writer builds `releases/v42` completely
2. Writer validates `v42`
3. Writer reads `current.json` and its ETag
4. Writer updates `current.json` using `If-Match`
5. Readers detect `v42` and reopen the dataset

Here, S3 optimistic locking is particularly valuable. Two builders may produce candidate indexes, but only one can successfully move the `current.json` pointer from the expected previous version. You could use:

```json
{
  "project_version": "v42",
  "memory_uri": "s3://wren-memory/project-a/releases/v42/",
  "mdl_hash": "..."
}
```

### Summary

* multiple Strands/Wren readers
* shared S3-backed LanceDB
* one logical mutation writer
* S3 If-Match/If-None-Match as concurrency protection
* versioned schema-index releases
* idempotent query events

S3 optimistic locking makes shared S3 LanceDB considerably more viable, especially because it now supplies Lance’s required atomic commit primitive. However, you should still retain the single-writer design for Wren because Wren’s higher-level mutation workflows are not atomic Lance transactions.

---

## Appendix B: Query Scan Protection

Neither WrenAI cubes nor models enforce mandatory partition or sort key filters. The agent can generate queries that trigger full table scans on large Iceberg datasets, causing severe compute costs in Trino. This appendix details the risk and mitigation strategies across four protection layers.

### Risk Assessment by Query Path

| Query Path | Format | Partition Filter Enforced? | Risk Level |
|:---|:---|:---|:---|
| **Cube** (`query_cube`) | Structured `CubeQuery` API with `filters` and `time_dimensions` | No — but the structured API encourages it | Medium |
| **Model** (`run_sql`) | Freeform SQL | No — completely open | High |

WrenAI's `CubeQuery` API accepts runtime filters:

```
CubeQuery {
    cube: String,
    measures: Vec<String>,
    dimensions: Vec<String>,
    time_dimensions: Vec<TimeDimensionFilter>,  // date range + granularity
    filters: Vec<CubeFilter>,                   // eq, gt, lt, in, contains, etc.
    limit: Option<usize>,
}
```

However, the cube **definition** (`metadata.yml`) has no `pre_filter`, `required_filter`, or `partition_key` field. Nothing prevents the agent from querying `daily_revenue` with `measures: [gross_revenue]` and no time filter.

For model queries, the situation is worse. The agent writes arbitrary SQL via `run_sql` with no structural constraints. A query like `SELECT * FROM customers` would scan the entire table.

### Layer 1: Prompt-Level Protection

Update the orchestrator's system prompt to instruct the agent:

```
Query Safety Rules:
- When querying cubes with time dimensions, ALWAYS include a date range filter.
- ALWAYS include a LIMIT clause (default 1000) unless the user explicitly requests all rows.
- NEVER use SELECT * — always specify the exact columns needed.
- When querying time-series data, default to the last 90 days if the user does not specify a range.
- ALWAYS run dry_plan before run_sql to validate the query plan.
```

This is the weakest layer — the LLM may ignore instructions, especially under complex multi-step reasoning. It should never be the only protection.

### Layer 2: Semantic Layer Protection

Use `dry_plan` as a validation gate. The agent's workflow should always be:

1. Generate SQL
2. Call `dry_plan` to validate
3. Inspect the plan for full scan indicators
4. Only then call `run_sql`

A future enhancement could extend WrenAI's `dry_plan` response to include estimated scan size or a warning when no partition filter is detected. This would give the agent a structured signal to add filters before execution.

Additionally, WrenAI cube definitions could benefit from a `required_filters` field:

```yaml
name: daily_revenue
base_object: orders
required_filters:
  - dimension: order_date
    message: "A date range is required to prevent full table scans."
```

This does not exist today and would be a valuable feature request to the WrenAI project.

### Layer 3: Engine-Level Protection (Trino)

Trino provides several built-in mechanisms to kill or reject expensive queries:

**Resource Groups** — Assign the agent's Trino user to a resource group with strict limits:

```json
{
  "name": "agent-queries",
  "maxRunning": 5,
  "hardConcurrencyLimit": 10,
  "maxQueued": 20,
  "softMemoryLimit": "1GB",
  "hardMemoryLimit": "2GB",
  "queryExpirationTimeout": "30s"
}
```

**Session-level scan limits** — Reject queries that would scan too much data:

```sql
SET SESSION query_max_scan_physical_bytes = 1073741824;  -- 1 GB
```

If the query exceeds the scan limit, Trino returns an error. The agent receives this error and can retry with tighter filters (e.g., adding a date range or LIMIT).

**Query execution timeout** — Hard kill after a time limit:

```
query.max-execution-time=30s
```

Engine-level protection is the strongest layer because it works regardless of what the agent generates. Even if the LLM ignores prompt instructions and the semantic layer has no filter enforcement, Trino will reject or kill the query before it consumes excessive resources.

### Layer 4: Storage-Level Protection (Iceberg)

Configure Iceberg tables with appropriate partitioning so that Trino's partition pruning activates automatically when a WHERE clause includes the partition column:

```sql
ALTER TABLE iceberg.ecommerce.orders
SET PROPERTIES partitioning = ARRAY['month(created_at)'];
```

With monthly partitioning on `created_at`, a query filtered by `WHERE created_at >= DATE '2026-01-01'` will only scan the relevant partitions rather than the entire table. Combined with Iceberg's sorted file organization and Parquet predicate pushdown, this dramatically reduces I/O even when the agent's filters are broad.

### Recommended Defense-in-Depth Strategy

| Layer | Mechanism | Strength | Bypassable by LLM? |
|:---|:---|:---|:---|
| **Prompt** | System prompt query safety rules | Weak | Yes — LLM may ignore |
| **Semantic** | `dry_plan` validation gate, future `required_filters` | Medium | Partially — agent could skip `dry_plan` |
| **Engine** | Trino resource groups, scan limits, timeouts | Strong | No — enforced by Trino |
| **Storage** | Iceberg partitioning and sort order | Strong | No — enforced by storage format |

All four layers should be implemented together. Prompt and semantic protections reduce the frequency of bad queries. Engine and storage protections guarantee that bad queries cannot cause damage when they do occur.

---

## Appendix C: Agentic Troubleshooting & Hallucination Prevention

When an LLM agent generates SQL autonomously, it can sometimes get caught in execution loops or hallucinate non-existent database structures. Below are the four most effective strategies for preventing and troubleshooting these failures.

### 1. Reserved Keyword Trap
If your semantic models share names with reserved SQL keywords (e.g., `returns`, `order`, `group`), the engine's SQL parser will throw a fatal syntax error. When the LLM encounters this syntax error, it often panics and attempts to "guess" the table name by hallucinating physical schema prefixes (e.g., `ecommerce.returns`, `pg_catalog.returns`), leading to an infinite failure loop.
* **Fix:** Rename the model in your WrenAI MDL to something unambiguous (e.g., `returned_orders`), OR enforce a strict system prompt rule requiring the agent to always wrap model names in double-quotes (e.g., `SELECT * FROM "returns"`).

### 2. MDL Descriptions as Guardrails
The most effective way to stop an LLM from searching for non-existent columns is to explicitly declare their absence within the semantic schema itself.
* **Fix:** Add explicit negative constraints to your `metadata.yml` descriptions. For example: `description: "Records of returned orders. NOTE: We do not track or store 'return reasons' anywhere in the database."` When the agent calls `describe_model`, it reads this and stops looking immediately.

### 3. Bounding Agent Retries
Frameworks like the Strands SDK allow agents to autonomously retry failed tool calls. If not bounded, a single syntax error can result in 10+ API calls, burning tokens and increasing latency.
* **Fix:** Instruct the agent via the system prompt to fail fast: *"If `run_sql` fails more than twice with syntax or table not found errors, STOP IMMEDIATELY and inform the user."* Additionally, if your agentic framework exposes an execution loop limit (e.g., maximum tool calls per turn), configure it strictly (e.g., 5 steps max) to serve as a hard circuit breaker.

### 4. WrenAI Knowledge Seeds (Few-Shot SQL)
If the LLM consistently struggles to plan a specific query structure, you can bypass its reasoning entirely using WrenAI's Knowledge engine.
* **Fix:** Add a Markdown file in the `knowledge/sql/` directory mapping the exact natural language phrase to a valid, tested SQL statement. When the user asks a similar question, WrenAI will intercept it and plan the correct SQL automatically, bypassing the LLM's query generation step.
