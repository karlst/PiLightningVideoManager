"""SSH/SFTP access to one Raspberry Pi Camera Capture installation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import posixpath
import socket
import shlex

import paramiko
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from camera_capture_manager.camera_registry import CameraDefinition


SYSTEM_CONFIG_PATH = "/opt/piCameraCapture/config/system_config.json"
CCM_KEY_NAME = "ccm_ed25519"


@dataclass(frozen=True)
class RemoteCapture:
    stem: str
    mp4_path: str
    json_path: str
    mp4_size: int
    json_size: int
    modified_time: float

    @property
    def total_size(self) -> int:
        return self.mp4_size + self.json_size


@dataclass(frozen=True)
class RemoteInventory:
    capture_root: str
    captures: list[RemoteCapture]
    incomplete_count: int
    free_bytes: int | None


def ccm_private_key_path() -> Path:
    """Return the dedicated private key used only by Camera Capture Manager."""
    return Path.home() / ".ssh" / CCM_KEY_NAME


def ccm_public_key_path() -> Path:
    return Path.home() / ".ssh" / f"{CCM_KEY_NAME}.pub"


def ccm_key_exists() -> bool:
    return ccm_private_key_path().is_file()


def ensure_ccm_key() -> Path:
    """
    Create CCM's dedicated Ed25519 key pair if it does not already exist.

    CCM never creates or modifies the user's generic id_ed25519/id_rsa keys.
    The private key is intentionally unencrypted because CCM must use it
    non-interactively after the user has authorized it on a registered Pi.
    """
    private_path = ccm_private_key_path()
    public_path = ccm_public_key_path()

    private_path.parent.mkdir(parents=True, exist_ok=True)

    if private_path.is_file():
        # Rebuild a missing .pub file from the existing private key.
        if not public_path.is_file():
            key = paramiko.Ed25519Key.from_private_key_file(str(private_path))
            public_path.write_text(
                f"{key.get_name()} {key.get_base64()} camera-capture-manager\n",
                encoding="utf-8",
            )
        return private_path

    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )

    private_path.write_bytes(private_bytes)
    public_path.write_text(
        public_bytes.decode("ascii") + " camera-capture-manager\n",
        encoding="utf-8",
    )

    if os.name != "nt":
        private_path.chmod(0o600)
        public_path.chmod(0o644)

    return private_path


def ccm_public_key_line() -> str:
    """Return the dedicated CCM public key as one authorized_keys line."""
    ensure_ccm_key()
    line = ccm_public_key_path().read_text(encoding="utf-8").strip()
    if not line:
        raise RuntimeError("CCM public key is empty.")
    return line


class PiConnection:
    def __init__(self, camera: CameraDefinition, timeout_seconds: float = 5.0) -> None:
        self.camera = camera
        self.timeout_seconds = timeout_seconds
        self.client: paramiko.SSHClient | None = None
        self.sftp: paramiko.SFTPClient | None = None

    def __enter__(self) -> "PiConnection":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def connect(self, password: str | None = None) -> None:
        """
        Connect to a registered Pi.

        Normal CCM operation uses only ~/.ssh/ccm_ed25519.  A password is
        accepted only for the one-time public-key installation operation.
        """
        self.close()
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        try:
            client.load_host_keys(str(Path.home() / ".ssh" / "known_hosts"))
        except OSError:
            pass

        # Registered cameras are explicit trusted targets.  Persisting host
        # keys is not required for CCM operation, so accept first connection.
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            if password is None:
                key_path = ccm_private_key_path()
                if not key_path.is_file():
                    raise RuntimeError(
                        "CCM SSH access is not set up yet. "
                        "Use 'Set Up SSH Access...' for this camera first."
                    )

                client.connect(
                    hostname=self.camera.ip_address,
                    username=self.camera.ssh_user,
                    key_filename=str(key_path),
                    timeout=self.timeout_seconds,
                    auth_timeout=self.timeout_seconds,
                    banner_timeout=self.timeout_seconds,
                    look_for_keys=False,
                    allow_agent=False,
                )
            else:
                # One-time bootstrap connection. Do not try unrelated desktop
                # SSH identities such as the GitHub or web-publishing keys.
                client.connect(
                    hostname=self.camera.ip_address,
                    username=self.camera.ssh_user,
                    password=password,
                    timeout=self.timeout_seconds,
                    auth_timeout=self.timeout_seconds,
                    banner_timeout=self.timeout_seconds,
                    look_for_keys=False,
                    allow_agent=False,
                )

            sftp = client.open_sftp()
        except RuntimeError:
            client.close()
            raise
        except (paramiko.AuthenticationException, paramiko.SSHException, OSError, socket.error) as error:
            client.close()
            raise RuntimeError(
                f"Unable to connect to {self.camera.name} "
                f"({self.camera.ip_address}): {error}"
            ) from error

        self.client = client
        self.sftp = sftp

    def close(self) -> None:
        if self.sftp is not None:
            try:
                self.sftp.close()
            except OSError:
                pass
            self.sftp = None

        if self.client is not None:
            self.client.close()
            self.client = None

    def test_connection(self) -> str:
        if self.client is None:
            self.connect()
        assert self.client is not None
        stdin, stdout, stderr = self.client.exec_command("hostname")
        del stdin
        host = stdout.read().decode("utf-8", errors="replace").strip()
        error_text = stderr.read().decode("utf-8", errors="replace").strip()
        if error_text and not host:
            raise RuntimeError(error_text)
        return host or self.camera.ip_address

    def read_capture_root(self) -> str:
        if self.sftp is None:
            self.connect()
        assert self.sftp is not None

        try:
            with self.sftp.open(SYSTEM_CONFIG_PATH, "r") as stream:
                raw = stream.read()
        except OSError as error:
            raise RuntimeError(f"Unable to read {SYSTEM_CONFIG_PATH}: {error}") from error

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        try:
            config = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid Pi system config: {error}") from error

        data_root = str(config.get("data_root", "")).strip()
        if not data_root:
            raise RuntimeError(f"Pi system config does not define data_root: {SYSTEM_CONFIG_PATH}")

        return posixpath.join(data_root, "captures")

    def inventory(self) -> RemoteInventory:
        if self.sftp is None:
            self.connect()
        assert self.sftp is not None

        capture_root = self.read_capture_root()
        try:
            attributes = self.sftp.listdir_attr(capture_root)
        except OSError as error:
            raise RuntimeError(f"Unable to list Pi capture folder {capture_root}: {error}") from error

        mp4: dict[str, object] = {}
        sidecars: dict[str, object] = {}

        for attr in attributes:
            name = attr.filename
            lower = name.lower()
            if lower.endswith(".mp4"):
                mp4[name[:-4]] = attr
            elif lower.endswith(".json"):
                sidecars[name[:-5]] = attr

        complete_stems = sorted(set(mp4) & set(sidecars))
        incomplete_count = len(set(mp4) ^ set(sidecars))
        captures: list[RemoteCapture] = []

        for stem in complete_stems:
            mp4_attr = mp4[stem]
            json_attr = sidecars[stem]
            captures.append(
                RemoteCapture(
                    stem=stem,
                    mp4_path=posixpath.join(capture_root, f"{stem}.mp4"),
                    json_path=posixpath.join(capture_root, f"{stem}.json"),
                    mp4_size=int(mp4_attr.st_size),
                    json_size=int(json_attr.st_size),
                    modified_time=max(float(mp4_attr.st_mtime), float(json_attr.st_mtime)),
                )
            )

        free_bytes: int | None = None
        try:
            stats = self.sftp.statvfs(capture_root)
            free_bytes = int(stats.f_bavail * stats.f_frsize)
        except (AttributeError, OSError):
            # Some Raspberry Pi SFTP servers do not advertise statvfs.
            # Fall back to the standard POSIX df command over the same SSH
            # connection so CCM can still report useful free-space data.
            if self.client is not None:
                try:
                    command = f"df -Pk {shlex.quote(capture_root)} | tail -n 1"
                    _stdin, stdout, stderr = self.client.exec_command(command)
                    line = stdout.read().decode("utf-8", errors="replace").strip()
                    error_text = stderr.read().decode("utf-8", errors="replace").strip()
                    fields = line.split()
                    if not error_text and len(fields) >= 4:
                        free_bytes = int(fields[3]) * 1024
                except (OSError, ValueError, paramiko.SSHException):
                    free_bytes = None

        return RemoteInventory(
            capture_root=capture_root,
            captures=captures,
            incomplete_count=incomplete_count,
            free_bytes=free_bytes,
        )

    def download_file(self, remote_path: str, local_path: Path, callback=None) -> None:
        if self.sftp is None:
            self.connect()
        assert self.sftp is not None
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.sftp.get(remote_path, str(local_path), callback=callback)

    def remove_file(self, remote_path: str) -> None:
        if self.sftp is None:
            self.connect()
        assert self.sftp is not None
        self.sftp.remove(remote_path)

    @staticmethod
    def install_public_key(camera: CameraDefinition, password: str) -> None:
        """Install CCM's dedicated public key using one password login."""
        public_line = ccm_public_key_line()
        escaped_public_line = public_line.replace("'", "'\\''")

        connection = PiConnection(camera)
        try:
            connection.connect(password=password)
            assert connection.client is not None

            command = (
                "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; "
                f"grep -qxF '{escaped_public_line}' ~/.ssh/authorized_keys "
                f"|| printf '%s\\n' '{escaped_public_line}' >> ~/.ssh/authorized_keys; "
                "chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys"
            )
            stdin, stdout, stderr = connection.client.exec_command(command)
            del stdin
            stdout.read()
            error_text = stderr.read().decode("utf-8", errors="replace").strip()
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                raise RuntimeError(error_text or "Unable to install CCM SSH public key.")
        finally:
            connection.close()
