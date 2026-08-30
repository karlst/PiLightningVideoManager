"""Per-user Camera Capture Manager settings."""
from __future__ import annotations

from pathlib import Path
import json
import os


def settings_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "CameraCaptureManager" / "settings.json"


class CcmSettings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_path()
        self.host_destination = Path.home()
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        destination = str(raw.get("host_destination", "")).strip() if isinstance(raw, dict) else ""
        if destination:
            candidate = Path(destination).expanduser()
            if candidate.is_dir():
                self.host_destination = candidate

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"host_destination": str(self.host_destination)}
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def set_host_destination(self, destination: Path) -> None:
        self.host_destination = destination
        self.save()
