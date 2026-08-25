# Instagram Reel Scraper — .exe Installer + UI Enhancement + MCP Server + Agent Skill

> **For agentic workers:** execute with `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`. Each task below has a **DISPATCH** block — paste it verbatim into a fresh sub-agent, review its output against **DONE WHEN**, and run the listed skill before advancing.

**Goal:** Ship the scraper as an installable Windows .exe with a polished dark-themed frontend, expose it to AI agents via an MCP server, and give agents a SKILL.md so they can drive it autonomously.

**Architecture:** 4 independent phases — (1) PyInstaller + Inno Setup packaging, (2) Tkinter restyle driven by a central `theme.py` token module, (3) FastMCP stdio server reusing `scraper.py` programmatically, (4) agent-facing SKILL.md validated against real MCP tool names. Each phase ends in a testable artifact.

**Tech Stack:** Python 3.11, Tkinter/ttk, PyInstaller 6.21, Inno Setup 6, MCP SDK 1.26 (FastMCP), pytest.

## Global Constraints

- All paths relative to `reelminner/` unless absolute.
- The 58 existing tests must keep passing; new tests use pytest.
- No emoji as icons. Unicode glyphs (`▶`, `■`) are allowed only in the tool window; keep all brand visuals in code (canvas) or generated assets.
- Every entry point must work both as `.py` and frozen inside the `.exe` (guard paths with `getattr(sys, "_MEIPASS", Path(__file__).parent)`).
- Tree column order is fixed: `COLUMN_ORDER = ("idx","username","followers","reel_url","music","artist","likes","status")` — `reel_url` is index 3; never hardcode indices, always `COLUMN_ORDER.index(...)`.
- MCP: exactly one scrape at a time (threading lock), `stop_scrape` must be able to abort it.
- After Phase 2, zero hardcoded colors in widgets — everything reads from `theme.py`.
- Commit after every task with the exact message given.

## Skill Map — invoke the best skill per sub-task

| Task | Skills to invoke | Why |
|---|---|---|
| 1 | `focused-fix`, `tdd-workflow` | small targeted regression, test-first |
| 2 | `python-executor`, `e2e-testing`, `verification-before-completion` | run build, launch smoke, DoD gate |
| 3 | `e2e-testing`, `verification-loop` | silent-install + uninstall verification |
| 4 | `ui-ux-pro-max`, `theme-factory`, `design-system` | design tokens from the design database |
| 5 | `ui-ux-pro-max`, `frontend-design`, `high-end-visual-design` | shell/header visual polish |
| 6 | `ui-ux-pro-max`, `ui-styling` | card layout + CTA styling |
| 7 | `ui-ux-pro-max`, `ui-styling` | table, log, phase indicator |
| 8 | `ui-ux-pro-max` (ux domain), `web-design-guidelines` | accessibility + interaction polish |
| 9 | `mcp-server-builder`, `mcp-server-patterns`, `strict-api` | FastMCP server + tool contract |
| 10 | `aionui-config`, `mcp-apps-builder`, `documentation-lookup` | register in AionUi, client config |
| 11 | `skill-creator`, `skill-tester`, `skill-reviewer`, `writing-guidelines` | author + validate SKILL.md |
| 12 | `verification-before-completion`, `e2e-testing` | full integration gate |
| meta | `subagent-driven-development`, `executing-plans` | execution mode |

---

## PHASE 1 — Windows .exe Installer

### Task 1: Fix reel_url column-index regression (+ tests)

**Skills:** `focused-fix`, `tdd-workflow` · **Files:** Modify `gui.py:551-563`, Create `tests/test_gui_columns.py`

