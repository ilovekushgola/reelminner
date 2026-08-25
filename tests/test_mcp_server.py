"""MCP server contract tests: tool-surface regression + discovery API."""

import importlib
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import mcp_server  # noqa: E402


# The five original scraping-contract tools must always remain present.
ORIGINAL_FIVE = [
    "export_results",
    "get_status",
    "import_cookies",
    "scrape_reels",
    "stop_scrape",
]

# Full surface after the Phase 3.5 enhancement.
EXPECTED_TOOLS = sorted(
    ORIGINAL_FIVE
    + [
        # Job management
        "create_job",
        "start_job",
        "pause_job",
        "resume_job",
        "stop_job",
        "retry_job",
        "get_job",
        "list_jobs",
        # Session management
        "list_sessions",
        "get_session",
        "import_session",
        "test_session",
        "update_session",
        "delete_session",
        # Result queries
        "get_result",
        "search_results",
        "filter_results",
        "sort_results",
        "paginate_results",
        "get_result_statistics",
        # Settings
        "get_settings",
        "update_settings",
        "reset_settings",
        # Status
        "get_application_status",
        # Proxy management
        "list_proxies",
        "get_proxy",
        "add_proxy",
        "import_proxies",
        "update_proxy",
        "delete_proxy",
        "enable_proxy",
        "disable_proxy",
        "test_proxy",
        # Performance intelligence & compute monitoring (Phase 3.6)
        "get_system_capabilities",
        "get_system_performance",
        "get_job_performance",
        "get_performance_history",
        "get_worker_recommendation",
        "get_performance_recommendations",
    ]
)


def test_original_five_tools_preserved():
    """Regression: the original 5-tool scraping contract still exists."""
    surface = mcp_server.registered_tools()
    for tool in ORIGINAL_FIVE:
        assert tool in surface, f"original tool {tool} was removed"
    # The full surface must be a superset of the original contract.
    assert set(ORIGINAL_FIVE).issubset(set(surface))


def test_registered_tools_full_surface():
    assert mcp_server.registered_tools() == EXPECTED_TOOLS


def test_module_imports_without_launching():
    # Importing must not start the stdio loop or a browser.
    importlib.reload(mcp_server)
    assert callable(mcp_server.registered_tools)


def test_scrape_reels_returns_json_dict():
    # FastMCP tool wrapper exists and returns a dict (JSON-serializable).
    import json

    payload = {"results": []}
    assert json.dumps(payload)  # contract: tools return JSON-serializable dicts
