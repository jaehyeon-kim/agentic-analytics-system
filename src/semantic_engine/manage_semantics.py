import os
import subprocess
import json
import logging
import argparse

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Hardcoded schema definitions for the CLI generator for simplicity in this PoC.
# In a full production system, this would dynamically query Trino's information_schema.
MODELS = {
    "customers": {
        "description": "Core table containing all registered e-commerce customers.",
        "columns": [
            {"name": "customer_id", "type": "integer", "is_primary_key": True},
            {"name": "first_name", "type": "varchar"},
            {"name": "last_name", "type": "varchar"},
            {"name": "loyalty_tier", "type": "varchar"},
            {"name": "created_at", "type": "timestamp"}
        ]
    },
    "products": {
        "description": "Table containing the catalog of all products sold.",
        "columns": [
            {"name": "product_id", "type": "integer", "is_primary_key": True},
            {"name": "product_name", "type": "varchar"},
            {"name": "category", "type": "varchar"},
            {"name": "price", "type": "double"},
            {"name": "stock_quantity", "type": "integer"},
            {"name": "created_at", "type": "timestamp"}
        ]
    },
    "orders": {
        "description": "Transactional table recording every purchase order placed by customers.",
        "columns": [
            {"name": "order_id", "type": "integer", "is_primary_key": True},
            {"name": "customer_id", "type": "integer"},
            {"name": "total_amount", "type": "double"},
            {"name": "status", "type": "varchar"},
            {"name": "created_at", "type": "timestamp"}
        ]
    },
    "order_items": {
        "description": "Line-item level details for every order.",
        "columns": [
            {"name": "order_item_id", "type": "integer", "is_primary_key": True},
            {"name": "order_id", "type": "integer"},
            {"name": "product_id", "type": "integer"},
            {"name": "quantity", "type": "integer"},
            {"name": "unit_price", "type": "double"},
            {"name": "total_price", "type": "double"},
            {"name": "is_returned", "type": "boolean"},
            {"name": "created_at", "type": "timestamp"}
        ]
    },
    "returns": {
        "description": "Records of returned products and refunded amounts.",
        "columns": [
            {"name": "return_id", "type": "integer", "is_primary_key": True},
            {"name": "order_id", "type": "integer"},
            {"name": "customer_id", "type": "integer"},
            {"name": "product_id", "type": "integer"},
            {"name": "refund_amount", "type": "double"},
            {"name": "return_status", "type": "varchar"},
            {"name": "created_at", "type": "timestamp"}
        ]
    },
    "payments": {
        "description": "Financial transactions recording payments for orders.",
        "columns": [
            {"name": "transaction_id", "type": "varchar", "is_primary_key": True},
            {"name": "order_id", "type": "integer"},
            {"name": "customer_id", "type": "integer"},
            {"name": "amount", "type": "double"},
            {"name": "merchant", "type": "varchar"},
            {"name": "transaction_type", "type": "varchar"},
            {"name": "created_at", "type": "timestamp"}
        ]
    },
    "daily_revenue": {
        "description": "Business Metric: Aggregated daily net revenue.",
        "columns": [
            {"name": "date", "type": "date"},
            {"name": "gross_revenue", "type": "double"},
            {"name": "total_refunds", "type": "double"},
            {"name": "net_revenue", "type": "double"}
        ]
    },
    "customer_lifetime_value": {
        "description": "Business Metric: Aggregated lifetime spend per customer.",
        "columns": [
            {"name": "customer_id", "type": "integer"},
            {"name": "first_name", "type": "varchar"},
            {"name": "last_name", "type": "varchar"},
            {"name": "total_orders", "type": "integer"},
            {"name": "lifetime_spend", "type": "double"}
        ]
    },
    "product_performance": {
        "description": "Business Metric: Aggregated product sales performance.",
        "columns": [
            {"name": "product_id", "type": "integer"},
            {"name": "product_name", "type": "varchar"},
            {"name": "category", "type": "varchar"},
            {"name": "units_sold", "type": "integer"},
            {"name": "gross_sales", "type": "double"}
        ]
    }
}

