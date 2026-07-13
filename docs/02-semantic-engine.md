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

WrenAI is an open-source (Apache 2.0) Agentic Analytics layer that connects natively to our Lakehouse:
1. **Cold Layer:** Native connection to **Trino** to federate queries against our massive **Iceberg** catalog and S3 objects.

*(Note: Connecting to a hot layer like ClickHouse or Tinybird for real-time telemetry can be implemented as an extension.)*

By defining our business logic (e.g., "Net Revenue") using WrenAI's Modeling Definition Language (MDL), our Strands AI agent simply queries the WrenAI API in natural language. WrenAI dynamically generates the mathematically correct SQL, executes it against the underlying engine (Trino), and returns the deterministic result.

### 🏗️ Text-to-SQL Architecture & Validation

Based on modern LLM architecture patterns (e.g., [Pinterest's Text-to-SQL approach](https://medium.com/pinterest-engineering/how-we-built-text-to-sql-at-pinterest-30bad30dabff)), building an effective Text-to-SQL system requires addressing **schema scale** and **schema drift**. To ensure robust querying, we employ a hybrid approach:

1. **Table Discovery (RAG):** RAG (Retrieval-Augmented Generation) is used to index historical queries and table summaries. WrenAI uses its embedded **LanceDB** vector store (persisted robustly in **SeaweedFS**) to identify the exact tables relevant to the user's intent without stuffing the entire schema into the LLM context.
2. **Schema Validation (Live Agent Tools):** To prevent hallucinations due to schema drift (e.g., deleted or added columns), the agent is equipped to query live database metadata (like Trino's `information_schema.columns`) for the retrieved tables *before* executing the final SQL. This guarantees up-to-the-second accuracy.

### 🛡️ Implementation Considerations

When building the agentic semantic layer, several practical safeguards must be established:

* **Guardrails for "Runaway" Queries:** If the LLM hallucinates an unoptimized `CROSS JOIN` across large lakehouse tables, it can cause severe compute bottlenecks. The system must utilize **Trino Resource Groups** and strict query execution timeouts. If a query times out, the agent must be able to gracefully handle the error and attempt to rewrite it more efficiently (e.g., adding `LIMIT` or time-bounded `WHERE` clauses).
* **Pragmatic Ambiguity Resolution:** Terms like "revenue" are ambiguous (Gross vs. Net vs. MRR). The orchestrator (Strands + Mem0) must be designed to ask the user clarifying questions when the semantic engine detects ambiguity. Once clarified, the agent saves the preference to its long-term memory (Qdrant) so it doesn't have to ask again.
* **Data Governance & Security:** The agent translates natural language into SQL and executes it on the user's behalf. It must not have "God Mode" access. We rely on **Trino's built-in access control** and Iceberg column-level security so that unauthorized queries (e.g., accessing PII) are rejected at the database level, and the agent can appropriately reply, "I don't have permission to view that data."
* **Simplifying Complex JOINs with MDL:** Writing SQL that joins 5+ tables is a common failure point for LLMs. Instead of forcing the LLM to navigate the raw schema, we build predefined semantic models and relationships using **WrenAI's Modeling Definition Language (MDL)**. By mapping physical Iceberg tables to logical YAML models in the `src/semantic_engine/` directory, we flatten the schema and provide explicit business definitions that the LLM cannot hallucinate.

### 📊 Testing & Evaluation Plan

To measure the success of the Semantic Engine, we will evaluate it using methodology inspired by industry benchmarks like [Spider](https://yale-lily.github.io/spider) and [BIRD](https://bird-bench.github.io/), focusing on **Execution Accuracy (EX)** over our internal E-commerce batch data.

**Testing Methodology:**
1. **Create a Golden Test Suite:** Develop a set of 20–50 natural language questions based on the batch data (e.g., *"What is the total revenue for users who bought more than 3 items?"*).
2. **Define Ground Truth SQL:** Manually write and verify the exact, correct SQL query for each question to serve as the ground truth.
3. **Execute via Agent:** Pass the natural language questions through the Strands SDK Orchestrator and WrenAI pipeline.
4. **Calculate Execution Accuracy (EX):** Execute both the generated SQL and the Ground Truth SQL against Trino. Compare the resulting data payloads. A perfect match of the output data (not just string matching the SQL query) counts as a success.

## 🚀 Step-by-Step Guide

> **Prerequisite:** Ensure you have fully completed [Module 1](../module1-lakehouse-foundation/README.md) before starting. The `trino`, `storage`, and `catalog` containers must be running, and the Parquet data must be ingested into Iceberg.

### Step 1: Install WrenAI (Modern SDK Approach)

WrenAI has evolved from a heavy, multi-container Docker web app into a lightweight, deterministic Python SDK/CLI. This architecture allows seamless, native integration into our Python-based Agentic Analytics System.

1. Activate your local Python virtual environment (e.g., `source .venv/bin/activate`).
2. Install the modern `wrenai` package with Trino connector and LanceDB memory extensions:
   ```bash
   pip install "wrenai[trino,memory,main]"
   ```

### Step 2: Initialize WrenAI and LanceDB Memory

We use SeaweedFS as the robust S3-compatible backend for WrenAI's LanceDB memory.

1. Ensure your core storage is running (this automatically provisions the `wrenai-memory` bucket):
   ```bash
   odctl up storage
   ```
2. Initialize your local WrenAI project workspace:
   ```bash
   mkdir -p wren-project && cd wren-project
   wren context init
   ```
3. To configure WrenAI's embedded LanceDB memory to persist securely to SeaweedFS rather than local files, you can connect it using the `pyarrow` S3 interface in your Python scripts:
   ```python
   import lancedb

   db = lancedb.connect(
       "s3://wrenai-memory/lancedb_data",
       storage_options={
           "endpoint": "http://localhost:8333",
           "access_key_id": "user",
           "secret_access_key": "password" # Enforced by odctl infrastructure
       }
   )
   ```

### Step 3: Connect the Trino Data Source

You can securely register your Trino Lakehouse using the Wren CLI. From within your `wren-project` directory, add the Trino profile:

```bash
wren profile add trino
```

When prompted, input the standard `odctl` connection details:
- **Host:** `localhost` (if running locally on Mac) or `trino` (if inside Docker)
- **Port:** `8080`
- **User:** `user`
- **Password:** `password`
- **Catalog:** `iceberg`
- **Schema:** `ecommerce`

Once the profile is added, associate it with the project and build the semantic context:

```bash
wren context set-profile trino
wren context build
```

WrenAI is now fully configured natively in your agent environment, backed by robust object storage!
