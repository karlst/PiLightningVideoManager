"""AWS authentication for Pi Camera Capture.

Credential storage is intentionally isolated from S3 logic so the authentication
mechanism can be changed later without changing callers such as PiSide, Vce,
CCM, or the standalone S3 test utility.

Initial credential file format (default: ~/.picam/aws_credentials.json):

{
  "region": "us-west-2",
  "bucket": "soloran-picam",
  "profiles": {
    "picam-ingest": {
      "access_key_id": "...",
      "secret_access_key": "..."
    },
    "picam-manager": {
      "access_key_id": "...",
      "secret_access_key": "..."
    }
  }
}

The bucket entry is deployment configuration and is not used by this module;
it is allowed in the file so one private provisioning file can carry the small
amount of AWS setup information needed by Pi Camera applications.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import boto3


DEFAULT_CREDENTIAL_FILE = Path.home() / ".picam" / "aws_credentials.json"


class AwsAuthError(Exception):
    """Base exception for AWS authentication/configuration failures."""


class AwsCredentialFileError(AwsAuthError):
    """Credential file is missing, unreadable, or malformed."""


class AwsProfileNotFoundError(AwsAuthError):
    """Requested credential profile does not exist."""


@dataclass(frozen=True)
class AwsAuthConfig:
    """Configuration needed to create an authenticated boto3 session."""

    profile_name: str
    credential_file: Path = DEFAULT_CREDENTIAL_FILE
    region: str | None = None


class AwsAuthenticator:
    """Create authenticated boto3 sessions/clients from Pi Camera credentials.

    Callers should depend on this class rather than reading secret keys directly.
    A future implementation can replace the file-based credentials with AWS
    profiles, temporary credentials, Roles Anywhere, or a provisioning service
    without changing S3Store or its callers.
    """

    def __init__(self, config: AwsAuthConfig) -> None:
        self._config = config
        self._document: dict[str, Any] | None = None

    @property
    def profile_name(self) -> str:
        return self._config.profile_name

    @property
    def credential_file(self) -> Path:
        return Path(self._config.credential_file).expanduser()

    @property
    def region(self) -> str:
        if self._config.region:
            return self._config.region

        document = self._load_document()
        region = document.get("region")
        if not isinstance(region, str) or not region.strip():
            raise AwsCredentialFileError(
                f"AWS region is missing from credential file: {self.credential_file}"
            )
        return region.strip()

    def create_session(self) -> boto3.Session:
        """Return an authenticated boto3 Session for the configured profile."""
        profile = self._load_profile()

        return boto3.Session(
            aws_access_key_id=profile["access_key_id"],
            aws_secret_access_key=profile["secret_access_key"],
            region_name=self.region,
        )

    def create_s3_client(self):
        """Return an authenticated low-level boto3 S3 client."""
        return self.create_session().client("s3")

    def _load_document(self) -> dict[str, Any]:
        if self._document is not None:
            return self._document

        path = self.credential_file
        if not path.is_file():
            raise AwsCredentialFileError(f"AWS credential file not found: {path}")

        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise AwsCredentialFileError(
                f"Unable to read AWS credential file: {path}: {exc}"
            ) from exc

        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AwsCredentialFileError(
                f"AWS credential file is not valid JSON: {path}: {exc}"
            ) from exc

        if not isinstance(document, dict):
            raise AwsCredentialFileError(
                f"AWS credential file root must be a JSON object: {path}"
            )

        profiles = document.get("profiles")
        if not isinstance(profiles, dict):
            raise AwsCredentialFileError(
                f"AWS credential file must contain a 'profiles' object: {path}"
            )

        self._document = document
        return document

    def _load_profile(self) -> dict[str, str]:
        document = self._load_document()
        profiles = document["profiles"]
        profile = profiles.get(self.profile_name)

        if not isinstance(profile, dict):
            raise AwsProfileNotFoundError(
                f"AWS profile '{self.profile_name}' not found in {self.credential_file}"
            )

        access_key_id = profile.get("access_key_id")
        secret_access_key = profile.get("secret_access_key")

        if not isinstance(access_key_id, str) or not access_key_id.strip():
            raise AwsCredentialFileError(
                f"Profile '{self.profile_name}' is missing 'access_key_id'"
            )

        if not isinstance(secret_access_key, str) or not secret_access_key.strip():
            raise AwsCredentialFileError(
                f"Profile '{self.profile_name}' is missing 'secret_access_key'"
            )

        return {
            "access_key_id": access_key_id.strip(),
            "secret_access_key": secret_access_key.strip(),
        }
