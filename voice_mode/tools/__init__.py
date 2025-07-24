"""Auto-import all tools for registration with FastMCP."""
import os
import importlib
from pathlib import Path

# Get the directory containing this file
tools_dir = Path(__file__).parent

# Import all Python files in this directory (except __init__.py)
for file in tools_dir.glob("*.py"):
    if file.name != "__init__.py" and not file.name.startswith("_"):
        module_name = file.stem
        importlib.import_module(f".{module_name}", package=__name__)

# Import all service tools from subdirectories
services_dir = tools_dir / "services"
if services_dir.exists():
    for service_dir in services_dir.iterdir():
        if service_dir.is_dir() and not service_dir.name.startswith("_"):
            # Import all Python files in each service directory
            for file in service_dir.glob("*.py"):
                if file.name != "__init__.py" and not file.name.startswith("_") and file.name != "helpers.py":
                    module_path = f".services.{service_dir.name}.{file.stem}"
                    importlib.import_module(module_path, package=__name__)