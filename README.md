# Agentic Analytics System

A local, open-source stack for building conversational data agents and semantic reasoning workflows over an Iceberg Lakehouse.

## Motivation and Benefits

This architecture updates and extends the concepts from the [AWS Agentic Analytics Ready Lakehouse Workshop](https://catalog.workshops.aws/agentic-analytics-lakehouse/en-US), replacing managed cloud services with robust open-source alternatives.

Modern data ecosystems require systems that can autonomously reason about data, translate natural language into accurate queries, and maintain conversational context. However, tightly coupled, managed cloud AI services often struggle with complex business logic and create friction when integrating external databases.

This repository provides an open-source stack for building an Agentic Data System.

**Benefits:**
* **Accuracy:** Improves semantic reasoning reliability by constraining query generation with explicit semantic models, relationships, business definitions and query validation.
* **Modularity:** Compute, storage, and AI orchestration are decoupled, preventing vendor lock-in.
* **Contextual Awareness:** Mem0 v3 provides built-in entity-linked graph memory over Valkey (Redis-compatible), improving retrieval of related user preferences, people, events and conversational facts without requiring a separate graph database.

## Evaluating Semantic Layer AI Solutions

When building an autonomous data assistant, the biggest challenge is translating ambiguous natural language into deterministic, accurate SQL. There are several popular tools in the ecosystem attempting to solve this:

*   **[WrenAI](https://www.getwren.ai/)**: A robust semantic engine that combines an AI semantic reasoning interface with a deterministic Semantic Layer (MDL). It bridges the gap between RAG (for query recall) and strict data governance (Cubes, Models, and Relationships). 
*   **[Vanna AI](https://vanna.ai/)**: An open-source, Python-based RAG approach for conversational data querying. It relies heavily on training a vector database with your schema, documentation, and historical queries. While highly flexible and easy to deploy as a Python library, it lacks a strict deterministic semantic modeling layer (like Cubes or Metrics). This means it relies entirely on the LLM's reasoning capabilities, which can lead to hallucinations when calculating complex, multi-join metrics that aren't explicitly in the training set.
*   **[Nao](https://getnao.io/)**: An AI-native data assistant focused heavily on business users. It often integrates into communication platforms (like Slack or Teams) to answer data questions out-of-the-box. It leans more towards a managed SaaS experience, prioritizing user experience over deep programmatic integration and open-source infrastructure control.

**Why WrenAI is the right choice for this stack:**
1.  **Governed Semantic Layer**: Instead of guessing SQL against raw tables, WrenAI relies on explicit, deterministic definitions. If you define `net_revenue` as `gross_sales - refunds` inside a Cube, the LLM doesn't have to guess the calculation; it simply routes to the Cube.
2.  **RAG + Semantic Search**: WrenAI natively integrates LanceDB. By feeding it Golden SQL examples, it embeds them into memory. When a user asks a similar question, WrenAI recalls the exact query structure, ensuring few-shot learning directly inside the semantic engine.
3.  **Native MCP Server**: WrenAI ships with a native Model Context Protocol (MCP) server. This makes it incredibly easy for our Strands orchestrator agent to introspect the schema, discover cubes, and execute queries using standardized tools (`recall_queries`, `query_cube`, `run_sql`) without requiring complex custom integrations.

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
| **Agent Memory** | Mem0 v3 over Valkey | Long-term conversational memory with entity-linked graph retrieval. Stores user preferences (e.g., "revenue means net revenue") across sessions. |
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
[Athena / Trino / Iceberg]
      │
      ▼
[Structured Data]
```

---

## Prerequisites

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and [Ollama](https://ollama.com/), then create and activate a local virtual environment using Python 3.12, and install the required dependencies (which includes the `odctl` orchestrator). Python 3.12 is explicitly required because Mem0 v3's NLP and entity-linking support does not yet provide wheels for Python 3.13+.

```bash
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r src/requirements.txt
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

WrenAI provides a **governed semantic compiler and execution boundary**. It does not interpret natural language or handle ambiguity. Instead, it:
1. Defines business logic as code using the [Modeling Definition Language](https://docs.getwren.ai/oss/concepts/what_is_mdl) (MDL schema version 5) - models, relationships, cubes, and metrics.
2. Plans physical SQL deterministically from logical semantic queries.
3. Validates and dry-runs queries against the backend before execution.

**Layer 2 - Autonomous Agent: `Strands SDK`**

The [Strands SDK](https://github.com/strands-agents/sdk-python) (by AWS) provides the autonomous reasoning layer. It:
1. Interprets natural language and maps ambiguous terms (e.g., "revenue") to the correct WrenAI semantic objects (cubes, models, views).
2. Orchestrates multi-step tool calls to WrenAI's MCP server - listing cubes, describing schemas, validating SQL via `dry_plan`, and executing queries.
3. Maintains conversational context via Mem0 to remember user preferences across sessions.

By combining these layers, the LLM never sees raw database tables. It only interacts with WrenAI's governed semantic API, which constrains its output to valid, deterministic SQL.

### 🛡️ Production Architecture

When migrating this local agentic semantic layer to a distributed, multi-tenant production environment, several safeguards and architectural changes must be made (e.g., S3-backed LanceDB, Kafka writing queues, semantic caching, and LLM guardrails). 

For a complete breakdown of how to scale this system securely, see our [Production Architecture & Considerations Guide](PRODUCTION_CONSIDERATIONS.md).

### 💾 Production Persistence

The entire `.wren_project` directory is intentionally disposable.

The local `.wren/memory` directory is a derived LanceDB index. It can optionally be mounted on a persistent volume to avoid rebuilding it after ordinary container restarts.

Approved semantic reasoning examples (Golden SQL) are represented by `knowledge/sql/*.md`. For this PoC, those files are generated during project initialization and are also disposable.

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

WrenAI doesn't read the scattered YAML files at runtime. Instead, this command natively compiles all the YAML definitions, relationships, and business rules into a single, highly optimized `mdl.json` manifest. The Wren execution engine uses this manifest to plan physical SQL queries deterministically.

```bash
python src/semantic_engine/manage_semantics.py build
```

#### Memory Indexing (index)

If you have hundreds of models and approved query patterns, you cannot fit the entire schema and business context into an LLM's prompt. Wren solves this by building a local vector database using **LanceDB** to act as a **retrieval accelerator**. This command reads the table descriptions from your MDL files, as well as the rules and approved SQL examples from the `knowledge/` directory, and embeds them.

```bash
python src/semantic_engine/manage_semantics.py index

# Output:
# INFO: 🧠 Indexing Semantic Memory (Vectorizing to local .wren/memory)...
# Indexed 64 schema items, 22 seed queries.
# Indexed 1 pair(s) from knowledge/sql/.
# INFO: 🎉 Semantic memory successfully indexed locally.
```

**How Memory is Structured:**
When you run the index command, WrenAI breaks your project into three distinct vectors:
1. **Schema Items (64 items):** This is the structural index. Wren parses the MDL files and embeds every Model, View, Cube, and their descriptive metadata. This allows the LLM to search for relevant tables and columns by meaning rather than exact name matching.
2. **Seed Queries (22 queries):** This is an automated baseline index. When Wren compiles relationships and cubes (like our `net_revenue` measure), it automatically synthesizes sample questions and SQL patterns. This jumpstarts the memory, giving the agent a foundational understanding of how your tables join without you having to write a manual example for everything.
3. **Knowledge Pairs (1 pair):** This is the manual query recall index. It represents the custom, explicitly approved Natural-Language-to-SQL example we placed in the `knowledge/sql/` directory.

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

In this section, you will bring the AI orchestrator to life by connecting it to your data lakehouse using the Model Context Protocol (MCP).

### Objectives

- Leverage WrenAI's native MCP server (`wren serve mcp`) to securely expose the semantic layer to the AI agent, removing the need for manual database connection boilerplate.
- Build a Python CLI agent using the **Strands SDK** - AWS's open-source agentic AI framework that natively supports tool calling via the Model Context Protocol (MCP).
- Connect Strands to **Amazon Bedrock** (default) or any LiteLLM-compatible model (Gemini, OpenAI, Ollama).
- The Strands agent autonomously spawns WrenAI's MCP server (`wren serve mcp`) as a subprocess, discovers available semantic tools, and orchestrates multi-step query planning - from schema exploration to SQL validation and execution - without hardcoded logic.

### 🏗️ Semantic Reasoning Architecture & Validation

Based on modern LLM architecture patterns, building an effective semantic reasoning system requires addressing **schema scale** and **schema drift**. To ensure robust querying, we employ a hybrid approach powered by WrenAI's native MCP integration:

1. **Table Discovery (RAG)**: RAG is used to retrieve schema items relevant to the query. WrenAI uses its embedded **LanceDB** vector store as a *local, rebuildable index* (`.wren/memory/`) to identify the exact tables relevant to the user's intent. For this PoC, the semantic project is generated dynamically from the models, relationships, and knowledge definitions inside `manage_semantics.py`.
2. **Schema & Syntax Validation (Native MCP Tools)**: The Strands agent utilizes WrenAI's native MCP endpoints to cross-reference the MDL and validate generated SQL using the `dry_plan` tool. This tests the logic and syntax against live metadata without executing a potentially expensive physical query, acting as a structural safeguard against hallucinations.

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
> `Agent ❯ There were 574 high-value orders (defined as orders with a total amount greater than 1,000) placed yesterday.`

While this might seem helpful, it is extremely dangerous in an enterprise setting. The agent confidently returned an arbitrary business metric that does not match your internal reporting rules, but remained consistent about its arbitrary choice across multiple questions.

#### 🛡️ Solution: Valkey-Powered Memory Overrides
While permanently adding rules to `knowledge/rules` or creating a new Cube in the WrenAI schema is the most robust and persistent solution for enterprise-wide metrics, we use Mem0 here to demonstrate how an agent can dynamically learn user-specific or session-specific preferences on the fly.

By booting the orchestrator with the memory flag enabled (`python src/agent/orchestrator.py --use-memory`), we inject the `save_user_preference_to_memory` and `search_memory` tools into the agent's prompt.

This allows you to explicitly teach the agent your organization's business rules once:
> `User ❯ Assume that when I say 'high-value orders', I am referring strictly to orders with a total amount greater than $500.`

**What happens WITH memory?**
1. **Immediate Storage**: The agent bypasses the semantic schema completely and immediately invokes the memory tool. The rule is permanently saved into the `odctl` Valkey instance.
2. **Contextual Retrieval**: The next time you ask *"How many high-value orders do we have yesterday?"*, the agent queries Mem0 first. It retrieves your exact definition.
3. **Deterministic Execution**: The agent automatically applies the proper filter to the `orders` table (`total_amount > 500`), returning the correct, non-hallucinated metric:
> `Agent ❯ There were 777 high-value orders (orders with a total amount greater than $500) yesterday.`

This memory architecture ensures the AI adapts to your company's unique jargon and business definitions without requiring you to manually update the underlying semantic model for every localized colloquialism.

---

## Testing and Evaluation

To measure the success of the Agentic Orchestrator, we evaluate it across three distinct dimensions. Because the system relies on an autonomous agent rather than a simple rule-based translation script, we must evaluate its decision-making (Tool Selection), its accuracy (Execution), and its safety (Negative Testing).

### Testing Methodology
1. **Cube Routing (Tool Selection):** When a user asks for governed metrics (e.g., "What was our net revenue?"), the agent must invoke the `query_cube` API. We evaluate this by verifying the agent selected the correct tool and passed the correct structured payload, avoiding raw SQL generation entirely.
2. **Execution Accuracy (EX):** When governed metrics don't exist, the agent falls back to generating SQL against the raw semantic models. We evaluate this by executing both the agent's generated SQL and our Ground Truth SQL against Trino. A perfect match of the resulting data payloads counts as a success.
3. **Graceful Failure (Negative Testing):** The most dangerous thing an agent can do is hallucinate. We feed the agent impossible queries (e.g., asking for a non-existent `return_reason` column) and use an LLM-as-a-judge to verify that the agent gracefully refused to answer rather than hallucinating fake data.

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
