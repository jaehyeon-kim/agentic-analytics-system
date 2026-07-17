import os
import sys
import asyncio
import argparse
import logging
from dotenv import load_dotenv

from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient

# Configure logger exclusively for stderr to avoid corrupting MCP's stdout JSON-RPC pipe
logger = logging.getLogger("orchestrator")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)


def build_model(use_api_key: bool):
    """Build the LLM model based on the selected backend."""
    if use_api_key:
        from strands.models.litellm import LiteLLMModel

        model_id = os.environ.get("AGENT_MODEL", "")
        if not model_id:
            raise EnvironmentError(
                "AGENT_MODEL is not set. "
                "Set it in your .env file (e.g. AGENT_MODEL=gemini/gemini-2.5-flash)."
            )
        logger.info(f"🚀 Initializing Strands Orchestrator with LiteLLM Model: {model_id}")
        return LiteLLMModel(model_id=model_id)
    else:
        from strands.models.bedrock import BedrockModel

        model_id = os.environ.get("BEDROCK_MODEL_ID", "")
        if not model_id:
            raise EnvironmentError(
                "BEDROCK_MODEL_ID is not set. "
                "Set it in your .env file (e.g. BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-20250514-v1:0)."
            )
        region = os.environ.get("AWS_REGION", "")
        if not region:
            raise EnvironmentError(
                "AWS_REGION is not set. "
                "Set it in your .env file (e.g. AWS_REGION=ap-southeast-2)."
            )
        profile = os.environ.get("AWS_PROFILE", "")
        if not profile:
            raise EnvironmentError(
                "AWS_PROFILE is not set. "
                "Set it in your .env file (e.g. AWS_PROFILE=default)."
            )
        logger.info(
            f"🚀 Initializing Strands Orchestrator with Bedrock Model: {model_id} "
            f"(region={region}, profile={profile})"
        )
        return BedrockModel(
            model_id=model_id,
            region_name=region,
            streaming=False,
        )


