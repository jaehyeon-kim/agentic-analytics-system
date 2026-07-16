# Production Considerations

This document outlines the critical architectural decisions and safeguards required to take the *Agentic Analytics System* from a local single-instance PoC to a distributed, multi-instance production environment.

## Enhancing Query Performance Over Time

To ensure the agent consistently generates accurate SQL for complex business questions, we must leverage WrenAI's semantic memory. However, in a production environment running multiple Strands Orchestrator replicas, we face two architectural risks:
1. **Concurrent Write Issues:** If all instances attempt to share and write to a single LanceDB memory store (e.g., hosted on S3), it introduces complex distributed locking problems and database corruption risks.
2. **Instance Divergence:** If each instance is allowed to write to its own local memory dynamically (via the `--allow-write` flag and `store_query` tool), Instance A will learn Query X while Instance B learns Query Y, causing the agents to behave inconsistently.

To solve this, we must decouple the memory retrieval from the memory promotion process.

### Why We Need Semantic Memory

Without memory, an agent requires the entire semantic schema and all business rules injected into its prompt. Memory acts as a critical **retrieval accelerator** when scaling because:
* You have hundreds of models that exceed the LLM's context window.
* You need to retrieve *targeted* schema context (`get_context`) to avoid prompt bloat.
* You need to retrieve proven SQL examples (`recall_queries`) to prevent hallucinations and retry loops.

### Hierarchy of Semantic Authority

To understand how memory fits into a multi-instance deployment, it is important to understand the hierarchy of semantic truth in WrenAI:
1. **MDL (Models, Relationships, Cubes):** The definitive semantic contract.
2. **`knowledge/rules`:** Durable, reviewable rules that capture important business behavior.
3. **`knowledge/sql`:** Approved natural-language-to-SQL examples to help with recurring query patterns.
4. **Memory Index (LanceDB):** The read-only retrieval accelerator built on top of the first three layers. It helps the agent find the truth efficiently.

### Recommended Architecture: Read-Only Memory & Out-of-Band Promotion

Because LanceDB is derived from the real truth (Git), there is no need to engineer a complex, shared mutable database across replicas. Each Strands replica maintains its own local, **read-only** LanceDB cache. 

While WrenAI provides a `store_query` MCP tool (enabled via `--allow-write`) to persist queries dynamically, enabling this in a multi-instance production environment causes replicas to diverge. Instead, we lock down WrenAI memory to be strictly read-only at runtime and handle learning through an **out-of-band promotion workflow**:

1. **Read-Only Local Memory:** Each replica runs its local LanceDB cache, rebuilt strictly during deployment.
2. **Orchestrator Saves Candidates:** When a user explicitly confirms a SQL query (e.g., clicking "Like"), the *Strands Orchestrator* saves an immutable JSON event to S3.
3. **Periodic Promotion Job:** A scheduled job evaluates these S3 events and proposes Git updates to the authoritative Wren project (e.g., adding a new `knowledge/sql/example.md`).
4. **Deploy & Rebuild:** Once merged, instances pull the updated project and rebuild their local memory accelerators.

*For a comprehensive technical deep-dive on this promotion workflow and MCP prompting, see **Appendix A: Read-Only Memory & Promotion Architecture**.*

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
* **Feedback Loop to LanceDB:** When users receive an answer, they should be able to "upvote" or "downvote" it. Upvoted SQL triggers the Strands Orchestrator to push an immutable candidate to S3. This candidate is later evaluated and committed to `knowledge/sql/` in Git, continuously improving the agent's accuracy after each deployment.
* **Pragmatic Ambiguity Resolution:** Terms like "revenue" are ambiguous. The Strands orchestrator handles ambiguity. Once clarified, conversational memory (Mem0 over Qdrant) stores the user's preferences (e.g., "I mean net revenue when I say revenue"). *Note: Mem0 handles user context and preferences; WrenAI handles authoritative semantic truth.*

---

## Appendix A: Read-Only Memory & Promotion Architecture

While WrenAI provides a `store_query` tool (enabled via `--allow-write`) to persist new queries on the fly, enabling this in a multi-instance production environment causes instances to rapidly diverge. Instance A learns Query X, while Instance B learns Query Y.

To solve this, we implement a **Read-Only Memory & Out-of-Band Promotion** architecture.

### MCP Prompt Engineering: Forcing Memory Usage
WrenAI does **not** automatically consult LanceDB when `run_sql` or `dry_plan` is called. Memory retrieval is exposed as separate MCP tools. If your Strands agent does not explicitly call these tools, the LanceDB index is useless.

To fix this, the Orchestrator's system prompt must mandate the following workflow:
1. **`get_context`**: The agent MUST call this with the user's original question to retrieve only the relevant models, cubes, and columns. (Prevents prompt bloat).
2. **`recall_queries`**: The agent MUST call this to retrieve previously confirmed NL-to-SQL examples. (Prevents hallucinations and retries).
3. **`dry_plan` / `run_sql`**: The agent validates and executes the query based on the retrieved context.

### Promotion Workflow
Because production WrenAI instances run completely read-only (`wren serve mcp` without `--allow-write`), the learning loop is governed by the Orchestrator out-of-band:

```text
Strands application
├── owns conversation/session state
├── observes Wren MCP calls
├── obtains user feedback ("Like")
└── writes candidate JSON to S3

WrenAI (Read-Only)
├── owns MDL planning
├── validates semantic SQL
├── executes queries
└── serves get_context & recall_queries

Promotion job
├── reads candidate JSON from S3
├── deduplicates and reviews candidates
├── proposes Git changes (knowledge/sql)
└── triggers deployment & memory rebuild
```

### 1. Generating Learning Candidates

The **application orchestrator** (Strands) manages the learning candidates. The LLM should never have an unrestricted tool to autonomously submit candidates, as it cannot be trusted to evaluate its own semantic correctness.

**When to create a candidate:**
* A user explicitly confirms that a SQL query is correct (e.g., clicks "Like" or says "Yes, that's correct").

### 2. S3 Candidate Layout & Payload

Each Strands instance writes a unique, append-only JSON object to S3. This avoids distributed locks entirely.

```json
{
  "event_version": 1,
  "candidate_id": "17d72a2d-6f5c-498e-944e-1c7168b34033",
  "created_at": "2026-07-16T03:15:22.124Z",
  "instance_id": "agent-pod-a",
  "candidate_type": "sql_example",
  "question": "What was net revenue yesterday?",
  "sql": "SELECT ...",
  "evidence": {
    "dry_plan_passed": true,
    "execution_succeeded": true,
    "user_confirmed": true
  }
}
```

*Note: Never store query result rows or personal data in these events.*

### 3. Periodic Promotion Job

A scheduled job lists the pending candidate objects and proposes Git changes based on the discovery type:

* **SQL Example (`knowledge/sql/*.md`):** A commonly requested query or complex join pattern that repeatedly succeeds.
* **Business Rule (`knowledge/rules/*.md`):** Explicit clarifications (e.g., "cancelled orders do not count toward revenue").

Once the PR is merged, the next production deployment executes `wren memory index`. Every Wren instance rebuilds its read-only LanceDB cache from the central truth, and instantly begins benefiting from the newly approved queries via `recall_queries`.

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
