# Production Considerations: Agentic Analytics System

Moving a local, conversational data assistant into a distributed, multi-tenant enterprise environment requires significant architectural hardening. This guide details the production considerations for deploying the Agentic Analytics System securely and reliably.

## Table of Contents

* [0. Current PoC Boundaries vs. Production Targets](#0-current-poc-boundaries-vs-production-targets)
* [1. Production Goals and Assumptions](#1-production-goals-and-assumptions)
* [2. Semantic Authority and Query Improvement](#2-semantic-authority-and-query-improvement)
* [3. Multi-Tenancy and Identity Propagation](#3-multi-tenancy-and-identity-propagation)
* [4. Authorization and Data Isolation](#4-authorization-and-data-isolation)
* [5. Agentic Safety and Query Guardrails](#5-agentic-safety-and-query-guardrails)
* [6. Performance, Caching, and Cost Control](#6-performance-caching-and-cost-control)
* [7. Observability, Evaluation, and User Feedback](#7-observability-evaluation-and-user-feedback)
* [8. Availability and Scaling](#8-availability-and-scaling)
* [9. Deployment, Versioning, and Schema Drift](#9-deployment-versioning-and-schema-drift)
* [10. Secrets, Privacy, and Compliance](#10-secrets-privacy-and-compliance)
* [11. Backup and Disaster Recovery](#11-backup-and-disaster-recovery)
* [12. SLOs and Operational Ownership](#12-slos-and-operational-ownership)
* [Appendix A: Query Promotion](#appendix-a-query-promotion)
* [Appendix B: Query Cost Protection](#appendix-b-query-cost-protection)
* [Appendix C: Failure Modes and Recovery](#appendix-c-failure-modes-and-recovery)
* [Appendix D: Tenant Deployment Patterns](#appendix-d-tenant-deployment-patterns)

## 0. Current PoC Boundaries vs. Production Targets

This repository is currently a **local, single-user proof of concept**. The controls described in this guide are production targets, not implemented features in the current codebase.

| Capability              | Current PoC                             | Production Target                                                       |
| :---------------------- | :-------------------------------------- | :---------------------------------------------------------------------- |
| **Interface**           | Interactive local CLI                   | Authenticated API/UI                                                    |
| **Users**               | Fixed logical user                      | Real user and tenant identities                                         |
| **Wren deployment** | Local MCP subprocess | Managed sidecar or standalone service |
| **Execution boundary** | Wren tools execute queries directly | Wren generates SQL only; a controlled SQL executor performs execution |
| **Semantic project**    | Regenerated destructively               | Version-controlled immutable artifact                                   |
| **Data ingestion**      | Destructive reload                      | Incremental, idempotent pipeline                                        |
| **Authorization**       | Shared local user                 | RBAC, row filters, masks, and tenant-aware identities                   |
| **Query policy**        | Prompt instructions                     | Enforced SQL policy, authorization, and engine limits                   |
| **Mem0**                | `user_id="user"`                        | Tenant/user-scoped memory                                               |
| **Candidate promotion** | Design only                             | S3 events, offline review, Git PR                                       |
| **Caching**             | Not implemented                         | Tenant- and policy-aware caches                                         |
| **Observability**       | Application logs                        | OpenTelemetry traces and metrics                                        |
| **Evaluation**          | Response-level LLM judge                | Tool trajectory, policy compliance, and result equivalence              |
| **Dependencies**        | Unpinned requirements                   | Locked, scanned builds                                                  |
| **Availability**        | Single local process                    | Health checks, scaling, and failover                                    |

## 1. Production Goals and Assumptions

The primary goal of the production architecture is to provide a reliable, secure, and performant conversational interface over data.

* **Semantic Correctness:** The agent must reason over governed business concepts rather than inferring logic from raw database schemas.
* **Controlled Execution:** Semantic SQL generation must remain separate from authorization, validation, and physical query execution.
* **Security and Isolation:** Tenants must be strictly isolated at the authentication, memory, authorization, and physical database levels.
* **Operational Reliability:** Components must be highly available, independently scalable, and fail gracefully.
* **Performance and Cost:** Query execution must be bounded, and semantic caching must reduce LLM and data warehouse overhead.

## 2. Semantic Authority and Query Improvement

As the semantic project and approved query corpus grow, WrenAI's memory index becomes important for retrieving targeted schema context and relevant SQL examples without injecting the full project into every prompt.

### Authority Hierarchy

The system relies on a strict hierarchy of semantic authority:

1. **MDL:** The structural and semantic contract.
2. **`knowledge/rules`:** Authoritative business and query policies, read separately through context instructions.
3. **`knowledge/sql`:** Reviewed examples of successful natural-language-to-SQL mappings.
4. **LanceDB:** The derived retrieval index over the MDL and `knowledge/sql`.
5. **Mem0:** User-specific preferences and conversational context.

Mem0 is not organizational truth. WrenAI's governed definitions must always override user-specific memory.

Each application replica runs or connects to a Wren MCP instance with a local, read-only LanceDB index.

### Controlled SQL Planning and Execution

In production, WrenAI acts as a semantic planner and must not execute user queries directly.

WrenAI supports two query-planning paths:

* **Structured metric queries:** A controlled wrapper invokes `query_cube` with `sql_only=true` to generate physical SQL from governed cube measures, dimensions, filters, and relationships.
* **Ad hoc logical queries:** The orchestrator invokes `dry_plan` to compile SQL written against MDL models, views, or cubes into the target database dialect.

The raw `run_sql` tool must not be available to the production agent. The raw `query_cube` tool should also not be exposed directly because execution is enabled by default. Instead, Strands should expose a restricted wrapper that always forces `sql_only=true`.

```text
Authenticated request
    ↓
Strands resolves user and tenant identity
    ↓
Agent selects a cube query or logical modeled SQL
    ↓
WrenAI generates physical SQL without executing it
    ↓
Authorization, isolation, SQL policy, and cost checks
    ↓
Controlled Trino executor
    ↓
Filtered results
```

This boundary assigns separate responsibilities:

* **WrenAI:** Business semantics, approved relationships, governed metrics, and physical SQL generation.
* **Strands:** Identity context, workflow orchestration, policy coordination, and tool selection.
* **Authorization layer:** Tenant access, roles, row filters, column masks, and catalog permissions.
* **Controlled Trino executor:** Validation, cost checks, execution, cancellation, and result handling.

This design allows enterprise security controls to evolve independently from the semantic layer.

## 3. Multi-Tenancy and Identity Propagation

The tenancy model determines how semantic projects, user context, policies, and physical data are isolated.

* **Shared semantics, shared tables:** Rows contain a `tenant_id`. Tenant isolation must be enforced through Trino row filters or another trusted authorization layer.
* **Shared semantics, separate schemas or catalogs:** Tenants use the same logical model but different physical namespaces. The executor selects an authorized catalog or schema from trusted request context.
* **Tenant-specific semantics:** Different models, metrics, rules, or schemas require a separate versioned Wren project and LanceDB index per tenant.

### Identity Propagation to Trino

WrenAI does not need to receive or propagate the end-user database identity because it does not execute the physical query.

The controlled executor must derive its authorization context from authenticated application state:

```text
Authenticated user
    ↓
Trusted tenant and role context
    ↓
Strands policy workflow
    ↓
Controlled Trino executor
    ↓
Trino identity, session properties, and access-control rules
```

Possible execution identity models include:

* **Per-tenant service identity:** Tenant A uses a Trino identity such as `tenant_a_agent`.
* **Controlled impersonation:** The trusted executor submits the query using a delegated end-user or service identity.
* **Shared executor identity with policy context:** A shared service account supplies trusted tenant and role attributes to Trino or an external policy engine.

Never derive `tenant_id`, roles, catalogs, schemas, or authorization filters from the natural-language prompt. They must come from authenticated application context and remain immutable throughout the request.

## 4. Authorization and Data Isolation

Iceberg is a table format. It does not authenticate users or enforce query-time policies. Authorization must be enforced through Trino access control, including table privileges, row filters, column blocking, and column masks.

### Recommended Controls

* **Request Context:** Every request must carry trusted identifiers such as `request_id`, `tenant_id`, `user_id`, `roles`, `groups`, `policy_version`, and `session_id`.
* **Executor Isolation:** Only the controlled executor may hold Trino execution credentials. WrenAI and the LLM must not have direct access to them.
* **Semantic-Project Isolation:** Use immutable artifacts downloaded or baked into the Wren runtime, such as `wren-projects/tenant-a/v7/`. Do not mount live S3-backed projects per session.
* **Catalog and Schema Allow-Lists:** Resolve permitted catalogs and schemas from trusted policy context before execution.
* **Row and Column Controls:** Enforce tenant filters, column masks, and PII restrictions in Trino rather than relying on SQL generated by the agent.
* **Mem0 Isolation:** Scope every Mem0 operation by both user and tenant, for example `filters={"tenant_id": tenant_id, "user_id": user_id}`.
* **Candidate Isolation:** Use tenant-scoped S3 prefixes and KMS controls, such as `candidates/tenant=<tenant-id>/date=<date>/<uuid>.json`.
* **Result Isolation:** Do not share query results or result caches across tenants unless the complete authorization context is part of the cache key.

The agent may propose a tenant filter as part of normal query logic, but that filter must never be treated as the authorization mechanism.

## 5. Agentic Safety and Query Guardrails

Treat all inputs as untrusted, including user prompts, recalled SQL, MCP output, retrieved documents, and Mem0 memories.

### Restricted Production Toolset

The production agent must not receive unrestricted Wren execution tools.

Expose only controlled tools such as:

* `get_context`
* schema and knowledge retrieval
* a wrapped cube-planning tool that forces `sql_only=true`
* `dry_plan`
* a separate policy-controlled query executor

Do not expose:

* `run_sql`
* raw `query_cube` with caller-controlled `sql_only`
* arbitrary database credentials
* unrestricted direct Trino clients

Prompt instructions alone are not an adequate control because the model can select incorrect parameters or tools.

### SQL Policy Gate

Every generated query must pass through the orchestrator before execution:

```text
Agent selects a cube query or logical modeled SQL
    ↓
WrenAI query_cube(sql_only=true) or dry_plan
    ↓
Physical SQL parsing and policy inspection
    ↓
Tenant-aware authorization and data-isolation checks
    ↓
EXPLAIN (TYPE IO) and cost validation
    ↓
Controlled Trino executor
    ↓
Bounded and filtered results
```

The SQL policy gate should reject or constrain:

* multiple statements;
* mutations and DDL;
* unapproved catalogs or schemas;
* access to system tables;
* unrestricted `SELECT *`;
* queries without required time or tenant constraints;
* unsafe functions;
* excessive joins or subqueries;
* unbounded result sets;
* scans above configured cost limits.

### Read-Only Enforcement

Do not rely on prompt instructions such as "only generate SELECT."

Enforce read-only access in Trino by denying:

* `INSERT`
* `UPDATE`
* `DELETE`
* `MERGE`
* DDL
* table procedures
* writes through connectors
* unauthorized access to the `system` catalog

The executor identity should have only the minimum privileges required for approved analytical queries.

### Bounding the Strands Loop

Replace vague retry loops with explicit per-invocation limits using the Strands API:

```python
result = await agent.invoke_async(
    question,
    limits={
        "turns": 6,
        "output_tokens": 2_000,
        "total_tokens": 12_000,
    },
)
```

A rejected SQL plan should return a structured policy error to the orchestrator. The agent may retry only within the configured turn and cost limits.

## 6. Performance, Caching, and Cost Control

Semantic similarity alone is not sufficient for caching. Two similar questions may differ by tenant, permissions, time range, policy version, or semantic-project version.

### Safe Caching Layers

1. **Context Cache:** `get_context` and instructions, keyed by Wren project version.
2. **Planning Cache:** Question to modeled query, keyed by tenant, user preferences, prompt version, and semantic version.
3. **Physical SQL Cache:** Modeled query to compiled SQL, keyed by Wren version, project version, and datasource dialect.
4. **Authorization Decision Cache:** Policy decision keyed by user, tenant, effective role, policy version, and normalized physical SQL.
5. **Result Cache:** Physical SQL to rows. This is the highest-risk cache.

A result-cache key must include:

```text
hash(
    tenant_id,
    effective_role,
    policy_version,
    wren_project_version,
    physical_sql,
    normalized_parameters,
    timezone,
    currency,
    datasource,
    data_snapshot_bucket
)
```

Do not result-cache:

* volatile logic such as `current_timestamp`;
* user-specific PII in shared storage;
* rapidly changing data;
* results produced under an authorization context that cannot be reproduced;
* queries whose row-filter policy is not part of the cache key.

### Cost and Noisy-Neighbor Control

Apply quotas at multiple levels using Trino Resource Groups:

* `hardPhysicalDataScanLimit`: Group-level scan quota over a configured period.
* `query_max_scan_physical_bytes`: Per-query limit for terminating excessive scans.
* `maxQueued`: Maximum queued queries.
* `softConcurrencyLimit`: Preferred concurrency limit.
* `hardConcurrencyLimit`: Maximum concurrent queries.

The controlled executor should also apply:

* statement timeouts;
* maximum returned rows;
* maximum result size;
* cancellation support;
* per-tenant concurrency limits;
* per-user or per-tenant cost budgets.

## 7. Observability, Evaluation, and User Feedback

Do not trace the model's private reasoning. Trace the observable execution trajectory, including model requests, tool calls, planning steps, policy decisions, validation, query execution, and final response generation.

### Trace Attributes

Every request should record:

* `request_id`
* `tenant_id`
* `pseudonymous_user_id`
* `effective_role`
* `orchestrator_version`
* `prompt_version`
* `wren_project_version`
* `policy_version`
* `model_provider`
* `model_id`
* planning path, such as `query_cube_sql_only` or `dry_plan`
* modeled query hash
* physical SQL hash
* policy decision
* authorization decision
* `EXPLAIN` outcome
* Trino query ID
* scanned bytes
* processed rows
* returned rows
* tool timings
* retry count
* stop reason

Never put raw credentials, unrestricted prompts, raw PII rows, sensitive memories, or complete sensitive SQL literals into traces.

### Evaluation

Use multiple evaluators beyond result equivalence:

* semantic model selection;
* cube and measure selection;
* tool-selection correctness;
* planner-to-executor trajectory;
* authorization compliance;
* tenant-isolation compliance;
* SQL policy compliance;
* scan cost;
* result correctness;
* regression by tenant;
* refusal correctness for unauthorized requests.

Production evaluation should verify that the agent never bypasses the controlled executor or invokes an unrestricted execution tool.

## 8. Availability and Scaling

Define the process topology and implement readiness and liveness checks for each component.

A production deployment may include:

```text
API or UI
    ↓
Strands orchestrator
    ├── Wren semantic-planning service
    ├── Mem0
    ├── policy service
    └── controlled Trino executor
```

The Wren service should not require physical query-execution credentials when operating only as a planner.

The controlled executor should scale separately from the semantic-planning service because query execution has different CPU, memory, concurrency, and security characteristics.

### Degraded-Mode Policy

* **Mem0 unavailable:** Continue without personal preferences.
* **LanceDB unavailable:** Use Wren filesystem or plain-schema fallback where possible.
* **Wren unavailable:** Do not generate ungoverned SQL. Return a temporary semantic-planning error.
* **Policy service unavailable:** Fail closed. Do not execute the query.
* **Trino unavailable:** Do not fabricate results. Return a temporary query-service error.
* **Model provider unavailable:** Fail over only to an evaluated and compatible provider.
* **Tracing unavailable:** Follow the defined compliance policy. Security-relevant deployments may need to fail closed.

## 9. Deployment, Versioning, and Schema Drift

Adopt an immutable deployment strategy.

The following artifacts must be versioned and deployed together:

* orchestrator code;
* system prompt;
* tool registry;
* Wren project;
* `target/mdl.json`;
* LanceDB index;
* policy definitions;
* executor configuration;
* evaluation suite;
* model-routing policy.

### Prompt and Workflow Versioning

Production requires:

* one shared prompt builder;
* explicit prompt versioning;
* explicit tool-registry versioning;
* explicit policy versioning;
* regression tests whenever prompts, tools, policies, or semantic models change.

Do not include evaluation-only instructions, such as forcing the agent to print exact SQL, in the user-facing production prompt. Capture modeled SQL, physical SQL, policy decisions, and tool calls through traces.

The production tool registry must be tested to confirm that `run_sql` and unrestricted `query_cube` are not exposed.

### Schema Drift Pipeline

```text
Source schema change detected
    ↓
Validate Wren models
    ↓
Rebuild MDL and LanceDB memory
    ↓
Run golden queries
    ↓
Validate generated physical SQL
    ↓
Run policy and authorization regression tests
    ↓
Compare outputs and costs
    ↓
Approve release
```

### Data Pipeline Productionization

The PoC uses destructive table reloads. A production data pipeline must implement:

* incremental and idempotent ingestion;
* checkpointing;
* retries;
* schema evolution;
* concurrent commit handling;
* Iceberg compaction;
* snapshot expiration;
* data-quality validation.

### Supply-Chain Controls

Production deployments must use:

* locked dependencies, such as a committed `uv.lock`;
* pinned container images;
* software-bill-of-material generation;
* dependency vulnerability scanning;
* signed build artifacts where required;
* restricted deployment identities.

## 10. Secrets, Privacy, and Compliance

* Use a secrets manager rather than `.env` files in production.
* Implement automatic credential rotation.
* Enforce TLS for all network paths.
* Restrict outbound egress.
* Ensure no public Trino or Valkey endpoints exist.
* Store Trino credentials only in the controlled executor.
* Do not provide execution credentials to WrenAI or the LLM runtime.
* Implement KMS separation for tenant candidate prefixes.
* Minimize sensitive SQL, prompts, and result data in logs and traces.

### Mem0 and Valkey Privacy

Mem0 over Valkey stores user-specific preferences using semantic, lexical, and entity-linked retrieval.

Define:

* retention periods;
* deletion and opt-out mechanisms;
* tenant and user filters;
* conflict-resolution rules;
* permitted memory categories;
* controls for sensitive personal information.

User preferences must never override organizational Wren policies, authorization rules, or Trino access controls.

## 11. Backup and Disaster Recovery

Classify system state and test restoration procedures.

* **Authoritative:** Git Wren project, policy definitions, and executor configuration. Back up and replicate.
* **Durable:** S3 candidate events. Apply lifecycle and replication policies.
* **Persistent User State:** Valkey and Mem0 memory. Back up according to privacy and retention requirements.
* **Derived or Generated:** LanceDB and `target/mdl.json`. Rebuild rather than restore.
* **Ephemeral:** Query results and temporary execution state. Do not treat as authoritative.

Disaster-recovery testing should confirm that a restored environment preserves:

* the expected semantic-project version;
* the expected policy version;
* the restricted production tool registry;
* tenant-isolation rules;
* executor permissions;
* audit continuity.

## 12. SLOs and Operational Ownership

Define explicit operational targets:

* availability;
* p95 response latency;
* p95 semantic-planning latency;
* p95 query execution time;
* maximum queue time;
* first-attempt SQL planning success rate;
* policy rejection rate;
* authorization failure rate;
* maximum scanned bytes per query;
* maximum stale semantic-project age;
* candidate-promotion delay;
* RPO and RTO for memory and semantic metadata.

Assign ownership for:

* Wren semantic models;
* business definitions;
* Strands orchestration;
* SQL policy;
* Trino authorization;
* executor operations;
* incident response;
* evaluation datasets;
* tenant onboarding.

---

## Appendix A: Query Promotion

To continuously improve the semantic layer without risking live hallucination, use an out-of-band promotion workflow:

1. **Runtime:** The orchestrator records the modeled query, generated physical SQL, policy result, execution outcome, and user feedback. The LLM must never autonomously promote its own query.
2. **S3 Candidate Event:** Include `tenant_id`, `question`, `modeled_sql`, `physical_sql`, `wren_project_version`, `prompt_version`, `policy_version`, `tool_path`, and `execution_succeeded`.
3. **Governance:** A separate process evaluates semantic correctness, security policy, tenant isolation, query cost, and duplication.
4. **Distribution:** Approved candidates are promoted to `knowledge/sql/` in Git through a pull request.
5. **Rebuild:** The deployment pipeline rebuilds the MDL and LanceDB index and runs regression tests before release.

Do not include raw result rows or unrestricted PII in candidate events.

## Appendix B: Query Cost Protection

The controlled executor must apply cost protection before and during physical execution.

Before execution:

1. Parse and normalize the generated SQL.
2. Confirm approved catalogs and schemas.
3. Apply authorization checks.
4. Run `EXPLAIN (TYPE IO)` where supported.
5. Estimate scan cost and reject queries over configured limits.
6. Apply tenant-specific resource-group and session settings.

During execution:

* enforce `query_max_scan_physical_bytes`;
* enforce statement timeouts;
* enforce result-size limits;
* support cancellation;
* record Trino query IDs;
* apply resource-group concurrency controls.

Engine limits reduce the blast radius, while read-only authorization prevents data mutation.

## Appendix C: Failure Modes and Recovery

Ensure robust handling for planner, policy, and executor failures.

* **Wren planning failure:** Return the structured error to Strands and allow a bounded retry.
* **Policy rejection:** Explain the allowed correction without weakening the policy.
* **Authorization rejection:** Do not retry with broader permissions or infer a different tenant.
* **Cost rejection:** Ask the agent to narrow the time range, dimensions, or requested detail.
* **Executor timeout:** Cancel the Trino query and return a controlled failure.
* **Tool loop:** Stop after the configured Strands invocation limits.
* **Partial result:** Do not present incomplete data as a complete answer.
* **Service outage:** Follow the degraded-mode policy and never fabricate results.

Log the observable failure trajectory for offline review.

## Appendix D: Tenant Deployment Patterns

Evaluate the trade-offs of the selected tenancy model.

### Shared Project and Shared Tables

* Lowest semantic-model maintenance overhead.
* Requires strong Trino row filters and policy enforcement.
* Requires tenant-aware caching and result isolation.
* Appropriate only when the authorization layer is mature.

### Shared Project and Separate Schemas

* Reuses the logical semantic model.
* Provides stronger physical separation.
* Requires trusted schema resolution in the executor.
* May require per-tenant connection or session configuration.

### Dedicated Tenant Projects

* Provides strict semantic and configuration isolation.
* Supports tenant-specific metrics, rules, and models.
* Increases deployment, testing, and index-rebuilding overhead.
* May be appropriate for regulated or highly customized tenants.

In every model, WrenAI remains the semantic planner and the controlled executor remains the only component permitted to submit physical SQL to Trino.
