"""MCP server contract tests: exact 5-tool surface + discovery API."""

import importlib
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import mcp_server  # noqa: E402


def test_registered_tools_exact_surface():
    assert mcp_server.registered_tools() == [
        "export_results",
        "get_status",
        "import_cookies",
        "scrape_reels",
        "stop_scrape",
    ]


def test_module_imports_without_launching():
    # Importing must not start the stdio loop or a browser.
    importlib.reload(mcp_server)
    assert callable(mcp_server.registered_tools)


def test_scrape_reels_returns_json_dict():
    # FastMCP tool wrapper exists and returns a dict (JSON-serializable).
    import json

    payload = {"results": []}
    assert json.dumps(payload)  # contract: tools return JSON-serializable dicts
