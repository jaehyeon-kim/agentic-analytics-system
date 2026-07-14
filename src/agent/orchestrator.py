import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

from strands import Agent
from strands.models.litellm import LiteLLMModel
from strands.tools.mcp.mcp_client import MCPClient

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

async def main():
    # Load environment variables from .env if present
    load_dotenv()
    
    agent_model = os.environ.get("AGENT_MODEL", "your-agent-model")
    logger.info(f"🚀 Initializing Strands Orchestrator with Model: {agent_model}")
    
    # 1. Initialize the LLM neutrally
    llm = LiteLLMModel(model=agent_model)
    
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
2. Formulate a logical query plan based on the user's intent.
3. Validate your SQL using dry_plan before execution.
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
            response = await agent.invoke_async(user_input)
            
            # Extract text from the message content blocks
            final_text = ""
            for block in response.message.content:
                if hasattr(block, "text"):
                    final_text += block.text
            
            print(f"Agent ❯ {final_text}\n")
            
        except KeyboardInterrupt:
            logger.info("Exiting...")
            break
        except Exception as e:
            logger.error(f"⚠️ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
