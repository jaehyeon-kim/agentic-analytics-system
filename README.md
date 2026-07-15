# Agentic Analytics System

A local, open-source stack for building context-aware, text-to-SQL AI agents over an Iceberg Lakehouse.

## Motivation and Benefits

Modern data ecosystems require systems that can autonomously reason about data, translate natural language into accurate queries, and maintain conversational context. However, tightly coupled, managed cloud AI services often struggle with complex business logic and create friction when integrating external databases.

This repository provides an open-source stack for building an Agentic Data System.

**Benefits:**
* **Accuracy:** Improves text-to-SQL reliability by constraining generation with explicit semantic models, relationships, business definitions and query validation.
* **Modularity:** Compute, storage, and AI orchestration are decoupled, preventing vendor lock-in.
* **Contextual Awareness:** Mem0 v3 provides built-in entity-linked graph memory over Valkey (Redis-compatible), improving retrieval of related user preferences, people, events and conversational facts without requiring a separate graph database.

## Table of Contents

- [Architecture](#architecture)
- [Query Flow](#query-flow)
- [Prerequisites](#prerequisites)
- [Module 1: Lakehouse Foundation](#module-1-lakehouse-foundation)
- [Module 2: Semantic Engine](#module-2-semantic-engine)
- [Module 3: Agentic Orchestrator](#module-3-agentic-orchestrator)

## Architecture

This architecture updates and extends the concepts from the [AWS Agentic Analytics Ready Lakehouse Workshop](https://catalog.workshops.aws/agentic-analytics-lakehouse/en-US), replacing managed cloud services with robust open-source alternatives.

```text
+-------------------+       +-----------------------+
|                   |       |                       |
|   User Request    | ----> |  Agent Orchestrator   |
|                   |       |  (Strands SDK)        |
+-------------------+       +-----------------------+
                                  |           |
                                  |           v
                                  |     +-------------------+
                                  |     |   Agent Memory    |
                                  |     |   (Mem0 v3)       |
                                  |     +-------------------+
                                  |           |
                                  |           v
                                  |     +-----------------------+
                                  |     |   Agent Vector DB     |
                                  |     |       (Valkey)        |
                                  |     +-----------------------+
                                  v
                            +-----------------------+
                            |   Semantic Engine     |
                            |       (WrenAI)        |
                            +-----------------------+
                               |                 |
                               v                 v
            +-----------------------+   +-------------------------------+
            |    Historical Data    |   |    Semantic Retrieval Index   |
            |   (Trino / Iceberg)   |   |        (Local LanceDB)        |
            +-----------------------+   +-------------------------------+
```

### Component Breakdown

| Component | Technology | Role |
|:---|:---|:---|
| **Agent Orchestrator** | [Strands SDK](https://github.com/strands-agents/sdk-python) | Autonomous AI agent framework (by AWS) that interprets natural language, plans multi-step tool calls, and coordinates the entire query pipeline via the Model Context Protocol (MCP). |
| **Semantic Engine** | [WrenAI](https://github.com/Canner/WrenAI) | Governed text-to-SQL compiler. Defines business logic as code using the Modeling Definition Language (MDL), plans physical SQL deterministically, and validates queries via `dry_plan` — preventing LLM hallucinations. |
| **Semantic Retrieval Index** | LanceDB (embedded) | Local vector database for RAG-based table discovery. Embeds MDL schema descriptions so the agent can retrieve only the relevant tables for a given question. |
| **Agent Memory** | Mem0 v3 over Valkey | Long-term conversational memory with entity-linked graph retrieval. Stores user preferences (e.g., "revenue means net revenue") across sessions. |
| **Historical Data** | Trino / Apache Iceberg | Distributed SQL engine over open table format. The physical query execution layer for lakehouse data. |
| **Object Storage** | SeaweedFS (S3-compatible) | Local S3-compatible storage backend for Iceberg table data and Parquet files. |

*(Note: Real-time data integration using Tinybird/ClickHouse and dynamic query routing between hot and cold storage are currently out of scope for this foundational phase, but the architecture is designed to be easily extended to support them in the future.)*

## Query Flow

1. **Context Check:** The orchestrator queries Mem0 (running on Valkey) to pull long-term preferences and context.
2. **Semantic Translation:** The request is sent to the semantic engine, which uses its MDL and LanceDB memory to map the request to accurate SQL.
3. **Validation & Execution:** The orchestrator agent validates the physical schema against live metadata before executing the final SQL against the Iceberg cold storage and returning the structured data.

```text
[User Request]
      │
      ▼
(1) Context Check
[Strands Orchestrator] <---> [Mem0 / Valkey]
      │
      ▼
(2) Semantic Translation
[WrenAI MDL] <---> [Local LanceDB]
      │
      ▼
(3) Execution
[Athena / Trino / Iceberg]
      │
      ▼
[Structured Data]
```

---

## Prerequisites

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and [Ollama](https://ollama.com/), then create and activate a local virtual environment using Python 3.12, and install the required dependencies (which includes the `odctl` orchestrator). Python 3.12 is explicitly required because Mem0 v3's NLP and entity-linking support (used in Module 3) does not yet provide wheels for Python 3.13+.

```bash
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r src/requirements.txt
```

---

## Module 1: Lakehouse Foundation

In this module, you will build the core batch data infrastructure for the Agentic Analytics Lakehouse using local open-source tools.

### Objectives

- Use the `odctl` orchestrator to launch a local Lakehouse stack (Trino, Iceberg REST Catalog, SeaweedFS, WrenAI).
- Use `dynamic-des` to instantly generate historical datasets (customers, products, orders, order items, payments, returns) and write them directly to SeaweedFS (S3) as Parquet files.
- Ingest the raw Parquet files into the Iceberg catalog as managed tables.

### 🛠️ Step 1: Launch the Infrastructure

We use the `odctl` package to manage our local data stack. This avoids the complexity of manual `docker-compose` configurations.

Initialize the Open Data Stack workspace and launch the core components (Trino, SeaweedFS, Iceberg Catalog).

```bash
odctl init
odctl up trino storage catalog
```

### 📊 Step 2: Generate the Historical Data

We use `dynamic-des`, an event simulation framework, configured with a fast-forward clock (`factor=0.0`) to instantly simulate e-commerce activity. The data is exported as flattened Parquet files directly to the SeaweedFS bucket (`s3://odctl-dev/landing`).

Run the data generator (configured for 90 days of history and 50,000 events per Parquet file):

```bash
python src/data_pipeline/generate_data.py --days 90 --batch_size 50000
```

> **Tip:** Object storage (SeaweedFS) can be accessed at [http://localhost:8889](http://localhost:8889).

### ❄️ Step 3: Iceberg Integration

Now that the raw Parquet data exists in the `odctl-dev` bucket, we need to load it into the Iceberg catalog as managed Iceberg tables.

> **Note:** For this PoC, the pipeline script performs a destructive reload. It drops any existing tables and re-ingests the data from scratch, ensuring a clean slate.

Execute the script directly:

```bash
python src/data_pipeline/run_pipeline.py
```

This script reads the raw data using PyArrow and writes formal Iceberg tables via the REST Catalog. Semantic descriptions are added directly to the MDL files in Module 2 rather than as Iceberg table comments.

### 🔎 Step 4: Query the Lakehouse

You can instantly query your newly registered Iceberg tables using Trino's SQL engine.

**Option A: Trino CLI (Terminal)**

The `odctl` Trino container comes with the CLI pre-installed. Drop into a SQL shell by running:

```bash
docker exec -it trino trino
```

**Option B: SQL Client (e.g. DBeaver)**

Connect your favorite SQL client using the built-in Trino driver with these credentials:
* **Host:** `localhost`
* **Port:** `8080`
* **Username:** `user`
* **Password:** *(Leave blank)*

<details>
<summary><strong>Example Queries</strong></summary>

#### 1. View the Structure (Catalogs & Schemas)

First, verify that Trino sees your Iceberg catalog and the namespace we created.

```sql
-- See all connected catalogs (you should see 'iceberg' and 'system')
SHOW CATALOGS;

-- See the databases/namespaces inside Iceberg (you should see 'ecommerce')
SHOW SCHEMAS FROM iceberg;

-- List all the tables we just generated
SHOW TABLES FROM iceberg.ecommerce;
```

#### 2. Inspect Table Schemas

You can use the `DESCRIBE` command to see the schema (column names and data types) of any table, exactly as PyIceberg registered them.

```sql
DESCRIBE iceberg.ecommerce.customers;

DESCRIBE iceberg.ecommerce.orders;
```

#### 3. Query the Raw Data

Run some basic selects to see the simulated data!

```sql
-- View 10 simulated customers
SELECT *
FROM iceberg.ecommerce.customers
LIMIT 10;

-- See the most recent orders placed
SELECT *
FROM iceberg.ecommerce.orders
ORDER BY created_at DESC
LIMIT 10;
```

#### 4. Run an Analytics Aggregation

Because Trino is a massively parallel SQL engine on top of Iceberg, you can run complex aggregations effortlessly. Try finding out the most popular order status:

```sql
SELECT status, COUNT(*) as total_orders
FROM iceberg.ecommerce.orders
GROUP BY status
ORDER BY total_orders DESC;
```

</details>

---

## Module 2: Semantic Engine

In this module, you will secure the AI's logic to prevent SQL hallucinations and ensure business metrics are calculated deterministically across your cold storage.

### Objectives

- Connect WrenAI to the Trino engine to access the underlying Iceberg tables and views.
- Define explicit semantic models and business metrics to provide strict guardrails against AI hallucinations.
- Configure WrenAI's **Table Discovery** (RAG) pipeline to dynamically retrieve relevant tables from the semantic index. **Schema Validation** against live metadata is handled by the Strands agent in Module 3.
- Create a "Golden Test Suite" of natural language questions and their exact SQL counterparts to evaluate execution accuracy.

### 🧠 Two-Layer Agentic Architecture

A major failure point of generative AI in data engineering is raw SQL hallucination. If an LLM is given raw tables and asked to join them on the fly, it will eventually generate incorrect business metrics.

This system solves the problem by separating concerns into two distinct layers:

**Layer 1 — Semantic Compiler: `WrenAI`**

WrenAI provides a **governed semantic compiler and execution boundary**. It does not interpret natural language or handle ambiguity. Instead, it:
1. Defines business logic as code using the [Modeling Definition Language](https://docs.getwren.ai/oss/concepts/what_is_mdl) (MDL schema version 5) — models, relationships, cubes, and metrics.
2. Plans physical SQL deterministically from logical semantic queries.
3. Validates and dry-runs queries against the backend before execution.

**Layer 2 — Autonomous Agent: `Strands SDK`**

The [Strands SDK](https://github.com/strands-agents/sdk-python) (by AWS) provides the autonomous reasoning layer. It:
1. Interprets natural language and maps ambiguous terms (e.g., "revenue") to the correct WrenAI semantic objects (cubes, models, views).
2. Orchestrates multi-step tool calls to WrenAI's MCP server — listing cubes, describing schemas, validating SQL via `dry_plan`, and executing queries.
3. Maintains conversational context via Mem0 to remember user preferences across sessions.

By combining these layers, the LLM never sees raw database tables. It only interacts with WrenAI's governed semantic API, which constrains its output to valid, deterministic SQL.

### 🛡️ Production Architecture

When migrating this local agentic semantic layer to a distributed, multi-tenant production environment, several safeguards and architectural changes must be made (e.g., S3-backed LanceDB, Kafka writing queues, semantic caching, and LLM guardrails). 

For a complete breakdown of how to scale this system securely, see our [Production Architecture & Considerations Guide](PRODUCTION_CONSIDERATIONS.md).

### 💾 Production Persistence (Query History)

The entire `.wren_project` directory is intentionally disposable.

The local `.wren/memory` directory is a derived LanceDB index. It can optionally be mounted on a persistent volume to avoid rebuilding it after ordinary container restarts.

Approved Text-to-SQL examples are represented by `knowledge/sql/*.md`. For this PoC, those files are generated during project initialization and are also disposable.

### 🚀 Managing the Semantic Engine

> **Prerequisite:** Ensure you have fully completed [Module 1](#module-1-lakehouse-foundation) before starting. The `odctl` infrastructure must be running, the Iceberg data must be generated, and your `.venv` must be active. The `wrenai` package is already installed via `src/requirements.txt`.

We have fully automated the lifecycle of the WrenAI Semantic Layer via a Management CLI suite (`src/semantic_engine/manage_semantics.py`).

Instead of manually typing arbitrary Wren CLI commands or handling one-off setup scripts, this CLI provides robust CRUD operations.

<details>
<summary>Project Initialization (<code>init</code>)</summary>

WrenAI uses a generated project directory structure (schema version 5) to manage its semantic models. This command initializes the `.wren_project/` directory and generates a `wren_project.yml` file pointing to our Trino data source. By keeping the semantic logic decoupled from the database, we treat our business logic as code.

```bash
# We must export WREN_HOME to ensure Wren AI uses the localized profiles.yml inside our project
export WREN_HOME=$(pwd)/src/semantic_engine/.wren_project

python src/semantic_engine/manage_semantics.py init
```

</details>

<details>
<summary>MDL Generation (<code>add</code>)</summary>

LLMs are notoriously bad at guessing complex SQL joins or understanding what a column like `status` means. Wren solves this using the Modeling Definition Language (MDL). This command maps our raw Iceberg tables into semantic YAML files and explicitly defines business metrics as Cubes. It explicitly defines descriptions, primary keys, and exact one-to-many relationships (e.g., *exactly* how `customers` joins to `orders`). By doing this, we create a governed sandbox where the AI cannot hallucinate invalid join paths.

```bash
python src/semantic_engine/manage_semantics.py add all
```

</details>

<details>
<summary>Context Compilation (<code>build</code>)</summary>

WrenAI doesn't read the scattered YAML files at runtime. Instead, this command natively compiles all the YAML definitions, relationships, and business rules into a single, highly optimized `mdl.json` manifest. The Wren execution engine uses this manifest to plan physical SQL queries deterministically.

```bash
python src/semantic_engine/manage_semantics.py build
```

</details>

<details>
<summary>Memory Indexing (<code>index</code>)</summary>

If you have 500 tables, you cannot fit the entire schema into an LLM's context window. Wren solves this by building a local vector database using **LanceDB** to support **RAG-capable schema retrieval**. This command reads the table and column descriptions from your MDL files and embeds them.

Note that Wren defaults to full context rather than similarity search for smaller schemas (under ~30,000 characters). This is intentional because full context generally works better when it fits.

```bash
python src/semantic_engine/manage_semantics.py index
```

**Dynamic Indexing (Daemon Mode):** Instead of manually re-indexing on every MDL change, you can run `wren memory watch -i 2` in the background. This daemon watches `mdl.json` and `knowledge/sql/*.md` files, automatically re-indexing LanceDB within 2 seconds of any change.

To explicitly demonstrate embedding retrieval and force RAG behavior regardless of schema size, you can run a fetch with a low threshold:

```bash
cd src/semantic_engine/.wren_project

wren memory fetch \
  --query "net revenue and processed refunds" \
  --threshold 1 \
  --output json
```

</details>

<details>
<summary>Verifying the Trino Profile and Queries</summary>

Once the project is initialized and indexed, you can verify that WrenAI is correctly connected to the Lakehouse. Our management script natively generates a localized connection profile inside `.wren_project` to keep your environment clean.

```bash
# Verify the active profile (Requires WREN_HOME to be exported as detailed above)
wren profile debug

# Run the extensive automated test suite to validate joins and cubes
python src/semantic_engine/manage_semantics.py test
```

The profile should point to `localhost:8080`, using the `iceberg` catalog and `ecommerce` schema, and the test suite should execute all queries successfully.

</details>

---

## Module 3: Agentic Orchestrator

In this module, you will bring the AI orchestrator to life by connecting it to your data lakehouse using the Model Context Protocol (MCP).

### Objectives

- Leverage WrenAI's native MCP server (`wren serve mcp`) to securely expose the semantic layer to the AI agent, removing the need for manual database connection boilerplate.
- Build a Python CLI agent using the **Strands SDK** — AWS's open-source agentic AI framework that natively supports tool calling via the Model Context Protocol (MCP).
- Connect Strands to **Amazon Bedrock** (default) or any LiteLLM-compatible model (Gemini, OpenAI, Ollama).
- The Strands agent autonomously spawns WrenAI's MCP server (`wren serve mcp`) as a subprocess, discovers available semantic tools, and orchestrates multi-step query planning — from schema exploration to SQL validation and execution — without hardcoded logic.

### 🏗️ Text-to-SQL Architecture & Validation

Based on modern LLM architecture patterns (e.g., [Pinterest's Text-to-SQL approach](https://medium.com/pinterest-engineering/how-we-built-text-to-sql-at-pinterest-30bad30dabff)), building an effective Text-to-SQL system requires addressing **schema scale** and **schema drift**. To ensure robust querying, we employ a hybrid approach powered by WrenAI's native MCP integration:

1. **Table Discovery (RAG)** *[Implemented in Module 2]*: RAG is used to retrieve schema items relevant to the query. WrenAI uses its embedded **LanceDB** vector store as a *local, rebuildable index* (`.wren/memory/`) to identify the exact tables relevant to the user's intent. For this PoC, the semantic project is generated dynamically from the models, relationships, and knowledge definitions inside `manage_semantics.py`.
2. **Schema & Syntax Validation (Native MCP Tools)** *[Implemented in Module 3]*: The Strands agent utilizes WrenAI's native MCP endpoints to cross-reference the MDL and validate generated SQL using the `dry_plan` tool. This tests the logic and syntax against live metadata without executing a potentially expensive physical query, acting as a structural safeguard against hallucinations.

### Incorporating Mem0

This module integrates Mem0 v3 over Valkey (Redis-compatible) for long-term memory, entity-linked retrieval and improved cross-memory reasoning.

*(Note: Dynamic query routing between real-time and historical databases can be implemented as an extension.)*

### 🚀 Setting up the LLM

The orchestrator defaults to **Amazon Bedrock** for model access (using your AWS credentials), with an optional **LiteLLM API key** fallback for providers like Gemini, OpenAI, or local Ollama.

1. Copy the environment template: `cp src/agent/.env.example src/agent/.env`
2. Configure your preferred backend:

**Option A: Amazon Bedrock (Default)**

*(Example Configuration)*
Set your AWS profile, region, and a Bedrock inference profile ID:

```env
BEDROCK_MODEL_ID="apac.anthropic.claude-sonnet-4-20250514-v1:0"
AWS_PROFILE="default"
AWS_REGION="ap-southeast-2"
```

> **Tip:** Use `aws bedrock list-inference-profiles --region <region>` to find available inference profile IDs for your account.

<details>
<summary>Option B: LiteLLM with API Keys</summary>

Set `AGENT_MODEL` and the corresponding API key for your chosen provider:

*(Example Configuration)*
```env
AGENT_MODEL="gemini/gemini-3.1-flash-lite"
GEMINI_API_KEY="your-gemini-key"
```

Then run the orchestrator with the `--use-api-key` flag (see below).

</details>

### 🚀 Running the Agent

With your LLM configured and your `.venv` activated, you can boot up the autonomous orchestrator:

> **Prerequisite:** Ensure your `WREN_HOME` environment variable is exported correctly, as detailed in Module 2. If you haven't set it yet, run `export WREN_HOME=$(pwd)/src/semantic_engine/.wren_project` in your active terminal before starting the orchestrator.

```bash
# 1. Activate your virtual environment (if not already active)
source .venv/bin/activate

# 2a. Run with Bedrock (default)
python src/agent/orchestrator.py

# 2b. Run with LiteLLM API keys (Gemini, OpenAI, Ollama, etc.)
python src/agent/orchestrator.py --use-api-key
```

Once you see `🧠 Orchestrator is online. Type 'exit' to quit.`, you can start asking natural language questions about your business data! The agent will autonomously connect to the WrenAI MCP server, explore the semantic schema, and generate/execute the physical SQL.

#### Example Queries & Expected Behavior

Here are three examples demonstrating how the agent dynamically routes queries:

**1. Hitting a Cube (Governed Metrics)**
> `User ❯ What is the revenue for orders that are delivered?`
*Behavior:* The agent discovers the `daily_revenue` cube, maps "revenue" to `gross_revenue`, and queries it. The LLM does not write the `GROUP BY` or `SUM()` logic — WrenAI compiles the deterministic SQL defined in the cube.

**2. Falling back to a Model (Raw Schema)**
> `User ❯ Show me all refunded amount of orders by status.`
*Behavior:* The agent checks cubes, realizes none cover refunds by status, and falls back to querying the raw `returns` model directly.

**3. Handling Missing Data Gracefully**
> `User ❯ Show me all returned orders and their return reasons.`
*Behavior:* The agent discovers the `returns` model but realizes there is no `return_reason` column. Instead of hallucinating, it explicitly informs the user that reasons are unavailable and asks if they want to query just the return statuses instead.

### 📊 Testing & Evaluation Plan

To measure the success of the Agentic Orchestrator, we will evaluate it using methodology inspired by industry benchmarks like [Spider](https://yale-lily.github.io/spider) and [BIRD](https://bird-bench.github.io/), focusing on **Execution Accuracy (EX)** over our internal E-commerce batch data.

**Testing Methodology:**
1. **Create a Golden Test Suite:** Develop a set of 20–50 natural language questions based on the batch data (e.g., *"What is the total revenue for users who bought more than 3 items?"*).
2. **Define Ground Truth SQL:** Manually write and verify the exact, correct SQL query for each question to serve as the ground truth.
3. **Execute via Agent:** Pass the natural language questions through the Strands SDK Orchestrator and WrenAI pipeline.
4. **Calculate Execution Accuracy (EX):** Execute both the generated SQL and the Ground Truth SQL against Trino. Compare the resulting data payloads. A perfect match of the output data (not just string matching the SQL query) counts as a success.

<details>
<summary>Test Suite Coverage</summary>

The evaluation suite ([`evaluations/golden_test_suite.json`](evaluations/golden_test_suite.json)) consists of rigorous test cases specifically designed to benchmark the AI's semantic reasoning capabilities:
- **Raw Table Navigation:** Tests the AI's ability to execute complex 3+ table JOINs, subqueries, and aggregations across the foundational Lakehouse schemas (e.g. joining `orders`, `order_items`, and `products`).
- **Semantic Routing:** Evaluates whether the AI correctly routes high-level business questions (e.g., "What was our net revenue?") to the pre-aggregated Lakehouse metric views (`daily_revenue`, `customer_lifetime_value`, `product_performance`) instead of attempting to blindly hallucinate raw schema calculations.
- **Edge Cases:** Challenges the AI with NULL value tracking (`LEFT JOIN`), complex Date logic, and cross-layer queries (e.g. joining an aggregated metric view with a raw dimension table).

</details>
