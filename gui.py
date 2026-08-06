"""
Instagram Reel Scraper - Desktop GUI
====================================
A small tkinter app that lets you:
  1. Log in to Instagram once (session cookies are saved locally),
  2. Paste reel URLs (one per line),
  3. Choose how many parallel browser workers you want,
  4. Scrape username / reel URL / music info / likes / comments,
  5. Review results in a table and export to CSV / Excel / JSON.

Run:  python gui.py
"""

from __future__ import annotations

import queue
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:  # crisp rendering on Windows HiDPI displays
    from ctypes import windll

    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

from scraper import (
    DEFAULT_STATE_FILE,
    InstagramReelScraper,
    export_excel,
    export_json,
    normalize_reel_url,
    write_csv,
)

# Design tokens — single source of truth (theme.py). No hardcoded colors below.
from theme import (
    ACCENT,
    ACCENT_HI,
    BG,
    BG_INPUT,
    BG_PANEL,
    BORDER,
    ERROR,
    FG,
    FG_MUTED,
    MONO,
    SUCCESS,
    TITLE,
    UI,
    UI_BOLD,
    WARN,
)

APP_DIR = Path(__file__).resolve().parent
RESULTS_DIR = APP_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

OK_GREEN = SUCCESS
ERR_RED = ERROR
WARN_ORANGE = WARN

