# Module 2: Semantic Data Layer

In this module, you will secure the AI's logic to prevent SQL hallucinations and ensure business metrics are calculated deterministically across your cold storage.

## Objectives
- Connect WrenAI to the Trino engine to access the underlying Iceberg tables.
- Define explicit semantic models and business metrics to provide strict guardrails against AI hallucinations.
- Understand and configure the hybrid approach for Text-to-SQL: utilizing **Table Discovery** (RAG) to dynamically find relevant tables and **Schema Validation** to prevent errors from schema drift.
- Create a "Golden Test Suite" of natural language questions and their exact SQL counterparts to evaluate execution accuracy.

## 🧠 Agentic Brain Philosophy

A major failure point of generative AI in data engineering is raw SQL hallucination. If an LLM is given raw tables and asked to join them on the fly, it will eventually generate incorrect business metrics.

This module solves this by introducing a purpose-built AI Semantic Layer:

### Text-to-SQL Engine: `WrenAI`
Rather than letting the AI figure out complex joins, we use **WrenAI** as the central semantic brain. 

WrenAI provides a **governed semantic compiler and execution boundary**. It does not autonomously handle natural-language ambiguity—that is the job of the Strands Agent in Module 3. Instead, Wren's responsibilities are:
1. Resolve logical models and explicit relationships.
2. Plan physical SQL and apply business definitions.
3. Validate and dry-run queries against the backend.

By defining our business logic (e.g., "Net Revenue") using WrenAI's modern Modeling Definition Language (MDL schema version 2), our Strands AI agent simply queries the WrenAI API. WrenAI dynamically plans the SQL, executes it against the underlying engine (Trino), and returns the deterministic result.

### 🏗️ Text-to-SQL Architecture & Validation