**DISPATCH**
```
ROLE: Python/Tkinter test-first engineer working in reelminner/.
CONTEXT: gui.py builds a results Treeview with columns
("idx","username","followers","reel_url","music","artist","likes","status").
"followers" was inserted at index 2, so "reel_url" moved to index 3 — but
_copy_url(), _open_url(), and _copy_row() still read values[2] (now the
followers cell). The GUI must be importable without opening a window.
TASK: Fix the index regression and lock it with tests.
STEPS:
1. Export the tuple as module-level COLUMN_ORDER; keep `cols = COLUMN_ORDER`.
2. Write tests/test_gui_columns.py:
   - COLUMN_ORDER[3] == "reel_url" and COLUMN_ORDER[2] == "followers"
   - _copy_url uses COLUMN_ORDER.index("reel_url"), not a literal.
3. pytest tests/test_gui_columns.py -v -> RED (constant missing).
4. Refactor gui.py: add COLUMN_ORDER, switch the three lookups to
   COLUMN_ORDER.index("reel_url"), update the log line in _copy_url.
   Guard window creation behind `if __name__ == "__main__"` so import is safe.
5. pytest tests -q -> GREEN, all 58 existing tests still pass.
CONSTRAINTS: Do not change scraper.py csv_columns() order. No renames.
DONE WHEN: new tests green, full suite green, commit
"fix: reel_url column index after followers insertion".
```

- [ ] Step 1: failing test → Step 2: RED → Step 3: fix → Step 4: GREEN + full suite → Step 5: commit

### Task 2: PyInstaller spec + build script + launch smoke

**Skills:** `python-executor`, `e2e-testing`, `verification-before-completion` · **Files:** Create `build_exe.py`, `Reelminner.spec`, `assets/icon.ico`

**DISPATCH**
```
ROLE: Windows packaging engineer (PyInstaller 6.21 installed).
CONTEXT: Entry point gui.py; deps: playwright, pandas, openpyxl, tkinter.
Target: one-file, windowed (no console) exe named Reelminner.exe.
TASK: Produce a reproducible build script + spec, build, and smoke-launch.
STEPS:
1. assets/make_icon.py -> 128px ICO (indigo rounded square + white play
   triangle, Pillow) written to assets/icon.ico.
2. Reelminner.spec: onefile=True, console=False, name=
   "Reelminner", icon=assets/icon.ico,
   hiddenimports=["playwright.sync_api","playwright._impl._driver",
   "pandas","openpyxl","openpyxl.cell._writer","email","email.mime"],
   datas=[("storage_state.json",".")] only if the file exists at build time.
3. build_exe.py: runs `pyinstaller Reelminner.spec --noconfirm`,
   prints dist\\Reelminner.exe + size when done, exits non-zero on error.
4. python build_exe.py -> exe exists and is > 5 MB.
5. Launch the exe; window opens, no console flash; close it.
6. Run dist\\Reelminner.exe with a --selftest flag stub that prints
   "SELFTEST OK" via a temp file (windowed exes have no stdout): write
   dist\\selftest_report.txt and exit 0. (Implement --selftest in gui.py main:
   argparse; if set, write report and sys.exit(0) without creating the window.)
CONSTRAINTS: Keep source-tree builds working (py_compile gui.py after edits).
DONE WHEN: exe >5MB, launches, selftest file written, commit
"build: pyinstaller spec + build script + --selftest".
```

### Task 3: Inno Setup installer + silent-install verification

**Skills:** `e2e-testing`, `verification-loop` · **Files:** Create `installer/Reelminner.iss`, `installer/install.bat`, `installer/SIGNING.md`

**DISPATCH**
```
ROLE: Windows installer engineer (Inno Setup 6).
CONTEXT: dist\\Reelminner.exe exists from Task 2. Inno Setup may
not be installed — check ISCC.exe on PATH or
"C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe"; if absent,
`winget install --id JRSoftware.InnoSetup -e` (fallback `choco install innosetup`).
TASK: Author the installer, build it, and verify install/uninstall on Windows.
STEPS:
1. installer/Reelminner.iss: AppName "Instagram Reel Scraper",
   version 1.0.0, DefaultDirName {autopf}\\Reelminner,
   PrivilegesRequired=lowest, OutputDir=..\\dist,
   OutputBaseFilename=Reelminner-Setup, lzma2 compression,
   [Files] the exe, [Icons] Start Menu + desktop (Tasks: desktopicon),
   [Run] postinstall launch (skipifsilent).
2. installer/install.bat: `"%ProgramFiles(x86)%\\Inno Setup 6\\ISCC.exe"
   Reelminner.iss`.
3. Run installer\\install.bat -> dist\\Reelminner-Setup.exe exists.
4. Verify: Setup.exe /VERYSILENT /DIR="%TEMP%\\irs-install" -> exe present;
   launch it; then run the uninstaller from the install dir; confirm removal.
5. installer/SIGNING.md documents that the Setup exe is unsigned today and
   what signing step to add (signtool) before public distribution.
CONSTRAINTS: Never hardcode your own user path in the .iss.
DONE WHEN: Setup exe builds, silent install + launch + uninstall all pass,
commit "build: inno setup installer + silent-install smoke".
```

