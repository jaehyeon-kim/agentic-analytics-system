# Agentic Analytics System

A local, open-source stack for building conversational data agents and semantic reasoning workflows over an Iceberg Lakehouse.

## Motivation

Generative AI has made conversational interfaces for analytics increasingly practical. However, direct text-to-SQL systems remain difficult to operate reliably in production. Database schemas describe tables, columns and data types, but they rarely capture canonical datasets, approved join paths, governed metrics or the intended meaning of business terms such as revenue, active customer or returned order.

A semantic layer addresses this gap by defining models, relationships, reusable metrics, business rules and approved query patterns independently of the language model. The agent can then reason over governed business concepts rather than attempting to infer business logic directly from raw database schemas.

This project extends the concepts demonstrated in the AWS Agentic Analytics Ready Lakehouse Workshop using a local, open-source and heterogeneous data stack. It does not assume that managed cloud services are inadequate; rather, it explores how independently developed technologies such as Strands, WrenAI, Trino, Apache Iceberg and external analytical platforms can be combined through open interfaces.

The result is a reference implementation for semantic-layer-backed conversational analytics, with separate components for agent orchestration, semantic planning, long-term user memory and physical query execution.

## Evaluating Semantic Layer and Analytics Agent Solutions

Building a reliable data assistant requires more than generating valid SQL. It must apply consistent business definitions, approved relationships, governed metrics, and controlled access to the underlying data model.

