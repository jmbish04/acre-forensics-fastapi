import os
import sys

import nbformat

# Try multiple paths (host vs container)
POSSIBLE_PATHS = [
    "src/notebooks/forensics_notebook.ipynb",
    "/home/jovyan/work/forensics_notebook.ipynb",
    "work/forensics_notebook.ipynb",
    "forensics_notebook.ipynb",
]

NOTEBOOK_PATH = None
for p in POSSIBLE_PATHS:
    if os.path.exists(p):
        NOTEBOOK_PATH = p
        break

if not NOTEBOOK_PATH:
    print(f"File not found in any of: {POSSIBLE_PATHS}")
    sys.exit(1)

print(f"Using notebook path: {NOTEBOOK_PATH}")


def fix_notebook():
    try:
        with open(NOTEBOOK_PATH, "r", encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)
    except FileNotFoundError:
        print(f"File not found: {NOTEBOOK_PATH}")
        sys.exit(1)

    # 1. Update Imports Cell
    # Looking for cell containing "from src.notebooks.forensics_helpers import"
    found_imports = False
    for cell in nb.cells:
        if (
            cell.cell_type == "code"
            and "from src.notebooks.forensics_helpers import" in cell.source
        ):
            # Force rewrite of imports to ensure correctness
            cell.source = """import os
import sys
import pandas as pd
import numpy as np
import plotly.express as px
from IPython.display import display, HTML

# Add project root to path for imports
project_root = os.path.abspath(os.path.join(os.getcwd(), '../..'))
if project_root not in sys.path:
    sys.path.append(project_root)

# Import our custom helpers
from src.notebooks.forensics_helpers import (
    get_db_connection_string, 
    get_engine, 
    test_connection, 
    discover_schema, 
    sanitize_html, 
    extract_text_from_html,
    load_threads,
    load_messages,
    find_similar_messages
)

print("✅ Setup Complete. Libraries Imported.")"""
            print("Force updated imports cell.")
            found_imports = True
            break

    if not found_imports:
        print("Warning: Could not find import cell.")

    # 2. Update Data Loading Cell
    # Looking for cell containing "# Load Threads" and "pd.read_sql"
    found_loading = False
    new_loading_source = """# Load Threads
try:
    df_threads = load_threads(engine, schema_map)
    print(f"Loaded {len(df_threads)} threads.")
    display(df_threads.head(3))
except Exception as e:
    print(f"Error loading threads: {e}")
    df_threads = pd.DataFrame()

# Load Messages
try:
    # Load messages using helper (schema adaptive)
    df_messages = load_messages(engine, schema_map, include_embedding=False)
    
    if not df_messages.empty:
        # Computed Fields
        df_messages['plain_len'] = df_messages['bodyPlain'].astype(str).apply(len)
        df_messages['html_len'] = df_messages['bodyHtml'].astype(str).apply(len)
        df_messages['has_html'] = df_messages['html_len'] > 10
    
    print(f"Loaded {len(df_messages)} messages.")
    display(df_messages.head(3))
except Exception as e:
    print(f"Error loading messages: {e}")
    df_messages = pd.DataFrame()"""

    for cell in nb.cells:
        if (
            cell.cell_type == "code"
            and "# Load Threads" in cell.source
            and "pd.read_sql" in cell.source
        ):
            cell.source = new_loading_source
            found_loading = True
            print("Updated data loading cell.")
            break

    if not found_loading:
        print("Warning: Could not find data loading cell to update.")

    # Save
    with open(NOTEBOOK_PATH, "w", encoding="utf-8") as f:
        nbformat.write(nb, f)
    print("Notebook saved.")


if __name__ == "__main__":
    fix_notebook()