---

## PHASE 2 — Frontend Enhancement (design tokens from ui-ux-pro-max)

### Task 4: Design token module

**Skills:** `ui-ux-pro-max`, `theme-factory`, `design-system` · **Files:** Create `theme.py`

**DISPATCH**
```
ROLE: UI designer-engineer (dark professional developer-tool aesthetic).
CONTEXT: Tkinter app currently hardcodes ACCENT = "#0095F6" and scattered
colors. Goal: one token module every widget reads from.
TASK: Create theme.py with exactly these tokens (verified against the
ui-ux-pro-max dark-tool palette):
  ACCENT="#6366F1" ACCENT_HI="#4F46E5" ACCENT_SOFT="#EEF2FF"
  BG="#0F172A" BG_PANEL="#1E293B" BG_INPUT="#334155"
  FG="#F8FAFC" FG_MUTED="#94A3B8" BORDER="#334155"
  SUCCESS="#22C55E" ERROR="#EF4444"
  MONO=("Consolas",10) UI=("Segoe UI",10) UI_BOLD=("Segoe UI",10,"bold")
  TITLE=("Segoe UI",16,"bold")
Also export COLOR_ROLES = {"bg":BG,"panel":BG_PANEL,"input":BG_INPUT,
"fg":FG,"muted":FG_MUTED,"border":BORDER,"accent":ACCENT,"success":SUCCESS,
"error":ERROR} for future theming/layout code.
STEPS:
1. Write theme.py. 2. python -c "import theme; print(theme.ACCENT)" -> #6366F1.
3. Contrast check: BG(#0F172A) vs FG(#F8FAFC) and BG_INPUT vs FG_MUTED pass
   4.5:1 (compute with a quick script or ui-ux-pro-max checklist).
CONSTRAINTS: No imports beyond standard library. No UI code here.
DONE WHEN: token module imports, contrast verified, commit "feat: theme token module".
```

### Task 5: Dark shell + header panel + status bar

**Skills:** `ui-ux-pro-max`, `frontend-design`, `high-end-visual-design` · **Files:** Modify `gui.py` (constructor, header block ~97-129, bottom of `_build_ui`)

**DISPATCH**
```
ROLE: Tkinter UI engineer applying theme.py.
CONTEXT: Window currently uses ACCENT header bar (row 0), session bar (row 1).
TASK: Apply the dark shell and add a status bar.
STEPS:
1. self.configure(bg=BG). Header: BG_PANEL strip with an ACCENT left accent
   bar (2px tk.Frame), title "Instagram Reel Scraper" in TITLE/FG, subtitle
   "reel URL -> username / followers / music / likes" in FG_MUTED.
2. Session bar (Login/Import/Clear buttons + session_lbl) on BG_PANEL;
   session_lbl FG_MUTED; buttons via ttk.Style Accent.TButton (ACCENT bg,
   FG text, ACCENT_HI active).
3. Add self.status_lbl at the bottom (BG_PANEL, FG_MUTED, 9pt). Wire:
   "Ready" on start; on log kind, if msg contains "Auto-scraping profiles"
   set "Phase 2/2: fetching followers…"; if msg starts "[OK] Done" set
   "Phase 1/2 complete"; on _on_done set "Complete — N/M ok".
4. python -c "import gui" -> OK; launch -> dark shell, header, status bar.
CONSTRAINTS: All colors from theme.py. Existing bindings/logic untouched.
DONE WHEN: shell renders dark with header + status bar, commit
"ui: dark shell + header panel + status bar".
```