def init_project():
    """Initializes the semantic_engine folder structure and Trino profile."""
    os.makedirs("src/semantic_engine/models", exist_ok=True)
    
    project_config = {
        "type": "project",
        "name": "agentic-ecommerce",
        "profile": {
            "type": "trino",
            "properties": {
                "host": "localhost",
                "port": 8080,
                "user": "user",
                "password": "password",
                "catalog": "iceberg",
                "schema": "ecommerce"
            }
        }
    }
    with open("src/semantic_engine/wren_project.yml", "w") as f:
        f.write(json.dumps(project_config, indent=2))
    logger.info("✅ Initialized WrenAI project and Trino profile.")

def add_model(table_name):
    """Generates the MDL YAML for a specific table."""
    if table_name not in MODELS:
        logger.error(f"❌ Table '{table_name}' definition not found in registry.")
        return
    
    meta = MODELS[table_name]
    yaml_lines = [
        "type: model",
        f"name: {table_name}",
        f"description: \"{meta['description']}\"",
        f"table_reference: iceberg.ecommerce.{table_name}",
        "columns:"
    ]
    
    for col in meta["columns"]:
        yaml_lines.append(f"  - name: {col['name']}")
        yaml_lines.append(f"    type: {col['type']}")
        if col.get("is_primary_key"):
            yaml_lines.append("    is_primary_key: true")
            
    # For a production CLI, relationships would be appended here dynamically.
    
    with open(f"src/semantic_engine/models/{table_name}.yml", "w") as f:
        f.write("\n".join(yaml_lines) + "\n")
        
    logger.info(f"✅ Created model: {table_name}.yml")

def remove_model(table_name):
    """Deletes an MDL YAML file."""
    path = f"src/semantic_engine/models/{table_name}.yml"
    if os.path.exists(path):
        os.remove(path)
        logger.info(f"🗑️ Removed model: {table_name}.yml")
    else:
        logger.warning(f"⚠️ Model {table_name}.yml does not exist.")

def list_models():
    """Lists all active models in the engine."""
    path = "src/semantic_engine/models"
    if not os.path.exists(path):
        logger.error("❌ Models directory does not exist. Run 'init' first.")
        return
        
    files = os.listdir(path)
    if not files:
        logger.info("📂 No models currently tracked.")
    else:
        logger.info("📂 Currently tracked models:")
        for f in files:
            if f.endswith(".yml"):
                logger.info(f"  - {f.replace('.yml', '')}")

def build_context():
    """Recompiles the WrenAI semantic context into LanceDB."""
    logger.info("🧠 Compiling Semantic Context (Vectorizing to LanceDB)...")
    try:
        subprocess.run(["wren", "context", "build"], cwd="src/semantic_engine", check=True)
        logger.info("🎉 Semantic Engine built successfully! LanceDB memory is populated.")
    except FileNotFoundError:
        logger.error("⚠️ 'wren' CLI not found. Make sure you have activated your virtual environment.")
    except subprocess.CalledProcessError:
        logger.error("⚠️ Failed to build the Wren context. Check your Trino connection and syntax.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WrenAI Semantic Engine Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init
    subparsers.add_parser("init", help="Initialize the project and Trino profile")
    
    # Add
    parser_add = subparsers.add_parser("add", help="Add a table/view to the semantic layer")
    parser_add.add_argument("table", help="Name of the table to model (e.g. customers, daily_revenue, all)")
    
    # Remove
    parser_remove = subparsers.add_parser("remove", help="Remove a table/view from the semantic layer")
    parser_remove.add_argument("table", help="Name of the table to remove")
    
    # List
    subparsers.add_parser("list", help="List all currently tracked models")
    
    # Build
    subparsers.add_parser("build", help="Compile the semantic context into LanceDB")

    args = parser.parse_args()

    if args.command == "init":
        init_project()
    elif args.command == "add":
        if args.table == "all":
            for t in MODELS.keys():
                add_model(t)
        else:
            add_model(args.table)
    elif args.command == "remove":
        remove_model(args.table)
    elif args.command == "list":
        list_models()
    elif args.command == "build":
        build_context()
