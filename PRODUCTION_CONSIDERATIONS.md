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

When building autonomous agents that execute SQL on data warehouses, several practical safeguards must be established:

* **Guardrails for "Runaway" Queries:** If the LLM hallucinates an unoptimized `CROSS JOIN` across large lakehouse tables, it can cause severe compute bottlenecks. The system must utilize **Trino Resource Groups** and strict query execution timeouts. If a query times out, the agent must be able to gracefully handle the error and attempt to rewrite it more efficiently (e.g., adding `LIMIT` or time-bounded `WHERE` clauses).
* **Infinite Loop Prevention:** The Strands Agent is autonomous. If a query fails validation, it will retry. We must enforce strict `max_steps` or `max_retries` limits in the orchestrator to prevent runaway API token burn.
* **Simplifying Complex JOINs with MDL:** Writing SQL that joins 5+ tables is a common failure point for LLMs. Instead of forcing the LLM to navigate the raw schema, we map physical Iceberg tables to logical YAML models using **WrenAI's Modeling Definition Language (MDL)**. This flattens the schema and provides explicit business definitions that the LLM cannot hallucinate.
* **Governing Business Metrics via Cubes:** Rather than asking the LLM to hallucinate complex `GROUP BY` logic, we define standardized metrics (e.g., ARR, WAU) directly within WrenAI **Cubes**.

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