### Task 6: Card-style input, options, actions

**Skills:** `ui-ux-pro-max`, `ui-styling` · **Files:** Modify `gui.py:130-216`

**DISPATCH**
```
ROLE: Tkinter UI engineer (theme.py applied).
TASK: Restyle input/options/actions rows.
STEPS:
1. Input LabelFrame -> BG_PANEL card, BORDER outline; URLs Text -> BG_INPUT,
   FG, MONO font; "Paste from clipboard" and "Clear list" buttons cursor
   hand2 + activebackground ACCENT_SOFT.
2. Options row: group into BG_PANEL card; labels FG_MUTED 10pt; checkboxes
   10pt; Spinboxes BG_INPUT/FG.
3. Start button: tk.Button bg=ACCENT, fg="#FFFFFF", font=TITLE, hover
   activebackground=ACCENT_HI, disabled bg "#64748B"; Stop button outline
   style with ERROR fg.
4. ttk.Style TProgressbar: trough BG_INPUT, bar ACCENT; progress_lbl MONO.
5. Launch + manual check: hover states visible, progress bar accent-colored.
CONSTRAINTS: Keep all variable names (workers_var, delay_var, headless_var,
auto_save_var, auto_profiles_var, start_btn, stop_btn, progress_bar,
progress_lbl). Colors from theme.py only.
DONE WHEN: rows restyled, launch smoke OK, commit "ui: card-style input/options + accent CTA".
```

### Task 7: Striped results table + colored log + phase indicator

**Skills:** `ui-ux-pro-max`, `ui-styling` · **Files:** Modify `gui.py` tree setup (~226-258), `_add_row`, `_append_log`

**DISPATCH**
```
ROLE: Tkinter data-display engineer.
TASK: Make results table and log scannable; add phase indicator to status bar.
STEPS:
1. Treeview: rowheight=28; headings BG_PANEL/FG_MUTED bold; tags
   "odd"/"even" alternating (even bg #16213A), "ok" fg SUCCESS,
   "error"/"session_expired"/"timeout" fg ERROR/amber (#F59E0B).
2. _add_row: apply parity tag + status tag based on d.status; followers cell
   shown right after username (unchanged index).
3. Log Text: BG_INPUT, MONO 9pt; line-level tags — "[OK]" SUCCESS, "[!]"
   #F59E0B, "[x]" ERROR, default FG_MUTED.
4. Status bar phase logic (from Task 5) triggers on the scraper's existing
   log line "[>] Auto-scraping profiles for followers count...".
5. Smoke: 2 real reel URLs -> striped rows, ok rows green, followers
   populate live, status flips to Phase 2/2, log colored.
CONSTRAINTS: COLUMN_ORDER untouched. Tree iid stays reel_url (stable).
DONE WHEN: manual 2-reel smoke shows all four effects, commit
"ui: striped table + colored log + phase indicator".
```

### Task 8: Accessibility + interaction polish

**Skills:** `ui-ux-pro-max` (ux domain), `web-design-guidelines` · **Files:** Modify `gui.py`

**DISPATCH**
```
ROLE: UI accessibility engineer.
TASK: Keyboard + focus + motion polish.
STEPS:
1. Bindings: Ctrl+Return -> _on_start, Escape -> _on_stop, Ctrl+A selects
   all text in the URLs Text.
2. All ttk buttons get cursor="hand2"; tk.Buttons already have active
   states; add highlightthickness=1 with ACCENT on focus for keyboard nav.
3. No animations/blinking (reduced-motion equivalent); only color state
   changes on hover.
4. Confirm context-menu "Copy URL"/"Open in browser" copy the reel_url cell
   (regression guard from Task 1).
CONSTRAINTS: No new dependencies.
DONE WHEN: shortcuts work, focus visible, commit
"ui: keyboard shortcuts + focus visibility".
```