Based on modern LLM architecture patterns (e.g., [Pinterest's Text-to-SQL approach](https://medium.com/pinterest-engineering/how-we-built-text-to-sql-at-pinterest-30bad30dabff)), building an effective Text-to-SQL system requires addressing **schema scale** and **schema drift**. To ensure robust querying, we employ a hybrid approach:

1. **Table Discovery (RAG)** *[Implemented in Module 2]*: RAG is used to retrieve schema items relevant to the query. WrenAI uses its embedded **LanceDB** vector store as a *local, rebuildable index* (`.wren/memory/`) to identify the exact tables relevant to the user's intent. For this PoC, the semantic project is generated dynamically from the models, relationships, and knowledge definitions inside `manage_semantics.py`.
2. **Schema Validation (Live Agent Tools)** *[Implemented in Module 3]*: To prevent hallucinations due to schema drift (e.g., deleted or added columns), the agent is equipped to query live database metadata (like Trino's `information_schema.columns`) for the retrieved tables *before* executing the final SQL. This guarantees up-to-the-second accuracy.

### 🛡️ Implementation Considerations

When building the agentic semantic layer, several practical safeguards must be established:

* **Guardrails for "Runaway" Queries:** If the LLM hallucinates an unoptimized `CROSS JOIN` across large lakehouse tables, it can cause severe compute bottlenecks. The system must utilize **Trino Resource Groups** and strict query execution timeouts. If a query times out, the agent must be able to gracefully handle the error and attempt to rewrite it more efficiently (e.g., adding `LIMIT` or time-bounded `WHERE` clauses).
* **Pragmatic Ambiguity Resolution:** Terms like "revenue" are ambiguous. The orchestrator (Strands) handles ambiguity. Once clarified, conversational memory (Mem0 over Qdrant) stores the user's preferences (e.g. "I mean net revenue when I say revenue"). Note: Mem0 handles user context; WrenAI handles authoritative semantic truth.
* **Data Governance & Security:** The agent translates natural language into SQL and executes it on the user's behalf. It must not have "God Mode" access. We rely on **Trino's built-in access control** and Iceberg column-level security so that unauthorized queries (e.g., accessing PII) are rejected at the database level, and the agent can appropriately reply, "I don't have permission to view that data."
* **Simplifying Complex JOINs with MDL:** Writing SQL that joins 5+ tables is a common failure point for LLMs. Instead of forcing the LLM to navigate the raw schema, we build predefined semantic models and relationships using **WrenAI's Modeling Definition Language (MDL)**. By mapping physical Iceberg tables to logical YAML models in the `src/semantic_engine/` directory, we flatten the schema and provide explicit business definitions that the LLM cannot hallucinate.

### 💾 Production Persistence (Query History)

WrenAI's local LanceDB memory contains two distinct datasets:
1. `schema_items.lance`: Rebuildable vector embeddings of your MDL definitions.
2. `query_history.lance`: Stateful, valuable history of learned NL→SQL pairs.

```text
.wren/memory/
└── memory
    ├── __manifest
    │   ├── _transactions
    │   │   └── 0-b5e70e6b-2889-4848-ab2e-d2977c549911.txn
    │   └── _versions
    │       ├── 18446744073709551614.manifest
    │       └── latest_version_hint.json
    ├── query_history.lance
    │   ├── _transactions
    │   │   ├── 0-f3ea978f-9604-49f3-8e48-a9df86cfdedb.txn
    │   │   ├── 1-056de8a8-9743-4c63-881b-b405ab7515da.txn
    │   ├── _versions
    │   │   ├── 18446744073709551590.manifest
    │   │   ├── 18446744073709551591.manifest
    │   │   └── latest_version_hint.json
    │   └── data
    │       ├── 0000101111010000000001113345d64cf09ccaafb742872b13.lance
    │       ├── 000100001000010010101010fc8f9040ba9496d56528e2a8db.lance
    └── schema_items.lance
        ├── _transactions
        │   └── 0-b6132636-6776-4454-90f8-01caf546be5f.txn
        ├── _versions
        │   ├── 18446744073709551614.manifest
        │   └── latest_version_hint.json
        └── data
            └── 0111011110111001011100103f46024e49b56a250d77d23e43.lance
```

Because WrenAI expects a local filesystem path, you cannot use a direct `s3://` URI for the live LanceDB database. To ensure ACID compliance and prevent data loss across restarts, use a two-layered persistence strategy:

#### 1. Live Persistence (Docker Volume)
Mount a local persistent volume to ensure the LanceDB files survive standard container restarts.
```yaml
volumes:
  - wren_memory:/app/src/semantic_engine/.wren_project/.wren/memory
```

#### Production Query History Persistence
For this fully disposable PoC, we intentionally do not persist query history between clean starts. Every environment starts fresh when running `init`, `add all`, `build`, and `index`. 

In a production environment, you should preserve user-approved examples outside of the ephemeral `.wren_project/` folder (e.g., in a version-controlled `src/semantic_engine/seed_knowledge/sql/` directory). During initialization, these markdown files are copied into `.wren_project/knowledge/sql/` so that the `index` command can automatically embed them as durable, canonical few-shot examples for the agent.

## 🚀 Managing the Semantic Engine

> **Prerequisite:** Ensure you have fully completed [Module 1](./01-lakehouse-foundation.md) before starting. The `odctl` infrastructure must be running, the Iceberg data must be generated, and your `.venv` must be active. The `wrenai` package is already installed via `src/requirements.txt`.

We have fully automated the lifecycle of the WrenAI Semantic Layer via a Management CLI suite (`src/semantic_engine/manage_semantics.py`). 

Instead of manually typing arbitrary Wren CLI commands or handling one-off setup scripts, this CLI provides robust CRUD operations. It handles:

### Verifying the Trino Profile

WrenAI needs to know how to connect to the Lakehouse. The `odctl` orchestrator pre-configures this for you in the background. You can verify the Trino profile inside the semantic engine directory:

```bash
cd src/semantic_engine/.wren_project

wren profile debug
wren --sql "SELECT COUNT(*) FROM customers"
```
The profile should point to `localhost:8080`, using the `iceberg` catalog and `ecommerce` schema.

### Project Initialization (`init`)

WrenAI uses a generated project directory structure (schema version 5) to manage its semantic models. This command initializes the `.wren_project/` directory and generates a `wren_project.yml` file pointing to our Trino data source. By keeping the semantic logic decoupled from the database, we treat our business logic as code.

```bash
python src/semantic_engine/manage_semantics.py init
```

### MDL Generation (`add`)

LLMs are notoriously bad at guessing complex SQL joins or understanding what a column like `status` means. Wren solves this using the Modeling Definition Language (MDL). This command maps our raw Iceberg tables and aggregated Trino views into semantic YAML files. It explicitly defines descriptions, primary keys, and exact one-to-many relationships (e.g., *exactly* how `customers` joins to `orders`). By doing this, we create a governed sandbox where the AI cannot hallucinate invalid join paths.

```bash
python src/semantic_engine/manage_semantics.py add all
```

### Context Compilation (`build`)

WrenAI doesn't read the scattered YAML files at runtime. Instead, this command natively compiles all the YAML definitions, relationships, and business rules into a single, highly optimized `mdl.json` manifest. The Wren execution engine uses this manifest to plan physical SQL queries deterministically.

```bash
python src/semantic_engine/manage_semantics.py build
```

### Memory Indexing (`index`)

If you have 500 tables, you cannot fit the entire schema into an LLM's context window. Wren solves this by building a local vector database using **LanceDB** to support **RAG-capable schema retrieval**. This command reads the table and column descriptions from your MDL files and embeds them. 

Note that Wren defaults to full context rather than similarity search for smaller schemas (under ~30,000 characters). This is intentional because full context generally works better when it fits.

```bash
python src/semantic_engine/manage_semantics.py index
```

To explicitly demonstrate embedding retrieval and force RAG behavior regardless of schema size, you can run a fetch with a low threshold:
```bash
cd src/semantic_engine/.wren_project

wren memory fetch \
  --query "net revenue and processed refunds" \
  --threshold 1 \
  --output json
```


