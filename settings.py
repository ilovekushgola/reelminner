"""Typed, validated, persistent settings service (Reelminner Phase 3).

Settings are stored as a single JSON blob in the existing key/value settings
table (``JobStore.set_setting("app_settings", ...)``). Categories mirror the
spec: General, Scraping, Storage, Export, MCP, Performance. Defaults reuse the
engine's existing defaults (workers=3, delay=2.0, headless=False, profile
enrichment on).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Optional

from app_events import AppEventKind, ApplicationEventBus
from storage import JobStore, StorageError

SETTINGS_KEY = "app_settings"
VALID_EXPORT_FORMATS = {"csv", "json", "xlsx"}
VALID_MCP_TRANSPORTS = {"stdio", "http", "sse"}

@dataclass
class GeneralSettings:
    default_page_size: int = 50

@dataclass
class ScrapingSettings:
    workers: int = 3
    delay: float = 2.0
    headless: bool = False
    profile_enrichment: bool = True

@dataclass
class StorageSettings:
    results_location: Optional[str] = None

@dataclass
class ExportSettings:
    default_format: str = "csv"

@dataclass
class McpSettings:
    transport: str = "stdio"

@dataclass
class PerformanceSettings:
    """Phase 3.6 — performance monitoring knobs (safe, no side effects)."""
    monitoring_enabled: bool = True
    sampling_interval: float = 5.0
    history_retention_days: int = 30
    max_samples_per_job: int = 100
    process_monitoring_enabled: bool = True
    gpu_monitoring_enabled: bool = False

@dataclass
class Settings:
    general: GeneralSettings = field(default_factory=GeneralSettings)
    scraping: ScrapingSettings = field(default_factory=ScrapingSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    export: ExportSettings = field(default_factory=ExportSettings)
    mcp: McpSettings = field(default_factory=McpSettings)
    performance: PerformanceSettings = field(default_factory=PerformanceSettings)

    def to_dict(self) -> dict:
        return {
            "general": self.general.__dict__,
            "scraping": self.scraping.__dict__,
            "storage": self.storage.__dict__,
            "export": self.export.__dict__,
            "mcp": self.mcp.__dict__,
            "performance": self.performance.__dict__,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        return cls(
            general=GeneralSettings(**data.get("general", {})),
            scraping=ScrapingSettings(**data.get("scraping", {})),
            storage=StorageSettings(**data.get("storage", {})),
            export=ExportSettings(**data.get("export", {})),
            mcp=McpSettings(**data.get("mcp", {})),
            performance=PerformanceSettings(**data.get("performance", {})),
        )

class SettingsService:
    """Typed persistent settings with validation and reset."""

    def __init__(
        self,
        store: JobStore,
        event_bus: Optional[ApplicationEventBus] = None,
    ) -> None:
        self._store = store
        self._bus = event_bus or ApplicationEventBus()
        self._settings = self._load()

    # ------------------------------------------------------------------ #
    # load / persist
    # ------------------------------------------------------------------ #
    def _load(self) -> Settings:
        data = self._store.get_setting(SETTINGS_KEY)
        if isinstance(data, dict) and data:
            try:
                return Settings.from_dict(data)
            except Exception:
                pass
        return Settings()

    def _persist(self) -> None:
        self._store.set_setting(SETTINGS_KEY, self._settings.to_dict())

    # ------------------------------------------------------------------ #
    # access
    # ------------------------------------------------------------------ #
    def get(self) -> Settings:
        return self._settings

    def get_all(self) -> Settings:
        """Return the current settings object (alias used by the MCP layer)."""
        return self._settings

    def get_section(self, name: str):
        return getattr(self._settings, name, None)

    # ------------------------------------------------------------------ #
    # update / reset
    # ------------------------------------------------------------------ #
    def update(self, **kwargs: Any) -> Settings:
        """Update settings from flat keys like ``scraping_workers=5``.

        Raises ``ValueError`` (with a joined message) if validation fails; the
        previous settings are left unchanged in that case.
        """
        updated = Settings.from_dict(self._settings.to_dict())
        for key, value in kwargs.items():
            section, _, attr = key.partition("_")
            section_obj = getattr(updated, section, None)
            if section_obj is None or not hasattr(section_obj, attr):
                raise ValueError(f"Unknown setting: {key}")
            setattr(section_obj, attr, value)

        errors = self.validate(updated)
        if errors:
            raise ValueError("; ".join(errors))
        self._settings = updated
        self._persist()
        self._bus.emit_app(
            AppEventKind.SETTINGS_UPDATED, None, {"keys": list(kwargs.keys())}
        )
        return self._settings

    def update_bulk(self, data: dict) -> Settings:
        """Update from a nested dict like ``{"scraping": {"workers": 5}}``.

        Flattens to the flat key format used by :meth:`update`
        (``scraping_workers=5``) so validation flows through the single path.
        """
        flat: dict[str, Any] = {}
        for section, fields in (data or {}).items():
            if not isinstance(fields, dict):
                raise ValueError(f"settings section '{section}' must be a dict")
            for attr, value in fields.items():
                flat[f"{section}_{attr}"] = value
        return self.update(**flat)

    def reset(self) -> Settings:
        self._settings = Settings()
        self._persist()
        self._bus.emit_app(AppEventKind.SETTINGS_UPDATED, None, {"reset": True})
        return self._settings

    # ------------------------------------------------------------------ #
    # validation
    # ------------------------------------------------------------------ #
    def validate(self, settings: Settings) -> list[str]:
        errors: list[str] = []
        g, s, st, ex, m, p = (
            settings.general,
            settings.scraping,
            settings.storage,
            settings.export,
            settings.mcp,
            settings.performance,
        )
        if not (isinstance(g.default_page_size, int) and 1 <= g.default_page_size <= 500):
            errors.append("general.default_page_size must be an int 1..500")
        if not (isinstance(s.workers, int) and 1 <= s.workers <= 32):
            errors.append("scraping.workers must be an int 1..32")
        if not (isinstance(s.delay, (int, float)) and 0 <= float(s.delay) <= 120):
            errors.append("scraping.delay must be a number 0..120")
        if not isinstance(s.headless, bool):
            errors.append("scraping.headless must be a bool")
        if not isinstance(s.profile_enrichment, bool):
            errors.append("scraping.profile_enrichment must be a bool")
        if ex.default_format not in VALID_EXPORT_FORMATS:
            errors.append(
                f"export.default_format must be one of {sorted(VALID_EXPORT_FORMATS)}"
            )
        if st.results_location is not None and not isinstance(st.results_location, str):
            errors.append("storage.results_location must be a string or None")
        if m.transport not in VALID_MCP_TRANSPORTS:
            errors.append(
                f"mcp.transport must be one of {sorted(VALID_MCP_TRANSPORTS)}"
            )
        if not isinstance(p.monitoring_enabled, bool):
            errors.append("performance.monitoring_enabled must be a bool")
        if not (isinstance(p.sampling_interval, (int, float)) and 1.0 <= float(p.sampling_interval) <= 60.0):
            errors.append("performance.sampling_interval must be a number 1.0..60.0")
        if not (isinstance(p.history_retention_days, int) and 1 <= p.history_retention_days <= 365):
            errors.append("performance.history_retention_days must be an int 1..365")
        if not (isinstance(p.max_samples_per_job, int) and 10 <= p.max_samples_per_job <= 1000):
            errors.append("performance.max_samples_per_job must be an int 10..1000")
        if not isinstance(p.process_monitoring_enabled, bool):
            errors.append("performance.process_monitoring_enabled must be a bool")
        if not isinstance(p.gpu_monitoring_enabled, bool):
            errors.append("performance.gpu_monitoring_enabled must be a bool")
        return errors
