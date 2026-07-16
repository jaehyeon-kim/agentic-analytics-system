# Production Considerations: Agentic Analytics System

Moving a local, conversational data assistant into a distributed, multi-tenant enterprise environment requires significant architectural hardening. This guide details the production considerations for deploying the Agentic Analytics System securely and reliably.

## Table of Contents
- [0. Current PoC Boundaries vs. Production Targets](#0-current-poc-boundaries-vs-production-targets)
- [1. Production Goals and Assumptions](#1-production-goals-and-assumptions)
- [2. Semantic Authority and Query Improvement](#2-semantic-authority-and-query-improvement)
- [3. Multi-Tenancy and Identity Propagation](#3-multi-tenancy-and-identity-propagation)
- [4. Authorization and Data Isolation](#4-authorization-and-data-isolation)
- [5. Agentic Safety and Query Guardrails](#5-agentic-safety-and-query-guardrails)
- [6. Performance, Caching, and Cost Control](#6-performance-caching-and-cost-control)
- [7. Observability, Evaluation, and User Feedback](#7-observability-evaluation-and-user-feedback)
- [8. Availability and Scaling](#8-availability-and-scaling)
- [9. Deployment, Versioning, and Schema Drift](#9-deployment-versioning-and-schema-drift)
- [10. Secrets, Privacy, and Compliance](#10-secrets-privacy-and-compliance)
- [11. Backup and Disaster Recovery](#11-backup-and-disaster-recovery)
- [12. SLOs and Operational Ownership](#12-slos-and-operational-ownership)
- [Appendix A: Query Promotion](#appendix-a-query-promotion)
- [Appendix B: Query Cost Protection](#appendix-b-query-cost-protection)
- [Appendix C: Failure Modes and Recovery](#appendix-c-failure-modes-and-recovery)
- [Appendix D: Tenant Deployment Patterns](#appendix-d-tenant-deployment-patterns)


## 0. Current PoC Boundaries vs. Production Targets

This repository is currently a **local, single-user proof of concept**. The controls described in this guide are production targets, not implemented features in the current codebase.

| Capability | Current PoC | Production Target |
| :--- | :--- | :--- |
| **Interface** | Interactive local CLI | Authenticated API/UI |
| **Users** | Fixed logical user | Real user and tenant identities |
| **Wren deployment** | Local MCP subprocess | Managed sidecar or service |
| **Semantic project** | Regenerated destructively | Version-controlled immutable artifact |
| **Data ingestion** | Destructive reload | Incremental, idempotent pipeline |
| **Authorization** | Shared local Trino user | RBAC, row filters, masks |
| **Query policy** | Prompt instructions | Enforced SQL policy and engine limits |
| **Mem0** | `user_id="user"` | Tenant/user-scoped memory |
| **Candidate promotion** | Design only | S3 events, offline review, Git PR |
| **Caching** | Not implemented | Tenant- and policy-aware caches |
| **Observability** | Application logs | OpenTelemetry traces and metrics |
| **Evaluation** | Response-level LLM judge | Tool trajectory and result equivalence |
| **Dependencies** | Unpinned requirements | Locked, scanned builds |
| **Availability** | Single local process | Health checks, scaling and failover |

## 1. Production Goals and Assumptions

The primary goal of the production architecture is to provide a reliable, secure, and performant conversational interface over data.

*   **Semantic Correctness:** The agent must reason over governed business concepts rather than inferring logic from raw database schemas.
*   **Security and Isolation:** Tenants must be strictly isolated at the authentication, memory, and physical database levels.
*   **Operational Reliability:** Components must be highly available, independently scalable, and fail gracefully.
*   **Performance and Cost:** Query execution must be bounded, and semantic caching must be leveraged to reduce LLM and data warehouse overhead.

## 2. Semantic Authority and Query Improvement

As the semantic project and approved query corpus grow, WrenAI's memory index becomes important for retrieving targeted schema context and relevant SQL examples without injecting the full project into every prompt.

### Authority Hierarchy

To prevent hallucinations, the system relies on a strict hierarchy of semantic authority:

1.  **MDL (Modeling Definition Language):** The structural and semantic contract.
2.  **`knowledge/rules`:** Authoritative business and query policies (read separately through context instructions).
3.  **`knowledge/sql`:** Reviewed examples of successful natural language to SQL mappings.
4.  **LanceDB:** The derived retrieval index over the MDL and `knowledge/sql`.
5.  **Mem0:** User-specific preferences and conversational context. Mem0 is not organizational truth; Wren's governed definitions must always override it.

Each application replica runs or connects to a Wren MCP instance with a local, read-only LanceDB index.

## 3. Multi-Tenancy and Identity Propagation

The tenancy model dictates how semantic projects and data are isolated. You must choose a model that fits your organization:

*   **Shared semantics, shared tables:** Rows contain a `tenant_id`. Requires a shared Wren project; tenant isolation is enforced strictly in Trino.
*   **Shared semantics, separate schemas/catalogs:** Same logical model, different physical namespace. Requires a shared project template or per-tenant profile/process.
*   **Tenant-specific semantics:** Different models, metrics, rules, or schema. Requires a separate versioned Wren project and LanceDB index per tenant.

### Identity Propagation to Trino

Because Wren resolves connection credentials at server startup, Trino sees the Wren service account, not the original application user. To enforce isolation, you must implement identity propagation:

*   **Option A:** Per-tenant service identity (Tenant A → Wren A → Trino identity `tenant_a_agent`).
*   **Option B:** Controlled impersonation (Authenticated user → trusted gateway/Wren → Trino delegated identity).
*   **Option C:** Shared service identity plus policy context (Wren service identity → Trino/OPA policy using trusted tenant attributes).

*Never* derive `tenant_id` from the natural-language prompt. It must come from an authenticated application context and remain immutable during the request.

## 4. Authorization and Data Isolation

Iceberg is a table format; it does not authenticate users or enforce query-time policies. You must rely on **Trino Access Control** (table privileges, row filters, column blocking, and column masks).

### Recommended Controls

*   **Request Context:** Every request must carry trusted identifiers (`request_id`, `tenant_id`, `user_id`, `roles/groups`, `policy_version`, `session_id`).
*   **Semantic-Project Isolation:** Use immutable artifacts downloaded or baked into the Wren runtime (e.g., `wren-projects/tenant-a/v7/`). Do not mount live S3-backed projects per session.
*   **Mem0 Isolation:** Every Mem0 operation must be strictly scoped by both user and tenant via filters (e.g., `filters={"tenant_id": tenant_id, "user_id": user_id}`).
*   **Candidate Isolation:** Use tenant-scoped S3 prefixes and KMS controls (e.g., `candidates/tenant=<tenant-id>/date=<date>/<uuid>.json`). Do not put raw result rows into candidate events.

## 5. Agentic Safety and Query Guardrails

Treat all inputs—user prompts, recalled SQL, MCP output, and Mem0 memories—as untrusted.

### SQL Policy Gate

Before physical execution, the agent must pass through a strict policy gate:

```text
Agent-generated modeled SQL
    ↓
Wren dry_plan (Semantic expansion & syntax through MDL)
    ↓
Physical SQL policy inspection (Reject multiple statements, mutations, SELECT *, unapproved catalogs)
    ↓
Wren dry_run (Live database validation without returning rows)
    ↓
EXPLAIN (TYPE IO) (Optional physical-input and scan analysis)
    ↓
run_sql (Execution)
```

### Read-Only Enforcement

Do not rely on prompt instructions ("only generate SELECT"). Enforce read-only access in Trino by denying `INSERT`, `UPDATE`, `DELETE`, `MERGE`, DDL, and table procedures. Restrict access to the `system` catalog.

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

## 6. Performance, Caching, and Cost Control

Semantic similarity alone is not sufficient for caching. Two similar questions may differ by tenant, permissions, time range, or policy version.

### Safe Caching Layers

1.  **Context Cache:** `get_context` and instructions (Keyed by project version).
2.  **Planning Cache:** Question → Modeled SQL (Keyed by tenant, user preferences, and semantic version).
3.  **Physical SQL Cache:** Modeled SQL → Compiled SQL (Keyed by Wren and datasource version).
4.  **Result Cache:** Physical SQL → Rows (Highest risk. Key must include: `hash(tenant_id, effective_role, policy_version, wren_project_version, physical_sql, normalized_parameters, timezone, currency, datasource, data_snapshot_bucket)`).

Do not result-cache volatile logic (`current_timestamp`), user-specific PII in shared storage, or rapidly changing data.

### Cost and Noisy-Neighbor Control

Apply quotas at multiple levels using Trino Resource Groups:
*   `hardPhysicalDataScanLimit`: Group-level scan quota over a configured period.
*   `query_max_scan_physical_bytes`: Per-query limit to terminate massive scans.
*   `maxQueued`, `softConcurrencyLimit`, and `hardConcurrencyLimit`.

## 7. Observability, Evaluation, and User Feedback

Do not just trace the agent's "thought process". You must trace the **observable execution trajectory**, including model requests, tool calls, validation steps, query execution, and final response generation.

### Trace Attributes

Every request should record: `request_id`, `tenant_id`, `pseudonymous_user_id`, `orchestrator_version`, `prompt_version`, `Wren project version`, `model/provider`, `tool timings`, `dry_plan outcome`, `dry_run outcome`, `Trino query ID`, `scanned bytes`, `processed rows`, `retry count`, and `stop reason`.

*Never* put raw credentials, unrestricted prompts, raw PII rows, or sensitive memories into traces.

### Evaluation

Use multiple evaluators beyond simple result equivalence: tool-selection correctness, trajectory/order evaluation, policy compliance, scan cost, and regression by tenant.

## 8. Availability and Scaling

Define your process topology (e.g., Wren MCP as a sidecar or standalone service) and implement readiness/liveness checks.

### Degraded-Mode Policy

*   **Mem0 unavailable:** Continue without personal preferences.
*   **LanceDB unavailable:** Use Wren filesystem/plain-schema fallback where possible.
*   **Trino unavailable:** Do not fabricate; return a temporary service error.
*   **Model provider unavailable:** Fail over only to an evaluated, compatible provider.

## 9. Deployment, Versioning, and Schema Drift

Adopt an immutable deployment strategy. The orchestrator code, system prompt, Wren project, `target/mdl.json`, LanceDB index, evaluation suite, and model-routing policy must be versioned and deployed together.

### Prompt and Workflow Versioning

Production requires a single shared prompt builder, explicit prompt versioning, and regression tests whenever the prompt changes. Do not include evaluation-only instructions (like forcing the agent to print exact SQL) in the user-facing production prompt; instead, capture SQL and tool calls through traces.

### Schema Drift Pipeline

```text
Source schema change detected
    ↓
Validate Wren models
    ↓
Rebuild MDL & LanceDB memory
    ↓
Run golden queries (compare outputs and costs)
    ↓
Approve release
```

### Data Pipeline Productionization

The PoC uses destructive table reloads. A production data pipeline must implement incremental and idempotent ingestion, checkpointing, retries, and schema evolution handling. It must support concurrent commits and perform regular Iceberg compaction and snapshot expiration.

### Supply-Chain Controls

Production deployments must use locked dependencies (e.g., a committed `uv.lock`), pinned container images, and undergo regular dependency vulnerability scanning.

## 10. Secrets, Privacy, and Compliance

*   Use a Secrets Manager rather than `.env` files in production.
*   Implement automatic credential rotation.
*   Enforce TLS for all network paths.
*   Restrict outbound egress and ensure no public Trino or Valkey endpoints exist.
*   Implement KMS separation for tenant candidate prefixes.

### Mem0 (Valkey) Privacy

Mem0 v3 over Valkey stores user-specific preferences using semantic, lexical, and entity-linked retrieval. You must define retention periods, opt-out mechanisms, and conflict resolution rules when user preferences contradict organizational Wren policies.

## 11. Backup and Disaster Recovery

Classify your state and test restorations:

*   **Authoritative:** Git Wren project (Back up and replicate).
*   **Durable:** S3 candidate events (Lifecycle-managed).
*   **Persistent User State:** Valkey/Mem0 memory (Back up according to policy).
*   **Derived/Generated:** LanceDB, `target/mdl.json` (Rebuild rather than restore).

## 12. SLOs and Operational Ownership

Define explicit operational targets:
*   Availability targets.
*   p95 response latency & p95 query execution time.
*   Maximum queue time.
*   First-attempt SQL success rate.
*   Maximum stale semantic-project age.
*   Candidate promotion delay.
*   RPO and RTO for memory and semantic metadata.

---

## Appendix A: Query Promotion

To continuously improve the semantic layer without risking live hallucination, use an out-of-band promotion workflow:

1.  **Runtime (Read-Only):** The orchestrator evaluates the SQL. If the result is successful and confirmed by the user, the application backend (or an orchestrator hook) captures the completed interaction and exports a Candidate Event to S3. The LLM should never autonomously decide to promote its own query.
2.  **S3 Candidate Event:** Must include `tenant_id`, `question`, `modeled_sql`, `physical_sql`, `wren_project_version`, `prompt_version`, `tool_path`, and `execution_succeeded`.
3.  **Governance (Offline):** A separate process evaluates the candidate for semantic correctness, security policy, query cost, and duplication.
4.  **Distribution:** Approved candidates are promoted to `knowledge/sql/` in Git via PR, triggering a rebuild of the LanceDB index for the next deployment.

## Appendix B: Query Cost Protection

Engine limits and storage optimizations bound resource consumption and reduce the blast radius, while read-only authorization prevents data mutation. Use Trino's `query_max_scan_physical_bytes` session property to terminate queries that exceed cost thresholds during execution, and configure `hardPhysicalDataScanLimit` in resource groups to queue or reject excessive concurrent analytical workloads.

## Appendix C: Failure Modes and Recovery

Ensure robust handling for tool loops. Use Strands' native invocation limits to prevent infinite retries when the agent fails to formulate valid SQL after a `dry_run` rejection. Log the failure trajectory for offline review.

## Appendix D: Tenant Deployment Patterns

Evaluate the trade-offs of your tenancy model. Shared projects are highly scalable but require complex Trino row-level filtering. Dedicated per-tenant projects offer strict isolation and custom business rules but increase deployment and index-rebuilding overhead.