# Results table column order. "followers" sits at index 2, so "reel_url"
# is index 3 — always resolve by name, never by hardcoded index.
COLUMN_ORDER = ("idx", "username", "followers", "reel_url", "music", "artist", "likes", "status")


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class ReelScraperApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Instagram Reel Scraper")
        self.geometry("1140x820")
        self.minsize(980, 700)
        self.configure(bg=BG)

        # Thread -> GUI communication (log lines, progress, results)
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._scraper = InstagramReelScraper(log=self._log_from_thread)
        self._running = False
        self._results = []
        self._row_seq = 0

        self._build_style()
        self._build_ui()
        self._refresh_session()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._poll)

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=26, font=MONO,
                        background=BG_PANEL, fieldbackground=BG_PANEL,
                        foreground=FG, bordercolor=BORDER)
        style.configure("Treeview.Heading", font=UI_BOLD,
                        background=BG_PANEL, foreground=FG_MUTED)
        style.map("Treeview.Heading", background=[("active", BG_INPUT)])
        style.map("Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", "#FFFFFF")])
        style.configure("TButton", font=UI, background=BG_INPUT, foreground=FG,
                        bordercolor=BORDER, padding=(10, 5))
        style.map("TButton",
                  background=[("active", ACCENT_HI), ("pressed", ACCENT_HI)],
                  foreground=[("active", "#FFFFFF")])
        style.configure("Accent.TButton", font=UI_BOLD, background=ACCENT,
                        foreground="#FFFFFF", bordercolor=ACCENT, padding=(14, 7))
        style.map("Accent.TButton",
                  background=[("active", ACCENT_HI), ("pressed", ACCENT_HI)],
                  foreground=[("active", "#FFFFFF"), ("disabled", "#64748B")])
        style.configure("TLabel", font=UI, background=BG, foreground=FG)
        style.configure("Muted.TLabel", font=UI, background=BG, foreground=FG_MUTED)
        style.configure("TLabelframe", font=UI, background=BG_PANEL,
                        bordercolor=BORDER, relief=tk.SOLID, borderwidth=1)
        style.configure("TLabelframe.Label", font=UI_BOLD, background=BG_PANEL,
                        foreground=FG)
        style.configure("TEntry", font=MONO, fieldbackground=BG_INPUT,
                        foreground=FG, insertcolor=FG)
        style.configure("TSpinbox", font=UI, fieldbackground=BG_INPUT,
                        foreground=FG, insertcolor=FG)
        style.configure("TCheckbutton", font=UI, background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)],
                  foreground=[("active", FG)])
        style.configure("TProgressbar", troughcolor=BG_INPUT, background=ACCENT,
                        bordercolor=BORDER, thickness=12)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)  # results area expands

        # ---- header (dark panel + accent bar + brand) ----
        header = tk.Frame(self, bg=BG_PANEL, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        tk.Frame(header, bg=ACCENT, width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(
            header, text="Instagram Reel Scraper",
            bg=BG_PANEL, fg=FG, font=TITLE,
        ).pack(side=tk.LEFT, padx=(14, 0))
        tk.Label(
            header, text="reel URL → username / followers / music / likes",
            bg=BG_PANEL, fg=FG_MUTED, font=UI,
        ).pack(side=tk.LEFT, padx=(12, 0), pady=(6, 0))

        # ---- session bar ----
        session = tk.Frame(self, bg=BG_PANEL, height=46)
        session.grid(row=1, column=0, sticky="ew")
        session.grid_propagate(False)
        tk.Label(session, text="Session:", bg=BG_PANEL, fg=FG_MUTED,
                 font=UI_BOLD).pack(side=tk.LEFT, padx=(12, 4), pady=11)
        self.session_lbl = tk.Label(session, text="checking...", bg=BG_PANEL,
                                    fg=FG, font=UI)
        self.session_lbl.pack(side=tk.LEFT, padx=(0, 14), pady=11)
        ttk.Button(
            session, text="Login to Instagram",
            command=self._on_login, cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 4), pady=6)
        ttk.Button(
            session, text="Import cookies file",
            command=self._on_import_cookies, cursor="hand2",
        ).pack(side=tk.LEFT, padx=4, pady=6)
        ttk.Button(
            session, text="Clear session",
            command=self._on_clear_session, cursor="hand2",
        ).pack(side=tk.LEFT, padx=4, pady=6)

        # ---- URLs input ----
        input_frame = ttk.LabelFrame(
            self, text=" Reel URLs (one per line) ", padding=(8, 6)
        )
        input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
        input_frame.columnconfigure(0, weight=1)

        self.urls_text = tk.Text(
            input_frame, height=6, font=MONO,
            bg=BG_INPUT, fg=FG, insertbackground=FG,
            relief=tk.SOLID, borderwidth=1, undo=True,
        )
        self.urls_text.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.urls_text.insert(
            "1.0",
            "https://www.instagram.com/reel/CxXy123AbCd/\n"
            "https://www.instagram.com/reels/DfGh456EfGh/\n",
        )

        btn_col = tk.Frame(input_frame)
        btn_col.grid(row=0, column=1, sticky="ns")
        ttk.Button(
            btn_col, text="Load URLs from file",
            command=self._on_load_urls, cursor="hand2",
        ).pack(fill=tk.X, pady=(0, 4))
        ttk.Button(
            btn_col, text="Clear list",
            command=lambda: self.urls_text.delete("1.0", tk.END),
            cursor="hand2",
        ).pack(fill=tk.X)

        # ---- options ----
        opts = ttk.Frame(self, padding=(10, 0))
        opts.grid(row=3, column=0, sticky="ew")

        ttk.Label(opts, text="Parallel workers (browser windows):").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        self.workers_var = tk.StringVar(value="3")
        ttk.Spinbox(
            opts, from_=1, to=8, width=4, textvariable=self.workers_var
        ).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(opts, text="Delay between reels (s):").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        self.delay_var = tk.StringVar(value="2")
        ttk.Spinbox(
            opts, from_=0, to=15, width=4, textvariable=self.delay_var,
            increment=0.5,
        ).pack(side=tk.LEFT, padx=(0, 16))

        self.headless_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opts, text="Headless (invisible browsers)",
            variable=self.headless_var,
        ).pack(side=tk.LEFT, padx=(0, 16))

        self.auto_save_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts, text="Auto-save CSV when done", variable=self.auto_save_var
        ).pack(side=tk.LEFT, padx=(16, 0))

        self.auto_profiles_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts, text="Auto-scrape profiles (followers)",
            variable=self.auto_profiles_var,
        ).pack(side=tk.LEFT, padx=(16, 0))

        # ---- actions ----
        actions = ttk.Frame(self, padding=(10, 8))
        actions.grid(row=4, column=0, sticky="ew")
        self.start_btn = tk.Button(
            actions, text="Start Scraping", command=self._on_start,
            bg=ACCENT, fg="white", activebackground=ACCENT_HI,
            activeforeground="white", font=("Segoe UI", 11, "bold"),
            padx=20, cursor="hand2",
        )
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = tk.Button(
            actions, text="Stop", command=self._on_stop,
            state=tk.DISABLED, padx=16, cursor="hand2",
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 16))
        self.progress_bar = ttk.Progressbar(actions, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.progress_lbl = ttk.Label(actions, text="0/0", width=8)
        self.progress_lbl.pack(side=tk.LEFT)

        # ---- results ----
        results_frame = ttk.LabelFrame(
            self, text=" Results ", padding=(8, 6)
        )
        results_frame.grid(row=5, column=0, sticky="nsew", padx=10, pady=(0, 6))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)

        cols = COLUMN_ORDER
        self.tree = ttk.Treeview(
            results_frame, columns=cols, show="headings", selectmode="browse"
        )
        headings = {
            "idx": "#", "username": "Username", "followers": "Followers",
            "reel_url": "Reel URL", "music": "Music", "artist": "Artist",
            "likes": "Likes", "status": "Status",
        }
        widths = {
            "idx": 40, "username": 150, "followers": 90, "reel_url": 300,
            "music": 220, "artist": 140, "likes": 80, "status": 130,
        }
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(
                c, width=widths[c],
                anchor=tk.CENTER if c in ("idx", "likes") else tk.W,
                stretch=(c in ("reel_url", "music")),
            )
        self.tree.tag_configure("ok", foreground=OK_GREEN)
        self.tree.tag_configure("err", foreground=ERR_RED)
        self.tree.tag_configure("warn", foreground=WARN_ORANGE)

        vsb = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(results_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<Double-1>", self._on_tree_double)
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        export_bar = tk.Frame(results_frame)
        export_bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.csv_btn = ttk.Button(
            export_bar, text="Save CSV", command=self._on_export_csv,
            state=tk.DISABLED, cursor="hand2",
        )
        self.csv_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.excel_btn = ttk.Button(
            export_bar, text="Save Excel", command=self._on_export_excel,
            state=tk.DISABLED, cursor="hand2",
        )
        self.excel_btn.pack(side=tk.LEFT, padx=4)
        self.json_btn = ttk.Button(
            export_bar, text="Save JSON", command=self._on_export_json,
            state=tk.DISABLED, cursor="hand2",
        )
        self.json_btn.pack(side=tk.LEFT, padx=4)
        self.copy_btn = ttk.Button(
            export_bar, text="Copy table", command=self._on_copy_table,
            state=tk.DISABLED, cursor="hand2",
        )
        self.copy_btn.pack(side=tk.LEFT, padx=4)
        self.saved_lbl = ttk.Label(export_bar, text="", foreground=OK_GREEN)
        self.saved_lbl.pack(side=tk.LEFT, padx=(10, 0))

        # ---- log ----
        log_frame = ttk.LabelFrame(self, text=" Log ", padding=(8, 4))
        log_frame.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=9, font=("Consolas", 9),
            state="disabled", relief=tk.SOLID, borderwidth=1,
            bg=BG_INPUT, fg=FG, insertbackground=FG,
        )
        self.log_text.grid(row=0, column=0, sticky="ew")

        # ---- status bar ----
        status = tk.Frame(self, bg=BG_PANEL, height=26)
        status.grid(row=7, column=0, sticky="ew")
        status.grid_propagate(False)
        self.status_lbl = tk.Label(status, text="Ready", bg=BG_PANEL,
                                   fg=FG_MUTED, font=("Segoe UI", 9))
        self.status_lbl.pack(side=tk.LEFT, padx=12, pady=4)

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #

    def _on_login(self) -> None:
        if self._running:
            messagebox.showinfo("Busy", "Stop the current scrape before logging in.")
            return
        self._append_log(
            "Opening Instagram login in a visible browser window..."
        )
        threading.Thread(target=self._do_login, daemon=True).start()

    def _do_login(self) -> None:
        try:
            username = self._scraper.login()
            self._q.put(("login_ok", username))
        except Exception as e:
            self._q.put(("log", f"[x] Login failed: {e}"))

    def _on_import_cookies(self) -> None:
        path = filedialog.askopenfilename(
            title="Import cookies (Playwright storage_state.json or "
            "EditThisCookie export)",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            if self._scraper.save_cookies_from_file(path):
                self._append_log(f"[OK] Cookies imported from {path}")
                self._refresh_session()
            else:
                messagebox.showerror(
                    "Import failed",
                    "Unrecognized cookie file format.\n\nExpected either:\n"
                    "  - Playwright storage_state JSON ({\"cookies\": [...]})\n"
                    "  - an EditThisCookie extension export (JSON array)",
                )
        except Exception as e:
            messagebox.showerror("Import failed", str(e))

    def _on_clear_session(self) -> None:
        self._scraper.clear_session()
        self._append_log("Session file deleted.")
        self._refresh_session()

    def _on_load_urls(self) -> None:
        path = filedialog.askopenfilename(
            title="Load reel URLs",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
            return
        self.urls_text.delete("1.0", tk.END)
        self.urls_text.insert("1.0", "\n".join(l for l in lines if l.strip()))
        self._append_log(f"[OK] Loaded {len(lines)} line(s) from {path}")

    def _on_start(self) -> None:
        if self._running:
            return
        urls = self._collect_urls()
        if not urls:
            messagebox.showwarning(
                "No URLs",
                "Please paste at least one Instagram reel URL "
                "(https://www.instagram.com/reel/...).",
            )
            return
        if not self._scraper.has_session():
            if not messagebox.askyesno(
                "No session",
                "No saved Instagram session found.\n"
                "You should click 'Login to Instagram' first "
                "(or import a cookies file).\n\nContinue anyway?",
            ):
                return

        self._scraper.headless = bool(self.headless_var.get())
        self._scraper.workers = int(self.workers_var.get())
        self._scraper.delay = float(self.delay_var.get())
        total = len(urls)

        self._results = []
        self._row_seq = 0
        self._clear_tree()
        self.saved_lbl.config(text="")
        self.progress_bar.config(maximum=total, value=0)
        self.progress_lbl.config(text=f"0/{total}")
        self.status_lbl.config(text="Phase 1/2: scraping reels…", fg=FG)
        self._set_running(True)
        self._append_log(f"[>] Starting with {total} URL(s)...")
        threading.Thread(
            target=self._run_scrape, args=(urls,), daemon=True
        ).start()

    def _run_scrape(self, urls) -> None:
        try:
            results = self._scraper.scrape(
                urls,
                progress_cb=lambda done, t: self._q.put(("progress", done, t)),
                row_cb=lambda d: self._q.put(("row", d)),
                with_profiles=bool(self.auto_profiles_var.get()),
            )
            self._q.put(("done", results))
        except Exception as e:
            self._q.put(("log", f"[x] Fatal error: {e}"))
            self._q.put(("done", []))

    def _on_stop(self) -> None:
        self._scraper.stop()
        self._append_log("Stop requested - finishing current reels...")

    def _on_close(self) -> None:
        self._scraper.stop()
        self.destroy()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _collect_urls(self) -> list:
        raw = self.urls_text.get("1.0", tk.END)
        seen, out = set(), []
        for line in raw.splitlines():
            norm = normalize_reel_url(line)
            if norm:
                if norm not in seen:
                    seen.add(norm)
                    out.append(norm)
            else:
                self._append_log(f"  * skipped (not a reel URL): {line.strip()}")
        return out

    def _refresh_session(self) -> None:
        if self._scraper.has_session():
            self.session_lbl.config(
                text="Session saved (cookies present)", foreground=OK_GREEN
            )
        else:
            self.session_lbl.config(
                text="No session - click 'Login to Instagram'",
                foreground=ERR_RED,
            )

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.start_btn.config(
            state=tk.DISABLED if running else tk.NORMAL
        )
        self.stop_btn.config(
            state=tk.NORMAL if running else tk.DISABLED
        )
        self.urls_text.config(state=tk.DISABLED if running else tk.NORMAL)

    def _clear_tree(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)

    def _fill_tree(self, results) -> None:
        self._clear_tree()
        self._row_seq = 0
        for d in results:
            self._add_row(d)

    def _add_row(self, d) -> None:
        """Insert or update one table row.

        reel_url is the stable iid, so the profile phase can live-update the
        followers cell without duplicating rows.
        """
        iid = d.reel_url or f"row{self._row_seq + 1}"
        if self.tree.exists(iid):
            cur = self.tree.item(iid, "values")
            idx = cur[0] if cur else str(self._row_seq + 1)
            self.tree.item(
                iid,
                values=(
                    idx, d.username, d.followers, d.reel_url, d.music_title,
                    d.music_artist, d.likes, d.status,
                ),
            )
            return
        self._row_seq += 1
        if d.status == "ok":
            tag = "ok"
        elif d.status.startswith("error"):
            tag = "err"
        else:
            tag = "warn"
        self.tree.insert(
            "", tk.END, iid=iid,
            values=(
                str(self._row_seq), d.username, d.followers, d.reel_url,
                d.music_title, d.music_artist, d.likes, d.status,
            ),
            tags=(tag,),
        )

    def _on_done(self, results) -> None:
        self._results = results
        self._set_running(False)
        self._fill_tree(results)
        total = int(self.progress_bar["maximum"]) or 1
        self.progress_lbl.config(text=f"{len(results)}/{total}")
        ok_count = sum(1 for r in results if r.status == "ok")
        self.status_lbl.config(
            text=f"Complete — {ok_count}/{len(results)} ok", fg=SUCCESS
        )

        enabled = tk.NORMAL if results else tk.DISABLED
        for btn in (self.csv_btn, self.excel_btn, self.json_btn, self.copy_btn):
            btn.config(state=enabled)

        saved = ""
        if results and self.auto_save_var.get():
            path = RESULTS_DIR / f"reels_{stamp()}.csv"
            try:
                write_csv(results, path)
                saved = f"  -> auto-saved: {path.name}"
                self.saved_lbl.config(text=f"Saved: {path}")
            except Exception as e:
                self._append_log(f"[x] Auto-save failed: {e}")

        self._append_log(f"[OK] Finished: {len(results)} reel(s) scraped.{saved}")

    # ------------------------------------------------------------------ #
    # Tree context actions
    # ------------------------------------------------------------------ #

    def _on_tree_double(self, _event) -> None:
        iid = self.tree.focus()
        if iid:
            self._open_url(iid)

    def _on_tree_right_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Copy reel URL", command=lambda: self._copy_url(iid))
        menu.add_command(
            label="Open in browser", command=lambda: self._open_url(iid)
        )
        menu.add_command(
            label="Copy row (tab-separated)", command=lambda: self._copy_row(iid)
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _row_values(self, iid) -> tuple:
        return self.tree.item(iid, "values")

    def _copy_url(self, iid) -> None:
        values = self._row_values(iid)
        url = values[COLUMN_ORDER.index("reel_url")]
        self.clipboard_clear()
        self.clipboard_append(url)
        self._append_log(f"* Copied URL: {url}")

    def _open_url(self, iid) -> None:
        values = self._row_values(iid)
        webbrowser.open(values[COLUMN_ORDER.index("reel_url")])

    def _copy_row(self, iid) -> None:
        values = self._row_values(iid)
        self.clipboard_clear()
        self.clipboard_append("\t".join(str(v) for v in values))
        self._append_log("* Row copied to clipboard.")

    # ------------------------------------------------------------------ #
    # Exports
    # ------------------------------------------------------------------ #

    def _on_export_csv(self) -> None:
        if not self._results:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"reels_{stamp()}.csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            write_csv(self._results, path)
            self._append_log(f"[OK] CSV saved: {path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _on_export_excel(self) -> None:
        if not self._results:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            initialfile=f"reels_{stamp()}.xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not path:
            return
        try:
            export_excel(self._results, path)
            self._append_log(f"[OK] Excel saved: {path}")
        except ImportError as e:
            messagebox.showwarning(
                "Missing dependency",
                str(e) + "\nCSV / JSON export still work.",
            )
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _on_export_json(self) -> None:
        if not self._results:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=f"reels_{stamp()}.json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        try:
            export_json(self._results, path)
            self._append_log(f"[OK] JSON saved: {path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _on_copy_table(self) -> None:
        if not self._results:
            return
        lines = [
            "\t".join(
                ["#", "username", "reel_url", "music_title",
                 "music_artist", "likes", "status"]
            )
        ]
        for i, d in enumerate(self._results, 1):
            lines.append(
                "\t".join(
                    [str(i), d.username, d.reel_url, d.music_title,
                     d.music_artist, d.likes, d.status]
                )
            )
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self._append_log("[OK] Table copied to clipboard.")

    # ------------------------------------------------------------------ #
    # Logging / polling (thread-safe UI updates)
    # ------------------------------------------------------------------ #

    def _log_from_thread(self, msg: str) -> None:
        self._q.put(("log", msg))

    def _append_log(self, msg: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _poll(self) -> None:
        try:
            while True:
                item = self._q.get_nowait()
                kind = item[0]
                if kind == "log":
                    msg = item[1]
                    self._append_log(msg)
                    if "Auto-scraping profiles" in msg:
                        self.status_lbl.config(text="Phase 2/2: fetching followers…", fg=FG)
                    elif msg.startswith("[OK] Done"):
                        self.status_lbl.config(text="Phase 1/2 complete", fg=SUCCESS)
                elif kind == "progress":
                    done, total = item[1], item[2]
                    self.progress_bar.config(maximum=total, value=done)
                    self.progress_lbl.config(text=f"{done}/{total}")
                elif kind == "login_ok":
                    self._refresh_session()
                    user = item[1] or "unknown"
                    messagebox.showinfo(
                        "Logged in",
                        f"Logged in as @{user}\nSession saved locally to\n"
                        f"{DEFAULT_STATE_FILE.name}",
                    )
                elif kind == "row":
                    self._add_row(item[1])
                elif kind == "done":
                    self._on_done(item[1])
        except queue.Empty:
            pass
        self.after(120, self._poll)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="InstagramReelScraper")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="write a health report to dist/selftest_report.txt (or cwd) and exit without opening the window",
    )
    args = parser.parse_args()
    if args.selftest:
        lines = [
            "SELFTEST OK",
            f"frozen={'yes' if getattr(sys, 'frozen', False) else 'no'}",
            "app=InstagramReelScraper",
        ]
        report = Path("selftest_report.txt")
        try:
            report.write_text("\n".join(lines), encoding="utf-8")
        except OSError:
            report = Path(__file__).resolve().parent / "selftest_report.txt"
            report.write_text("\n".join(lines), encoding="utf-8")
        sys.exit(0)
    app = ReelScraperApp()
    app.mainloop()