* **[WrenAI](https://www.getwren.ai/):** A semantic engine that uses MDL to define models, relationships, views, calculated fields, and cubes as a structured, executable semantic contract. It also supports a wide range of data sources, including Trino and ClickHouse.
* **[Vanna AI](https://vanna.ai/):** A flexible SQL-agent framework built around tools, memory, permissions, and learned query examples. It does not provide the same formal semantic modeling layer, and popular data sources such as Trino and ClickHouse would require custom database integration. Moreover, ts official open-source GitHub repository was archived on March 29, 2026.
* **[Nao](https://getnao.io/):** An integrated analytics-agent platform whose Context Builder stores business definitions, rules, metadata, and query examples primarily as Markdown-based context. This is flexible, but it relies more heavily on agent interpretation and is less suitable where strict enterprise control over semantic meaning is required.
* **[MetricFlow](https://docs.getdbt.com/docs/build/about-metricflow):** A formal semantic query engine for defining metrics, entities, dimensions, and relationships. It is closely aligned with dbt and OSI semantic models, while this project must also support objects that are not consistently represented in dbt.

### Why WrenAI Was Selected

1. Structured MDL models, relationships, views, calculated fields, and cubes.
2. Stronger control over business definitions, relationships, and metrics.
3. SQL generation without execution, allowing Strands to enforce tenant-aware authorization, validation, security policies, and controlled execution.
4. Greater flexibility to introduce enterprise security and governance controls around the semantic layer.
5. Deterministic expansion of logical semantic queries into physical SQL.
6. Support for a wide range of popular data sources, including Trino and ClickHouse.
7. Direct modeling of existing tables, views, and materialized objects.
8. Version-controlled definitions, separate business rules, reviewed SQL examples, native MCP tools, and a rebuildable LanceDB index.

WrenAI was selected because this project prioritises formal semantic governance and a clear separation between SQL generation and execution. This separation makes it easier to adapt the architecture for enterprise requirements such as tenant isolation, authorization, validation, and audit controls. Nao provides a broader integrated platform, but its flexible context model and end-to-end open-source workflow make these enforcement boundaries less explicit and more difficult to customise. Vanna lacks the required semantic modeling and native support for several relevant data sources, while MetricFlow is more closely aligned with dbt-oriented metric management.

## Table of Contents

- [Architecture](#architecture)
- [Query Flow](#query-flow)
- [Prerequisites](#prerequisites)
- [Infrastructure Setup](#infrastructure-setup)
- [Semantic Engine](#semantic-engine)
- [Agentic Orchestrator](#agentic-orchestrator)
- [Testing and Evaluation](#testing-and-evaluation)

## Architecture

This system relies on a fully decoupled, open-source stack. The AI orchestrator interprets requests and uses the Model Context Protocol (MCP) to interact with the Semantic Engine. The Semantic Engine plans deterministic queries using its business models and vector memory, which are then executed against the physical Lakehouse storage layer.

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
| **Semantic Engine** | [WrenAI](https://github.com/Canner/WrenAI) | Governed semantic query compiler. Defines business logic as code using the Modeling Definition Language (MDL), plans physical SQL deterministically, and validates queries via `dry_plan` - preventing LLM hallucinations. |
| **Semantic Retrieval Index** | LanceDB (embedded) | Local vector database for RAG-based table discovery. Embeds MDL schema descriptions so the agent can retrieve only the relevant tables for a given question. |
| **Agent Memory** | Mem0 v3 over Valkey | Persistent user and conversational memory using hybrid retrieval across semantic similarity, keyword matching and built-in entity linking. Mem0 stores entity embeddings in a parallel Valkey collection and boosts memories connected through shared entities, without requiring a separate graph database. |
| **Historical Data** | Trino / Apache Iceberg | Distributed SQL engine over open table format. The physical query execution layer for lakehouse data. |
| **Object Storage** | SeaweedFS (S3-compatible) | Local S3-compatible storage backend for Iceberg table data and Parquet files. |

*(Note: Real-time data integration using Tinybird/ClickHouse and dynamic query routing between hot and cold storage are currently out of scope for this foundational phase, but the architecture is designed to be easily extended to support them in the future.)*

## Query Flow

1. **Context Check:** The orchestrator queries Mem0 (running on Valkey) to pull long-term preferences and context.
2. **Semantic Translation:** The request is sent to the semantic engine, which uses its MDL and LanceDB memory to map the request to accurate SQL.
3. **Validation and Execution:** The orchestrator agent validates the physical schema against live metadata before executing the final SQL against the Iceberg cold storage and returning the structured data.

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
[Trino / Iceberg]
      │
      ▼
[Structured Data]
```

---

## Prerequisites

*   Install **[Docker](https://docs.docker.com/get-docker/)** (with compose support) to run the containerized local data infrastructure.
*   Install **[uv](https://docs.astral.sh/uv/getting-started/installation/)**, then create and activate a local virtual environment using Python 3.12, and install the required dependencies (which includes the `odctl` orchestrator). Python 3.12 is explicitly required because Mem0 v3's NLP and entity-linking support does not yet provide wheels for Python 3.13+.

```bash
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r src/requirements.txt
python -m spacy download en_core_web_sm
```

---

## Infrastructure Setup

In this section, you will build the core batch data infrastructure for the Agentic Analytics Lakehouse using local open-source tools.

### Objectives

- Use the `odctl` orchestrator to launch a local Lakehouse stack (Trino, Iceberg REST Catalog, SeaweedFS, WrenAI).
- Use `dynamic-des` to instantly generate historical datasets (customers, products, orders, order items, payments, returns) and write them directly to SeaweedFS (S3) as Parquet files.
- Ingest the raw Parquet files into the Iceberg catalog as managed tables.

### 🛠️ Step 1: Launch Infrastructure

We use the `odctl` package to manage our local data stack. This avoids the complexity of manual `docker-compose` configurations.

Initialize the Open Data Stack workspace and launch the core components (Trino, SeaweedFS, Iceberg Catalog).

```bash
odctl init
odctl up trino storage catalog valkey
```

### 📊 Step 2: Generate Historical Data

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

This script reads the raw data using PyArrow and writes formal Iceberg tables via the REST Catalog. Semantic descriptions are added directly to the MDL files in the Semantic Engine rather than as Iceberg table comments.

### 🔎 Step 4: Query Data

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

#### 1. View Structure

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

#### 3. Query Raw Data

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

#### 4. Run Analytics Aggregation

Because Trino is a massively parallel SQL engine on top of Iceberg, you can run complex aggregations effortlessly. Try finding out the most popular order status:

```sql
SELECT status, COUNT(*) as total_orders
FROM iceberg.ecommerce.orders
GROUP BY status
ORDER BY total_orders DESC;
```

</details>

---

## Semantic Engine

In this section, you will secure the AI's logic to prevent SQL hallucinations and ensure business metrics are calculated deterministically across your cold storage.

### Objectives

- Connect WrenAI to the Trino engine to access the underlying Iceberg tables and views.
- Define explicit semantic models and business metrics to provide strict guardrails against AI hallucinations.
- Configure WrenAI's **Table Discovery** (RAG) pipeline to dynamically retrieve relevant tables from the semantic index. **Schema Validation** against live metadata is handled by the Strands agent in the Orchestrator section.
- Create a "Golden Test Suite" of natural language questions and their exact SQL counterparts to evaluate execution accuracy.

### 🧠 Two-Layer Agentic Architecture

A major failure point of generative AI in data engineering is raw SQL hallucination. If an LLM is given raw tables and asked to join them on the fly, it will eventually generate incorrect business metrics.

This system solves the problem by separating concerns into two distinct layers:

**Layer 1 - Semantic Compiler: `WrenAI`**

WrenAI provides a **governed semantic compiler and execution boundary**. It:
1. Supplies governed context (MDL models, relationships, cubes, and metrics).
2. Expands modeled SQL through MDL (`dry_plan`).
3. Generates cube SQL, validates queries against the live backend (`dry_run`), and executes them through Trino (`run_sql`).

**Layer 2 - Autonomous Agent: `Strands SDK`**

The [Strands SDK](https://github.com/strands-agents/sdk-python) (by AWS) provides the autonomous reasoning layer. It:
1. Interprets the user question.
2. Calls tools like `get_instructions`, `get_context`, and `recall_queries`.
3. Selects a cube or constructs modeled SQL.
4. Decides which execution tool to invoke (`dry_plan`, `dry_run`, or `run_sql`).
5. Maintains conversational context via Mem0 to remember user preferences across sessions.

By combining these layers, the LLM never sees raw database tables. It only interacts with WrenAI's governed semantic API, which constrains available models and joins, improving consistency and reducing hallucination risk.

### 🛡️ Production Architecture

When migrating this local agentic semantic layer to a distributed, multi-tenant production environment, several safeguards and architectural changes must be made. Production deployment keeps Wren runtime memory read-only and local to each replica. Candidate queries are captured by the application, evaluated out of band, promoted into the version-controlled Wren project, and distributed through normal deployment. 

For a complete breakdown of how to scale this system securely, see our [Production Architecture & Considerations Guide](PRODUCTION_CONSIDERATIONS.md).

### 💾 Production Persistence

For this PoC, the `.wren_project` directory is disposable because `manage_semantics.py` regenerates it. 

For production, project persistence should be split:
* **Version-Controlled Source:** `models/`, `cubes/`, `relationships.yml`, `knowledge/rules/`, and `knowledge/sql/` should be managed as code.
* **Generated Artifacts:** `target/mdl.json` and `.wren/memory/` are disposable generated artifacts. The `.wren/memory` directory can optionally be mounted on a persistent volume to avoid rebuilding it after ordinary container restarts.

### 🚀 Managing Semantic Engine

> **Prerequisite:** Ensure you have fully completed the [Infrastructure Setup](#infrastructure-setup) before starting. The `odctl` infrastructure must be running, the Iceberg data must be generated, and your `.venv` must be active. The `wrenai` package is already installed via `src/requirements.txt`.

We have fully automated the lifecycle of the WrenAI Semantic Layer via a Management CLI suite (`src/semantic_engine/manage_semantics.py`).

Instead of manually typing arbitrary Wren CLI commands or handling one-off setup scripts, this CLI provides robust CRUD operations.

#### Project Initialization (init)

WrenAI uses a generated project directory structure (schema version 5) to manage its semantic models. This command initializes the `.wren_project/` directory and generates a `wren_project.yml` file pointing to our Trino data source. By keeping the semantic logic decoupled from the database, we treat our business logic as code.

```bash
# We must export WREN_HOME to ensure Wren AI uses the localized profiles.yml inside our project
export WREN_HOME=$(pwd)/src/semantic_engine/.wren_project

python src/semantic_engine/manage_semantics.py init
```

You can verify the generated connection profile (which should point to `localhost:8080`, using the `iceberg` catalog and `ecommerce` schema) by running:

```bash
wren profile debug
```

#### MDL Generation (add)

LLMs are notoriously bad at guessing complex SQL joins or understanding what a column like `status` means. Wren solves this using the Modeling Definition Language (MDL). This command maps our raw Iceberg tables into semantic YAML files and explicitly defines business metrics as Cubes. It explicitly defines descriptions, primary keys, and exact one-to-many relationships (e.g., *exactly* how `customers` joins to `orders`). By doing this, we create a governed sandbox where the AI cannot hallucinate invalid join paths.

```bash
python src/semantic_engine/manage_semantics.py add all
```

#### Context Compilation (build)

`wren context build` compiles models, relationships, views, and cubes into `target/mdl.json`. Business rules remain Markdown files under `knowledge/rules/` and are retrieved separately through `get_instructions`.

```bash
python src/semantic_engine/manage_semantics.py build
```

#### Memory Indexing (index)

If you have hundreds of models and approved query patterns, you cannot fit the entire schema and business context into an LLM's prompt. Wren solves this by building a local vector database using **LanceDB** to act as a **retrieval accelerator**. This command reads the table descriptions from your MDL files and the approved SQL examples from the `knowledge/sql/` directory, and embeds them. (Note: Business rules from `knowledge/rules/` are read separately via context instructions and are not embedded by the memory index).

```bash
python src/semantic_engine/manage_semantics.py index

# Output:
# INFO: 🧠 Indexing Semantic Memory (Vectorizing to local .wren/memory)...
# Indexed 64 schema items, 22 seed queries.
# Indexed 1 pair(s) from knowledge/sql/.
# INFO: 🎉 Semantic memory successfully indexed locally.
```

**How Memory is Structured:**
When you run the index command, WrenAI breaks your project into distinct vectors:
1. **Schema Items:** This is the structural index. Wren parses the MDL files and embeds Models, Views, Cubes, and metadata.
2. **Seed Queries:** This is an automated baseline index synthesized from relationships and cubes.
3. **Knowledge Pairs:** This is the manual query recall index from `knowledge/sql/`.

**Learning Over Time:** Most text-to-SQL systems treat every question like the first question. WrenAI adds a memory layer so successful work can improve future work. The memory index has two jobs:
1. **Schema context retrieval:** It retrieves only the relevant models (from the 64 items) and guidance for a specific question, which is critical when the total schema is too large for the LLM's prompt.
2. **Query recall:** It retrieves proven SQL examples (from the knowledge pairs or seed queries) to provide as few-shot context, completely preventing the LLM from hallucinating.

This turns usage into a learning loop. The memory becomes increasingly useful as your team asks, corrects, and confirms more questions, expanding the `knowledge/` base. *(Note: While WrenAI provides a `store_query` tool via `--allow-write` to update this dynamically, we lock this down in production. The Strands orchestrator securely captures liked queries and promotes them via Git to rebuild the index safely).*

*(For a technical deep-dive on how to safely deploy and manage this memory layer across multiple concurrent agent instances in production, see [PRODUCTION_CONSIDERATIONS.md](./PRODUCTION_CONSIDERATIONS.md)).*

Note that Wren defaults to full context rather than similarity search for smaller schemas (under ~30,000 characters). This is intentional because full context generally works better when it fits.

#### Running the Test Suite

Once the project is initialized and indexed, you can run the extensive automated test suite to validate joins and cubes against your Lakehouse:

```bash
python src/semantic_engine/manage_semantics.py test
```

The test suite should execute all queries successfully.

<details>
<summary>💡 Deep Dive: Daemon Mode & Manual RAG Fetching</summary>

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

---

## Agentic Orchestrator

> [!NOTE]
> The examples and outputs demonstrated in this section were generated using the **`gemini-3.1-flash-lite`** model. If you use a different LLM or provider (such as Claude 3.5 Sonnet on Bedrock), the exact query formatting and responses may vary slightly.

In this section, you will bring the AI orchestrator to life by connecting it to your data lakehouse using the Model Context Protocol (MCP).

### Objectives

- Leverage WrenAI's native MCP server (`wren serve mcp`) to securely expose the semantic layer to the AI agent, removing the need for manual database connection boilerplate.
- Build a Python CLI agent using the **Strands SDK** - AWS's open-source agentic AI framework that natively supports tool calling via the Model Context Protocol (MCP).
- Connect Strands to **Amazon Bedrock** (default) or any LiteLLM-compatible model (Gemini, OpenAI, Ollama).
- The Strands agent autonomously spawns WrenAI's MCP server (`wren serve mcp`) as a subprocess, discovers available semantic tools, and orchestrates multi-step query planning - from schema exploration to SQL validation and execution - without hardcoded logic.

### 🏗️ Semantic Reasoning Architecture & Validation

Based on modern LLM architecture patterns, building an effective semantic reasoning system requires addressing **schema scale** and **schema drift**. To ensure robust querying, we employ a hybrid approach powered by WrenAI's native MCP integration:

1. **Table Discovery (RAG)**: RAG is used to retrieve schema items relevant to the query. WrenAI uses its embedded **LanceDB** vector store as a *local, rebuildable index* (`.wren/memory/`) to identify the exact tables relevant to the user's intent. For this PoC, the semantic project is generated dynamically from the models, relationships, and knowledge definitions inside `manage_semantics.py`.
2. **Schema & Syntax Validation (Native MCP Tools)**: The Strands agent utilizes WrenAI's native MCP endpoints to validate generated SQL using the `dry_plan` and `dry_run` tools. `dry_plan` inspects the generated physical SQL, while `dry_run` validates it against Trino, acting as a structural safeguard before invoking `run_sql`.

### 🚀 Setting up LLM

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

### 🚀 Running Agent

With your LLM configured and your `.venv` activated, you can boot up the autonomous orchestrator:

> **Prerequisite:** Ensure your `WREN_HOME` environment variable is exported correctly. If you haven't set it yet, run `export WREN_HOME=$(pwd)/src/semantic_engine/.wren_project` in your active terminal before starting the orchestrator.

```bash
# 1. Activate your virtual environment (if not already active)
source .venv/bin/activate

# 2a. Run with Bedrock (default)
python src/agent/orchestrator.py

# 2b. Run with LiteLLM API keys (Gemini, OpenAI, Ollama, etc.)
python src/agent/orchestrator.py --use-api-key
```

Once you see `🧠 Orchestrator is online. Type 'exit' to quit.`, you can start asking natural language questions about your business data! The agent will autonomously connect to the WrenAI MCP server, explore the semantic schema, and generate/execute the physical SQL.

#### Example Queries

Here are three examples demonstrating how the agent dynamically routes queries:

**1. Hitting a Cube (Governed Metrics)**
> `User ❯ What is the revenue for orders that are delivered?`
*Behavior:* The agent discovers the `daily_revenue` cube, maps "revenue" to `gross_revenue`, and queries it. The LLM does not write the `GROUP BY` or `SUM()` logic - WrenAI compiles the deterministic SQL defined in the cube.

```sql
SELECT SUM(total_amount)
FROM iceberg.ecommerce.orders 
WHERE status = 'delivered';
```

**2. Falling back to a Model (Raw Schema)**
When a question doesn't fit neatly into a governed cube, the agent must generate a query using the raw schema models. This introduces the challenge of ambiguity in natural language.

**Case 1: Misleading Prompt**
> `User ❯ Show me all refunded amount of orders by status.`
*Behavior:* Because the prompt is ambiguous, the agent joins `returned_orders` to `orders` and groups by `orders.status`. Since an order must be delivered to be returned, it incorrectly aggregates everything under `delivered`.

```sql
SELECT o.status, SUM(r.refund_amount) AS total_refunded
FROM iceberg.ecommerce.returned_orders r
JOIN iceberg.ecommerce.orders o ON r.order_id = o.order_id
GROUP BY o.status;
```

**Case 2: Intended Prompt (Prompt Engineering)**
> `User ❯ Show me all refunded amount of orders by return status.`
*Behavior:* By explicitly specifying "return status", the agent correctly identifies that it should group by the `return_status` column inside the `returned_orders` model instead of joining to `orders`.

```sql
SELECT return_status, SUM(refund_amount) AS total_refunded
FROM iceberg.ecommerce.returned_orders
GROUP BY return_status;
```

**Case 3: Using `knowledge/rules` (Semantic Fix)**
Instead of relying on users to write perfect prompts, we can explicitly teach the semantic engine how to interpret ambiguous phrases by providing domain-specific Business Rules.

We have a built-in `refresh` command that automatically appends a strict definition to `knowledge/rules/business_definitions.md` and then recompiles the engine:

```markdown
## Refunds by Status
When the user asks for 'refunded amount by status' or 'refunds by status', they ALWAYS mean the `return_status` column from the `returned_orders` table. NEVER use the `status` column from the `orders` table for this metric.
```

Run the following command:

```bash
python src/semantic_engine/manage_semantics.py refresh
```
*Behavior:* This command writes the new rule, executes `wren build` (to compile the new knowledge into the manifest), and runs `wren memory index` (to generate the RAG embeddings). 

*(Note: Because the LLM maintains a conversational history buffer, if you previously asked this question and it hallucinated, you MUST restart the orchestrator by typing `exit` and running it again. Otherwise, the agent will just rely on its cached reasoning instead of fetching the new instructions!)*

Now, when a user asks the ambiguous **Case 1** prompt in a fresh session, the agent seamlessly reads this rule via `get_instructions`, perfectly resolving the ambiguity and executing the exact same correct SQL as **Case 2** without requiring any prompt engineering!

<details>
<summary>💡 Deep Dive: Alternatives to Rules</summary>

**1. Is there a way to do this with examples instead of rules?**
Yes! WrenAI allows you to provide "Golden SQL" examples in `knowledge/sql/`. The agent uses semantic similarity to recall these examples as few-shot prompts. However, for highly ambiguous conflicts (like the word "status"), LLMs often stubbornly ignore examples if they think the user explicitly demanded a specific column. Hardcoded Business Rules are universally more robust.

**2. Is there another way to fix this without writing SQL?**
Absolutely. While `knowledge/sql` is a great quick fix, the best architectural solution is to create a **Cube**:
```yaml
name: refunds_cube
source: returned_orders
dimensions:
  - return_status
measures:
  - name: total_refunded
    expression: sum(refund_amount)
```
If you define this cube, the LLM will skip the raw schema entirely and route the query directly to the cube (exactly like **Case 1: Hitting a Cube**), ensuring 100% deterministic accuracy.

*(Alternatively, simply renaming the ambiguous `status` column in the `orders` model to `order_status` would instantly stop the LLM from confusing it with `return_status`!)*
</details>

**3. Handling Missing Data Gracefully**
> `User ❯ Show me all returned orders and their return reasons.`
*Behavior:* The agent discovers the `returned_orders` model but realizes there is no `return_reason` column. Instead of hallucinating, it explicitly informs the user that reasons are unavailable and asks if they want to query just the return statuses instead.

### Incorporating Mem0 (Long-Term Agentic Memory)

One of the most powerful features of an autonomous agent is the ability to remember organizational context across sessions. This system integrates **Mem0 v3** over **Valkey** (a Redis alternative) as the agent's long-term vector graph memory, utilizing **FastEmbed** to compute embeddings locally without relying on expensive OpenAI APIs.

*(Note: Dynamic query routing between real-time and historical databases based on contextual history can be implemented as an extension of this setup.)*

#### 🧠 Problem: LLM Hallucination on Subjective Business Logic
When an LLM is presented with an ambiguous question, it will often try to "help" by creatively guessing the business logic rather than failing.

For example, if you ask the agent without memory enabled:
> `User ❯ How many high-value orders do we have yesterday?`

**What happens WITHOUT memory?**
Because the concept of "high-value" is not defined anywhere in the WrenAI schema, and LLMs are probabilistic, the agent will handle this ambiguity unpredictably. Rather than safely blocking the query, it will often arbitrarily invent a definition on the fly! For example, it might decide on its own that "high-value" means greater than $1,000:
> `Agent ❯ There were 574 high-value orders (defined as orders with a total amount greater than 500) placed yesterday.`

While this might seem helpful, it is extremely dangerous in an enterprise setting. The agent confidently returned an arbitrary business metric that does not match your internal reporting rules, but remained consistent about its arbitrary choice across multiple questions.

#### 🛡️ Solution: Valkey-Powered Memory Overrides
While permanently adding rules to `knowledge/rules` or creating a new Cube in the WrenAI schema is the most robust and persistent solution for enterprise-wide metrics, we use Mem0 here to demonstrate how an agent can dynamically learn user-specific or session-specific preferences on the fly.

By booting the orchestrator with the memory flag enabled (`python src/agent/orchestrator.py --use-memory`), we inject the `save_user_preference_to_memory` and `search_memory` tools into the agent's prompt.

This allows you to explicitly teach the agent your organization's business rules once:
> `User ❯ Assume that when I say 'high-value orders', I am referring strictly to orders with a total amount greater than $1,000.`

**What happens WITH memory?**
1. **Immediate Storage**: The agent bypasses the semantic schema completely and immediately invokes the memory tool. The rule is permanently saved into the `odctl` Valkey instance.
2. **Contextual Retrieval**: The next time you ask *"How many high-value orders do we have yesterday?"*, the agent queries Mem0 first. It retrieves your exact definition.
3. **Consistent Execution**: The agent applies the proper filter to the `orders` table (`total_amount > 1000`), returning a consistent metric aligned with your rules:
> `Agent ❯ There were 777 high-value orders (orders with a total amount greater than $500) yesterday.`

This memory architecture allows the AI to adapt to your company's unique jargon and business definitions without requiring you to manually update the underlying semantic model for every localized colloquialism.

---

## Testing and Evaluation

To measure the success of the Agentic Orchestrator, we must evaluate its decision-making (Tool Selection) and its safety (Negative Testing). 

### Testing Methodology (LLM-as-a-Judge Prototype)
1. **Cube Routing (Tool Selection):** When a user asks for governed metrics, the agent should invoke `query_cube`.
2. **Execution:** When governed metrics don't exist, the agent falls back to generating modeled SQL.
3. **Graceful Failure (Negative Testing):** We feed the agent impossible queries (e.g., asking for a non-existent `return_reason` column) to verify that the agent gracefully refused to answer rather than inventing fake data.

*Note: The current `evaluations/evaluate_semantics.py` is a prototype response-level LLM judge. It captures the agent's final text response and asks a separate LLM to grade it (PASS/FAIL). For a true production pipeline, this should be migrated to Strands Evals (using `ToolSelectionAccuracyEvaluator` and `TrajectoryEvaluator`) for deterministic SQL-result comparison and trajectory inspection.*

### Test Suite Coverage

The evaluation suite ([`evaluations/golden_test_suite.json`](evaluations/golden_test_suite.json)) is designed to benchmark the AI's agentic reasoning:
- **Cube Discovery:** Tests if the AI correctly routes high-level business questions to governed metrics.
- **Raw Table Navigation:** Tests the AI's ability to execute complex JOINs and aggregations across the underlying semantic models when cubes aren't available.
- **Hallucination Prevention:** Challenges the AI with missing data scenarios to ensure strict adherence to the schema.

### Running Evaluation Harness

The repository includes a fully automated evaluation script (`evaluations/evaluate_semantics.py`) that executes the golden test suite.
For each test case, the script spins up an isolated orchestrator agent, captures its output, and then uses a separate, tool-less **LLM-as-a-judge** to grade the response (PASS/FAIL) against the strict constraints.

```bash
# Run the full 20-case test suite
python evaluations/evaluate_semantics.py

# Optional: Run only a subset of tests for quick smoke-testing
python evaluations/evaluate_semantics.py --limit 3

# Optional: Bypass AWS Bedrock and use the API Key fallback
python evaluations/evaluate_semantics.py --use-api-key
```
Results, including the agent's full response and the judge's reasoning, are automatically saved to `evaluations/evaluation_results.json`.

### Analyzing & Troubleshooting Failures

When running the evaluation suite, you will see some test cases fail. LLMs are probabilistic, and output consistency can vary depending on the chosen model (e.g., `gemini-3.1-flash-lite` vs. `Claude 3.5 Sonnet`). 

Evaluation failures typically group into one of three common categories. Here is how to diagnose and resolve them:

#### 1. Routing Failures (Agent uses `run_sql` instead of `query_cube`)
*   **Symptom:** The agent writes custom logical SQL to calculate a metric (e.g., daily gross revenue or best-selling product) instead of calling `query_cube` with the predefined cubes (`daily_revenue`, `product_performance`).
*   **How to resolve:**
    *   *Enrich MDL Descriptions:* Open the cube YAML definitions and add detailed, keyword-rich descriptions to the measures and dimensions (e.g., explicitly mentioning terms like "gross sales", "revenue", and "units sold" inside the descriptions). This helps the RAG search (`get_context`) match them to natural language questions.
    *   *Seed Golden Queries:* Add direct natural-language-to-cube examples in `knowledge/sql/` to train the semantic search on how to query cubes correctly.

#### 2. SQL Logic & Business Rule Mismatches
*   **Symptom:** The agent executes a valid query, but the logic differs from the evaluation expectations (e.g., using `SUM(quantity)` instead of `COUNT(*)` to count returned items, or applying a custom `status != 'cancelled'` filter when the evaluation expected a simple unfiltered table scan).
*   **How to resolve:**
    *   *Standardize Patterns in `knowledge/sql/`:* Add reference examples in `knowledge/sql/` showing the preferred join paths, filter priorities, and aggregation syntax.
    *   *Refine Rule Scope in `knowledge/rules/`:* Make sure your markdown rules explicitly state whether constraints (like excluding cancelled orders) apply strictly to sales metrics or universally to all query contexts.

#### 3. Silent Aborts & Empty Responses
*   **Symptom:** The agent completes its run but returns a blank response, or stops immediately after the `dry_run` or `dry_plan` validation steps.
*   **How to resolve:**
    *   *Increase Invocation Limits:* If the retrieved schema context is large, the cumulative token count of the multi-turn validation chain can exceed limits. Ensure the `total_tokens` cap in `limits` is set high enough (e.g., `50_000` tokens) to accommodate history and schema definitions.
    *   *Graceful Refusal Prompting:* If the query fails because a requested field (e.g., `return_reason`) does not exist, check the system prompt. Make sure the agent is instructed to output an explicit, human-readable refusal (e.g., *"The return reason is not available in the schema"*) rather than terminating with a blank text response.

---

## Discarding the Environment

To tear down the local analytics infrastructure and completely wipe all container data and Docker volumes, run:

```bash
odctl down --all -v
```

This will stop all active container profiles (Trino, Valkey, Postgres, SeaweedFS) and cleanly delete their associated volumes.
