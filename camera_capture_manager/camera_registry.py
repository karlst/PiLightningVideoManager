"""Persistent registry for Raspberry Pi camera hosts used by CCM."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import ipaddress
import json
import os


@dataclass(frozen=True)
class CameraDefinition:
    name: str
    ip_address: str
    ssh_user: str

    def validated(self) -> "CameraDefinition":
        name = self.name.strip()
        user = self.ssh_user.strip()
        ip_text = self.ip_address.strip()

        if not name:
            raise ValueError("Camera name is required.")
        if not user:
            raise ValueError("SSH user is required.")

        try:
            address = ipaddress.ip_address(ip_text)
        except ValueError as error:
            raise ValueError(f"Invalid IP address: {ip_text}") from error

        if address.version != 4:
            raise ValueError("CCM currently expects an IPv4 address.")

        return CameraDefinition(
            name=name,
            ip_address=str(address),
            ssh_user=user,
        )


def registry_path() -> Path:
    """Return a per-user cross-platform location for the CCM registry."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    return base / "CameraCaptureManager" / "cameras.json"


class CameraRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or registry_path()
        self._cameras: list[CameraDefinition] = []
        self.load()

    @property
    def cameras(self) -> list[CameraDefinition]:
        return list(self._cameras)

    def load(self) -> None:
        self._cameras = []

        if not self.path.is_file():
            return

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Unable to read camera registry {self.path}: {error}") from error

        items = raw.get("cameras", []) if isinstance(raw, dict) else []
        if not isinstance(items, list):
            raise RuntimeError(f"Invalid camera registry format: {self.path}")

        cameras: list[CameraDefinition] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                camera = CameraDefinition(
                    name=str(item.get("name", "")),
                    ip_address=str(item.get("ip_address", "")),
                    ssh_user=str(item.get("ssh_user", "")),
                ).validated()
            except ValueError:
                continue
            cameras.append(camera)

        self._cameras = cameras

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "cameras": [asdict(camera) for camera in self._cameras],
        }
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def add(self, camera: CameraDefinition) -> None:
        camera = camera.validated()
        if any(existing.name.casefold() == camera.name.casefold() for existing in self._cameras):
            raise ValueError(f"A camera named '{camera.name}' is already registered.")
        self._cameras.append(camera)
        self._cameras.sort(key=lambda item: item.name.casefold())
        self.save()

    def update(self, old_name: str, camera: CameraDefinition) -> None:
        camera = camera.validated()
        index = self._index_for_name(old_name)

        for offset, existing in enumerate(self._cameras):
            if offset != index and existing.name.casefold() == camera.name.casefold():
                raise ValueError(f"A camera named '{camera.name}' is already registered.")

        self._cameras[index] = camera
        self._cameras.sort(key=lambda item: item.name.casefold())
        self.save()

    def remove(self, name: str) -> None:
        index = self._index_for_name(name)
        del self._cameras[index]
        self.save()

    def _index_for_name(self, name: str) -> int:
        for index, camera in enumerate(self._cameras):
            if camera.name.casefold() == name.casefold():
                return index
        raise ValueError(f"Camera '{name}' is not registered.")