---

## PHASE 3 — MCP Server for AI Agents

### Task 9: FastMCP stdio server (5 tools)

**Skills:** `mcp-server-builder`, `mcp-server-patterns`, `strict-api` · **Files:** Create `mcp_server.py`, `tests/test_mcp_server.py`

**DISPATCH**
```
ROLE: MCP server engineer (MCP SDK 1.26, FastMCP importable).
CONTEXT: scraper.py exposes Reelminner(headless, workers, delay)
with .scrape(urls, with_profiles=True) returning ReelData list; import
DEFAULT_STATE_FILE from scraper. Server runs on stdio; agents call it.
TASK: Implement mcp_server.py with exactly these 5 tools and a testable
discovery API.
TOOLS (each returns JSON-serializable dict):
- scrape_reels(urls: list[str], workers: int=2, delay: int=1,
  headless: bool=True, with_profiles: bool=True) -> {"results":[{reel_url,
  username, followers, music_title, music_artist, likes, comments, plays,
  status}]}. Acquire threading.Lock non-blocking; if busy return
  {"error":"a scrape is already running"}.
- get_status() -> {"session_ready": DEFAULT_STATE_FILE.exists(),
  "last_run": {"total": n, "ok": m}}.
- import_cookies(json_path: str) -> {"imported": count}.
- stop_scrape() -> sets scraper stop flag, {"stopped": True}.
- export_results(path: str, fmt: str="csv") -> exports last results via the
  existing export helpers (csv/xlsx/json), {"exported": path}.
Support: registered_tools() -> sorted list of tool names (walk
mcp._tool_manager); main() runs mcp.run(); sys.path guard so it imports
scraper.py both from source and frozen exe.
STEPS:
1. Write tests/test_mcp_server.py asserting registered_tools() == the exact
   5 names (alphabetical) -> RED.
2. Implement server; pytest tests/test_mcp_server.py -> GREEN.
3. Integration: start `python mcp_server.py`, connect with MCP Inspector
   (`npx @modelcontextprotocol/inspector`), call scrape_reels with 2 test
   reel URLs -> rows include followers; stop_scrape works mid-run.
CONSTRAINTS: One scrape at a time (lock). Tool names exactly as listed.
DONE WHEN: unit + Inspector smoke pass, commit "feat: FastMCP stdio server (5 tools)".
```

### Task 10: Client config + AionUi registration + docs

**Skills:** `aionui-config`, `mcp-apps-builder`, `documentation-lookup` · **Files:** Create `.mcp.json`, `mcp.env.example`, Modify `README.md`

**DISPATCH**
```
ROLE: MCP integration engineer for AionUi + Claude Desktop + Cursor.
TASK: Ship client configs and register the server in AionUi.
STEPS:
1. .mcp.json: {"mcpServers":{"reelminner":{"command":"python",
   "args":["mcp_server.py"],"cwd":"<ABS_REPO>/reelminner",
   "env":{"RMIN_HEADLESS":"true"}}}} (use the real absolute path).
2. mcp.env.example documents RMIN_HEADLESS, RMIN_WORKERS, RMIN_DELAY,
   RMIN_WITH_PROFILES (server reads them as scrape defaults).
3. Register in AionUi via the aionui-config skill (check its MCP-registry
   docs; add the stdio entry; verify it appears in the UI).
4. README section "AI Agent / MCP Usage": config snippet + tool table
   (name, params, returns, example).
CONSTRAINTS: Do not commit real session/cookie paths in .mcp.json.
DONE WHEN: configs parse, AionUi shows the server, README updated, commit
"docs: mcp client config + aionui registration + README".
```

---

## PHASE 4 — Agent Skill Documentation

### Task 11: SKILL.md for AI agents (validated against MCP)

**Skills:** `skill-creator`, `skill-tester`, `skill-reviewer`, `writing-guidelines` · **Files:** Create `skills/reelminner/SKILL.md`, mirror to `.aionrs/skills/reelminner/SKILL.md`, Create `tests/test_skill_matches_mcp.py`

