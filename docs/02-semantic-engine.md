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

1. **Table Discovery (RAG)** *[Implemented in Module 2]*: RAG is used to retrieve schema items relevant to the query. WrenAI uses its embedded **LanceDB** vector store as a *local, rebuildable index* (`.wren/memory/`) to identify the exact tables relevant to the user's intent. The actual version-controlled source of truth lives securely in our `src/semantic_engine/models/` folder.
2. **Schema Validation (Live Agent Tools)** *[Implemented in Module 3]*: To prevent hallucinations due to schema drift (e.g., deleted or added columns), the agent is equipped to query live database metadata (like Trino's `information_schema.columns`) for the retrieved tables *before* executing the final SQL. This guarantees up-to-the-second accuracy.

### 🛡️ Implementation Considerations

When building the agentic semantic layer, several practical safeguards must be established:

* **Guardrails for "Runaway" Queries:** If the LLM hallucinates an unoptimized `CROSS JOIN` across large lakehouse tables, it can cause severe compute bottlenecks. The system must utilize **Trino Resource Groups** and strict query execution timeouts. If a query times out, the agent must be able to gracefully handle the error and attempt to rewrite it more efficiently (e.g., adding `LIMIT` or time-bounded `WHERE` clauses).
* **Pragmatic Ambiguity Resolution:** Terms like "revenue" are ambiguous. The orchestrator (Strands) handles ambiguity. Once clarified, conversational memory (Mem0 over Qdrant) stores the user's preferences (e.g. "I mean net revenue when I say revenue"). Note: Mem0 handles user context; WrenAI handles authoritative semantic truth.
* **Data Governance & Security:** The agent translates natural language into SQL and executes it on the user's behalf. It must not have "God Mode" access. We rely on **Trino's built-in access control** and Iceberg column-level security so that unauthorized queries (e.g., accessing PII) are rejected at the database level, and the agent can appropriately reply, "I don't have permission to view that data."
* **Simplifying Complex JOINs with MDL:** Writing SQL that joins 5+ tables is a common failure point for LLMs. Instead of forcing the LLM to navigate the raw schema, we build predefined semantic models and relationships using **WrenAI's Modeling Definition Language (MDL)**. By mapping physical Iceberg tables to logical YAML models in the `src/semantic_engine/` directory, we flatten the schema and provide explicit business definitions that the LLM cannot hallucinate.

## 🚀 Managing the Semantic Engine

> **Prerequisite:** Ensure you have fully completed [Module 1](./01-lakehouse-foundation.md) before starting. The `odctl` infrastructure must be running, the Iceberg data must be generated, and your `.venv` must be active. The `wrenai` package is already installed via `src/requirements.txt`.

We have fully automated the lifecycle of the WrenAI Semantic Layer via a Management CLI suite (`src/semantic_engine/manage_semantics.py`). 

Instead of manually typing arbitrary Wren CLI commands or handling one-off setup scripts, this CLI provides robust CRUD operations. It handles:

### Project Initialization (`init`)

It initializes the Wren V2 schema structure (`wren_project/`) and generates `wren_project.yml` pointing to the Trino data source.

```bash
python src/semantic_engine/manage_semantics.py init
```

### MDL Generation (`add`)

It maps the raw Iceberg tables and aggregated business views to semantic business concepts, outputting them as strict Modeling Definition Language (MDL) YAML files alongside explicit relationships to prevent AI hallucinations.

```bash
python src/semantic_engine/manage_semantics.py add all
```

### Context Compilation (`build`)

It natively compiles the semantic YAML definitions into the `mdl.json` manifest required by the Wren engine.

```bash
python src/semantic_engine/manage_semantics.py build
```

### Memory Indexing (`index`)

It populates the local `.wren/memory` LanceDB retrieval index for use by the RAG orchestrator.

```bash
python src/semantic_engine/manage_semantics.py index
```




