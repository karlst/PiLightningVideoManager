from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common.aws_auth import (
    AwsAuthConfig,
    AwsAuthenticator,
    AwsCredentialFileError,
    AwsProfileNotFoundError,
)


class TestAwsAuthenticator(unittest.TestCase):
    def _write_credentials(self, document) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(document, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def _valid_document(self):
        return {
            "region": "us-west-2",
            "bucket": "soloran-picam",
            "profiles": {
                "picam-manager": {
                    "access_key_id": "ACCESS123",
                    "secret_access_key": "SECRET456",
                }
            },
        }

    def test_missing_credentials_file_raises(self):
        auth = AwsAuthenticator(AwsAuthConfig("picam-manager", Path("does-not-exist.json")))
        with self.assertRaises(AwsCredentialFileError):
            auth.create_session()

    def test_malformed_json_raises(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        tmp.write("{bad json")
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        auth = AwsAuthenticator(AwsAuthConfig("picam-manager", Path(tmp.name)))
        with self.assertRaises(AwsCredentialFileError):
            auth.create_session()

    def test_missing_profile_raises(self):
        path = self._write_credentials(self._valid_document())
        auth = AwsAuthenticator(AwsAuthConfig("picam-ingest", path))
        with self.assertRaises(AwsProfileNotFoundError):
            auth.create_session()

    def test_missing_access_key_raises(self):
        doc = self._valid_document()
        del doc["profiles"]["picam-manager"]["access_key_id"]
        path = self._write_credentials(doc)
        auth = AwsAuthenticator(AwsAuthConfig("picam-manager", path))
        with self.assertRaises(AwsCredentialFileError):
            auth.create_session()

    def test_missing_secret_key_raises(self):
        doc = self._valid_document()
        del doc["profiles"]["picam-manager"]["secret_access_key"]
        path = self._write_credentials(doc)
        auth = AwsAuthenticator(AwsAuthConfig("picam-manager", path))
        with self.assertRaises(AwsCredentialFileError):
            auth.create_session()

    @patch("common.aws_auth.boto3.Session")
    def test_creates_session_with_expected_credentials_and_region(self, session_cls):
        path = self._write_credentials(self._valid_document())
        auth = AwsAuthenticator(AwsAuthConfig("picam-manager", path))
        auth.create_session()
        session_cls.assert_called_once_with(
            aws_access_key_id="ACCESS123",
            aws_secret_access_key="SECRET456",
            region_name="us-west-2",
        )

    @patch("common.aws_auth.boto3.Session")
    def test_region_override_wins(self, session_cls):
        path = self._write_credentials(self._valid_document())
        auth = AwsAuthenticator(AwsAuthConfig("picam-manager", path, region="us-east-1"))
        auth.create_session()
        self.assertEqual(session_cls.call_args.kwargs["region_name"], "us-east-1")

    @patch("common.aws_auth.boto3.Session")
    def test_creates_s3_client(self, session_cls):
        path = self._write_credentials(self._valid_document())
        session = session_cls.return_value
        auth = AwsAuthenticator(AwsAuthConfig("picam-manager", path))
        result = auth.create_s3_client()
        session.client.assert_called_once_with("s3")
        self.assertIs(result, session.client.return_value)


if __name__ == "__main__":
    unittest.main()
