# Lab 3: Local MCP Analytics

In this lab, you will connect the AI layer to your data lakehouse using the Model Context Protocol (MCP).

## Objectives
- Write local Python tools using the MCP framework.
- Expose your Trino and ClickHouse databases securely so an AI agent can execute queries against them.

# Lab 4: Agentic Analytics

In this lab, you will bring the AI orchestrator to life.

## Objectives
- Build a local Python CLI using the **Strands** framework.
- Connect Strands to a local **Ollama** LLM (e.g., `qwen2.5-coder:7b`).
- Enable the agent to autonomously reason about user questions, select the right database tools, and return data-driven answers.


## Incorporating Mem0 & Routing

This module also integrates Mem0 over Qdrant for context-aware multi-hop reasoning, using Strands to dynamically route queries between real-time (ClickHouse) and historical (Iceberg) databases.
