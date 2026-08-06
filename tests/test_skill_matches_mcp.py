"""SKILL.md must document every real MCP tool — no fabricated tool names."""

import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import mcp_server  # noqa: E402

SKILL = PROJECT / "skills" / "instagram-reel-scraper" / "SKILL.md"


def test_skill_documents_all_tools():
    doc = SKILL.read_text(encoding="utf-8")
    tools = mcp_server.registered_tools()
    assert tools, "mcp_server.registered_tools() returned empty"
    for name in tools:
        assert f"**{name}**" in doc, f"SKILL.md missing tool section: {name}"


def test_skill_frontmatter_valid():
    doc = SKILL.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", doc, re.DOTALL)
    assert m, "SKILL.md must start with YAML frontmatter"
    fm = m.group(1)
    assert "name: instagram-reel-scraper" in fm
    assert "description:" in fm


def test_skill_examples_only_use_registered_tools():
    doc = SKILL.read_text(encoding="utf-8")
    tools = set(mcp_server.registered_tools())
    # Bold tool mentions in the doc must all be real registered tools
    # (a small prose whitelist covers bold emphasis that isn't a tool name).
    PROSE_WORDS = {"first"}
    mentioned = set(re.findall(r"\*\*([a-z_]+)\*\*", doc))
    bogus = mentioned - tools - PROSE_WORDS
    assert not bogus, f"SKILL.md mentions unregistered tools: {bogus}"


def test_mirror_copy_in_sync():
    mirror = (
        PROJECT.parent
        / ".aionrs"
        / "skills"
        / "instagram-reel-scraper"
        / "SKILL.md"
    )
    assert mirror.exists(), "mirror copy missing in .aionrs/skills/"
    assert (
        mirror.read_text(encoding="utf-8") == SKILL.read_text(encoding="utf-8")
    ), "mirror copy is out of sync"
