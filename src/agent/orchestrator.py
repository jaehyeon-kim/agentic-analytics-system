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
    system_prompt = """You are an elite autonomous AI Data Orchestrator. 
Your goal is to answer user questions accurately by querying the semantic layer.
You have access to the WrenAI semantic layer via MCP tools. 
1. Explore the schema to find relevant metrics and models. 
   IMPORTANT: Users will ask natural language questions (e.g. "order items" or "revenue"). 
   Do not expect them to know whether something is a 'cube', 'model', or 'view'. 
   You must autonomously map their natural language to the correct semantic objects in the schema.
   CRITICAL: Never try to guess the schema using physical backend tables (e.g. INFORMATION_SCHEMA or pg_catalog). Only use `list_models` and `list_cubes` to discover available tables and metrics.
2. Formulate a logical query plan based on the user's intent. When writing SQL, use the EXACT model names returned by `list_models` (e.g. `returned_orders`). NEVER prefix them with physical schemas like `ecommerce.returned_orders`.
   CRITICAL: If a requested concept does not exist, DO NOT hallucinate. Instead, analyze the schema for semantically related columns (e.g., if 'return reason' is missing, suggest 'return_status'). Inform the user about the missing data and ask if they would like you to query the alternative instead. Do not automatically execute a fallback query if the requested data is missing.
3. Validate your SQL using dry_plan before execution.
   CRITICAL: If `dry_plan` or `run_sql` fails more than twice with syntax or table not found errors, STOP IMMEDIATELY. Do not keep retrying. Inform the user of the error.
4. Execute the SQL and return the precise answer."""

    # Note: Mem0 memory manager is specifically excluded here as requested.
    agent = Agent(
        model=llm,
        tools=mcp_clients,
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
            response = await agent.invoke_async(user_input)
            print("\n")

        except KeyboardInterrupt:
            logger.info("Exiting...")
            break
        except Exception as e:
            logger.error(f"⚠️ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