async def main():
    parser = argparse.ArgumentParser(description="Agentic Analytics Orchestrator")
    parser.add_argument(
        "--use-api-key",
        action="store_true",
        default=False,
        help="Use LiteLLM with API keys instead of the default Amazon Bedrock.",
    )
    parser.add_argument(
        "--use-memory",
        action="store_true",
        default=False,
        help="Enable Mem0 long-term memory for the agent.",
    )
    args = parser.parse_args()

    # Load environment variables from .env if present
    load_dotenv()

    # 1. Initialize the LLM
    llm = build_model(use_api_key=args.use_api_key)

    # 2. Configure MCP to spawn WrenAI semantic server
    base_dir = os.path.dirname(os.path.abspath(__file__))
    wren_home_env = os.environ.get("WREN_HOME", "../semantic_engine/.wren_project")
    wren_home = os.path.abspath(os.path.join(base_dir, wren_home_env))

    # We use MCPServerConfig format internally loaded via MCPClient.load_servers
    mcp_config = {
        "mcpServers": {
            "wren_semantic_engine": {
                "command": "wren",
                "args": ["serve", "mcp"],
                "cwd": wren_home,
                "env": {
                    "WREN_HOME": wren_home,
                    "PATH": os.environ.get("PATH", "")
                }
            }
        }
    }

    logger.info(f"🔌 Connecting to WrenAI MCP Server at {wren_home}...")

    try:
        # Load the MCP client natively using the Strands SDK
        mcp_clients = MCPClient.load_servers(mcp_config)
    except Exception as e:
        logger.error(f"❌ Failed to connect to MCP Server: {e}")
        logger.error("Make sure 'wren' is installed and WREN_HOME is correct.")
        sys.exit(1)

    # 3. Build the Agent
    system_prompt = """You are an AI data orchestrator using WrenAI through MCP.
    
For EVERY SINGLE data question (including follow-ups), you MUST follow this exact workflow:

1. Call `get_instructions` to obtain relevant business rules.
2. Call `get_context` with the user's original question to find relevant models, columns, and relationships.
   - Do not retrieve the complete MDL (e.g. `list_models`) unless `get_context` is insufficient.
   - Never guess physical schemas (e.g. INFORMATION_SCHEMA).
3. Call `recall_queries` with the user's original question.
   - If the user's question has an exact normalized intent and identical parameters to a recalled example, you may execute its `sql_query` VERBATIM using `run_sql`.
   - Otherwise, use the recalled SQL as a reviewed example and adapt it carefully to the new parameters (e.g. date ranges, sort directions, or specific filters).
4. Determine the execution path based on the context:
    - CUBE PATH (PREFERRED): If the requested metric maps to a cube measure (e.g. daily_revenue.gross_revenue, customer_lifetime_value.lifetime_spend, product_performance.units_sold), you MUST use `query_cube` FIRST. This is ALWAYS your first choice when a cube covers the question. Since `query_cube` executes the query automatically, DO NOT call `dry_plan`, `dry_run`, or `run_sql` for this path.
      * KNOWN LIMITATION: On Trino, cube queries with time dimension filters (e.g. "yesterday", "last 7 days") may fail with a TYPE_MISMATCH error due to Trino not implicitly casting between TIMESTAMP and VARCHAR. If `query_cube` fails with a type mismatch error, you may fall back to `run_sql` with equivalent logical SQL.
    - NON-CUBE PATH: If no cube exists for the metric, write the query in logical SQL using only the exact Wren MDL object names (never prefix them). Then, execute this sequence:
      1. Call `dry_run` with your logical SQL to validate it against the physical database.
      2. If `dry_run` passes (returns ok: True), call `run_sql` with the same logical SQL to retrieve the rows and answer the user.
      * Note: You may optionally call `dry_plan` if you need to inspect the generated physical SQL dialect translation, but `dry_run` is the required validation gate.
    - If validation fails more than twice, STOP IMMEDIATELY and inform the user.
    - If a requested concept does not exist, do NOT hallucinate. Inform the user and suggest an alternative.

CRITICAL: Do not bypass `get_context` and `recall_queries` for analytical questions. Memory retrieval is mandatory. Even if you think you remember the schema from a previous turn, YOU MUST call `recall_queries` for EVERY new user query. NO EXCEPTIONS.

EVALUATION REQUIREMENT: Even if a query returns zero results, you MUST explicitly state the name of the tool you used (e.g. `query_cube` or `run_sql`) and the exact SQL or parameters you executed in your final text response so your work can be evaluated."""

    # Assemble tools
    tools_list = [mcp_clients]

    # Optional Mem0 Integration
    if args.use_memory:
        try:
            from mem0 import Memory
            from strands.tools.decorator import tool
            
            logger.info("🧠 Initializing Mem0 Long-Term Memory via Valkey...")
            
            # Configure Mem0 to use Valkey (Redis-compatible)
            valkey_url = os.environ.get("VALKEY_URL", "redis://user:password@localhost:6379")
            mem0_config = {
                "vector_store": {
                    "provider": "redis",
                    "config": {
                        "redis_url": valkey_url
                    }
                },
                "embedder": {
                    "provider": "fastembed",
                    "config": {
                        "model": "BAAI/bge-small-en-v1.5"
                    }
                }
            }
            mem0_client = Memory.from_config(mem0_config)

            _saved_preferences = set()
            
            @tool(description="MANDATORY: Call this tool IMMEDIATELY when the user states a rule, preference, or instruction for future queries (e.g., 'I always want...', 'Never do...'). Do not validate the schema first.")
            def save_user_preference_to_memory(preference: str) -> str:
                if preference in _saved_preferences:
                    return f"Preference already saved (duplicate skipped): {preference}"
                _saved_preferences.add(preference)
                mem0_client.add(preference, user_id="user")
                return f"Successfully saved preference: {preference}"
                
            @tool(description="Search long-term memory for facts or context from past conversations.")
            def search_memory(query: str) -> str:
                results = mem0_client.search(query, filters={"user_id": "user"})
                return str(results)

            tools_list.extend([save_user_preference_to_memory, search_memory])
            
            memory_directive = (
                "CRITICAL OVERRIDE: If the user provides a preference, rule, or instruction for how to handle future queries (e.g., 'I always want...', 'Assume that...'), "
                "you MUST immediately execute the `save_user_preference_to_memory` tool. DO NOT invoke ANY WrenAI MCP schema tools first. Just save it and reply.\n\n"
                "Furthermore, for ANY data question, you MUST execute the `search_memory` tool BEFORE generating SQL to retrieve any relevant user preferences or definitions.\n\n"
            )
            system_prompt = memory_directive + system_prompt
            
        except ImportError as e:
            logger.warning(f"Failed to load Mem0 or its dependencies. Error: {e}")
            logger.warning("Make sure 'mem0ai', 'redis', and 'fastembed' are properly installed.")
    else:
        logger.info("🧠 Mem0 memory is disabled (ephemeral mode).")

    agent = Agent(
        model=llm,
        tools=tools_list,
        system_prompt=system_prompt
    )

    logger.info("🧠 Orchestrator is online. Type 'exit' or 'quit' to close.\n")

    # 4. Interactive Loop
    while True:
        try:
            user_input = input("User ❯ ")
            if user_input.lower() in ["exit", "quit"]:
                break
            if not user_input.strip():
                continue

            logger.info("Agent is thinking...")

            # The agent's default callback handler streams the text automatically!
            # We just await the invocation, then print a newline for clean formatting.
            await agent.invoke_async(
                user_input,
                limits={
                    "turns": 10,
                    "output_tokens": 2_000,
                    "total_tokens": 50_000,
                }
            )
            print("\n")

        except (KeyboardInterrupt, EOFError):
            logger.info("Exiting...")
            break
        except Exception as e:
            logger.error(f"⚠️ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