**DISPATCH**
```
ROLE: Skill author (skill-creator conventions).
CONTEXT: MCP tools from Task 9: scrape_reels, get_status, import_cookies,
stop_scrape, export_results. CLI: python scraper.py <urls...> [--no-profiles]
[--workers N] [--delay N] [--headless].
TASK: Author SKILL.md with YAML frontmatter (name: reelminner;
description: "Scrape Instagram reels + followers via Playwright user session.
MCP tools: scrape_reels, get_status, import_cookies, stop_scrape,
export_results.") then sections:
- What this does (Phase 1 reels -> Phase 2 profiles/followers)
- Prerequisites (storage_state.json or cookie JSON; playwright browsers)
- MCP tools: per tool — signature, params, return schema, example call
- CLI fallback with sample output table
- Status values: ok / timeout / error / session_expired / skipped
- Workflows: "scrape a batch and report followers per reel", "check session
  health first", "export last results to xlsx"
- Troubleshooting: login wall -> overlay dismiss + retry; empty followers ->
  profile fetch fallback; rate limits -> raise delay/workers
STEPS:
1. Write SKILL.md + mirror copy.
2. Write tests/test_skill_matches_mcp.py: read SKILL.md, import mcp_server,
   assert every name in registered_tools() appears as **name** in the doc
   AND every **scrape_reels**-style doc example maps to a registered tool.
3. pytest tests/test_skill_matches_mcp.py -> GREEN; full suite still green.
CONSTRAINTS: No fabricated tool names; validate against registered_tools().
DONE WHEN: validation test green, commit "docs: agent SKILL.md validated against MCP tools".
```

### Task 12: Final integration gate

**Skills:** `verification-before-completion`, `e2e-testing` · **Files:** repo-wide

**DISPATCH**
```
ROLE: Release engineer (verification-before-completion).
TASK: Prove the whole deliverable end-to-end.
STEPS:
1. pytest tests -q -> all green (58 + new).
2. py_compile scraper.py gui.py mcp_server.py theme.py selftest wiring.
3. Rebuild: python build_exe.py && installer\\install.bat -> both artifacts
   fresh; silent-install smoke passes.
4. MCP Inspector smoke (Task 9 step 3) re-run -> 5 tools, scrape returns
   followers.
5. SKILL.md validation test passes (Task 11).
6. git tag v1.0.0 after the release commit.
CONSTRAINTS: Fix regressions in place; never weaken a prior task's test.
DONE WHEN: all gates pass, commit "chore: final integration gate" + tag.
```

---

## Risk Register (Pre-Mortem — assume it shipped broken, find causes now)

| Risk | Failure mode | Mitigation (built into tasks) |
|---|---|---|
| Playwright browsers not bundled | exe opens, scrape crashes "Executable doesn't exist" | Task 2 selftest checks `ms-playwright` dir; README + installer note: run `playwright install chromium` once |
| Inno Setup absent on build machine | installer task blocks | Task 3 auto-installs via winget with choco fallback |
| MCP call blocks too long | agent times out mid-scrape | Task 9 non-blocking lock + stop_scrape + workers/delay params; document timeout guidance in SKILL.md |
| FastMCP API drift | server fails at import | Pin `mcp>=1.26,<2` in requirements; Task 9 unit test imports at module load |
| Dark-theme contrast fails | unreadable UI | Task 4 computes 4.5:1 contrast before commit |
| `values[2]` regression resurfaces | Copy URL copies followers | Task 1 test + Task 8 regression guard |
| Unsigned installer blocked by SmartScreen | users get warning | Task 3 SIGNING.md documents signtool step for public release |

## Final Gate Checklist (run once, before tag)

- [ ] `pytest tests -q` all green
- [ ] `dist\Reelminner.exe` + `dist\Reelminner-Setup.exe` built fresh
- [ ] Silent install → launch → uninstall verified
- [ ] MCP Inspector: 5 tools, scrape with followers, stop works
- [ ] SKILL.md ↔ registered_tools() match
- [ ] `git tag v1.0.0`
