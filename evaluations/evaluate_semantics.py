import os
import sys
import json
import asyncio
import argparse
import logging
from typing import Dict, List, Any
from dotenv import load_dotenv

# Add src to path to import orchestrator logic
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from src.agent.orchestrator import build_model

from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("evaluator")

def load_test_suite(filepath: str) -> List[Dict[str, Any]]:
    with open(filepath, "r") as f:
        return json.load(f)

async def evaluate_suite(suite_path: str, use_api_key: bool, limit: int = None):
    logger.info("🚀 Starting Agentic Semantic Evaluation Harness")
    tests = load_test_suite(suite_path)
    
    if limit is not None and limit > 0:
        tests = tests[:limit]
        
    total = len(tests)
    logger.info(f"Loaded {total} golden test cases.")

    # 1. Setup LLM and MCP exactly like the Orchestrator
    llm = build_model(use_api_key=use_api_key)
    
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    wren_home_env = os.environ.get("WREN_HOME", "src/semantic_engine/.wren_project")
    wren_home = os.path.abspath(os.path.join(base_dir, wren_home_env))
    
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
    
    logger.info("🔌 Connecting to WrenAI MCP Server for Evaluation...")
    mcp_clients = MCPClient.load_servers(mcp_config)

    # Use the same exact prompt we use in production
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
   - CUBE PATH: If the requested metric is represented by a cube (e.g. daily_revenue, customer_lifetime_value, product_performance), you MUST use `query_cube`. Since `query_cube` executes the query automatically, DO NOT call `dry_plan`, `dry_run`, or `run_sql` for this path.
   - NON-CUBE PATH: If no cube exists for the metric, generate SQL using only the exact Wren MDL object names (never prefix them). Then, validate the SQL using `dry_plan` (to expand the semantic model) and `dry_run` (to validate against the physical database). If validation passes, execute using `run_sql`.
   - If validation fails more than twice, STOP IMMEDIATELY and inform the user.
   - If a requested concept does not exist, do NOT hallucinate. Inform the user and suggest an alternative.

CRITICAL: Do not bypass `get_context` and `recall_queries` for analytical questions. Memory retrieval is mandatory. Even if you think you remember the schema from a previous turn, YOU MUST call `recall_queries` for EVERY new user query. NO EXCEPTIONS. 

EVALUATION REQUIREMENT: Even if a query returns zero results, you MUST explicitly state the name of the tool you used (e.g. `query_cube` or `run_sql`) and the exact SQL or parameters you executed in your final text response so your work can be evaluated."""

    failed = 0
    results = []

    print("\n" + "="*50)
    print("🧪 BEGINNING EVALUATION RUN")
    print("="*50 + "\n")

    for i, test in enumerate(tests, 1):
        print(f"Test {i}/{total} | Category: {test['category']}")
        print(f"Question: {test['question']}")
        
        result_record = {
            "test_id": i,
            "category": test["category"],
            "question": test["question"],
            "status": "UNKNOWN",
            "agent_response": None,
            "error": None
        }
        
        try:
            # We instantiate the agent per test for true memory isolation
            test_agent = Agent(
                model=llm,
                tools=mcp_clients,
                system_prompt=system_prompt
            )
            
            logger.info("Executing Agent...")
            response = await test_agent.invoke_async(
                test["question"],
                limits={
                    "turns": 6,
                    "output_tokens": 2_000,
                    "total_tokens": 12_000,
                }
            )
            
            print(f"Agent Response:\n{response}")
            print("-" * 50)
            
            # Since invoke_async streams to stdout in Strands, it might return None.
            # We cast to string to capture it if it does return a string or object.
            agent_text = str(response)
            result_record["status"] = "COMPLETED"
            result_record["agent_response"] = agent_text
            
            # LLM-as-a-Judge Evaluation
            logger.info("Evaluating response...")
            judge_agent = Agent(
                model=llm,
                system_prompt="You are a strict evaluator. Respond exactly with 'PASS' or 'FAIL' on the first line, followed by a 1-sentence reason on the next line."
            )
            
            judge_prompt = f"""An AI agent was asked: "{test['question']}"
            The expected category of this task is: {test['category']}.
            Expected constraints to check against:
            {json.dumps(test, indent=2)}
            
            The agent's final response was:
            "{agent_text}"
            
            Did the agent meet the expected constraints? For negative_test, it MUST gracefully refuse (not error out or hallucinate). For others, it should have the data.
            """
            
            judge_response = await judge_agent.invoke_async(
                judge_prompt,
                limits={
                    "turns": 2,
                    "output_tokens": 500,
                    "total_tokens": 4_000,
                }
            )
            judge_text = str(judge_response).strip()
            
            if judge_text.upper().startswith("PASS"):
                result_record["grade"] = "PASS"
            elif judge_text.upper().startswith("FAIL"):
                result_record["grade"] = "FAIL"
                failed += 1
            else:
                result_record["grade"] = "UNKNOWN"
                failed += 1
                
            result_record["judge_reason"] = judge_text
            print(f"Grade: {result_record['grade']}")
            print(f"Reason: {result_record['judge_reason']}")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Test failed with error: {error_msg}")
            result_record["status"] = "ERROR"
            result_record["error"] = error_msg
            failed += 1
            
        results.append(result_record)

    # Save results to a file
    results_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evaluation_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "="*50)
    print("🏁 EVALUATION COMPLETE")
    print(f"Errors encountered: {failed}")
    print(f"Results saved to: {results_path}")
    print("Manual review required for exact Tool Call matching in standard output.")
    print("="*50 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agentic Semantic Evaluation Runner")
    parser.add_argument("--suite", default="evaluations/golden_test_suite.json", help="Path to golden test suite JSON")
    parser.add_argument("--use-api-key", action="store_true", default=False, help="Use API key instead of Bedrock")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of tests to run (default: all)")
    args = parser.parse_args()
    
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "src", "agent", ".env"))
    
    asyncio.run(evaluate_suite(args.suite, args.use_api_key, args.limit))
