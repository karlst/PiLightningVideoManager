from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, call

from botocore.exceptions import ClientError

from common.s3_store import (
    S3AccessDeniedError,
    S3ObjectNotFoundError,
    S3Store,
)


def client_error(code: str, message: str = "test") -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        "TestOperation",
    )


class TestS3Store(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.store = S3Store("soloran-picam", client=self.client)

    def test_list_objects_empty(self):
        self.client.list_objects_v2.return_value = {"IsTruncated": False}
        self.assertEqual(self.store.list_objects("unverified/"), [])

    def test_list_objects_returns_metadata(self):
        when = datetime.now(timezone.utc)
        self.client.list_objects_v2.return_value = {
            "IsTruncated": False,
            "Contents": [
                {"Key": "unverified/a.mp4", "Size": 123, "LastModified": when, "ETag": '"abc"'}
            ],
        }
        result = self.store.list_objects("unverified/")
        self.assertEqual(result[0].key, "unverified/a.mp4")
        self.assertEqual(result[0].size, 123)
        self.assertEqual(result[0].etag, "abc")

    def test_list_objects_handles_pagination(self):
        self.client.list_objects_v2.side_effect = [
            {
                "IsTruncated": True,
                "NextContinuationToken": "TOKEN",
                "Contents": [{"Key": "a", "Size": 1}],
            },
            {
                "IsTruncated": False,
                "Contents": [{"Key": "b", "Size": 2}],
            },
        ]
        result = self.store.list_objects("x/")
        self.assertEqual([x.key for x in result], ["a", "b"])
        self.assertEqual(
            self.client.list_objects_v2.call_args_list,
            [
                call(Bucket="soloran-picam", Prefix="x/"),
                call(Bucket="soloran-picam", Prefix="x/", ContinuationToken="TOKEN"),
            ],
        )

    def test_object_exists_true(self):
        self.client.head_object.return_value = {}
        self.assertTrue(self.store.object_exists("a"))

    def test_object_exists_false_on_404(self):
        self.client.head_object.side_effect = client_error("404")
        self.assertFalse(self.store.object_exists("a"))

    def test_object_exists_access_denied_raises(self):
        self.client.head_object.side_effect = client_error("AccessDenied")
        with self.assertRaises(S3AccessDeniedError):
            self.store.object_exists("a")

    def test_upload_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = Path(tmp.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        self.store.upload_file(path, "unverified/a")
        self.client.upload_file.assert_called_once_with(str(path), "soloran-picam", "unverified/a")

    def test_upload_missing_local_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.store.upload_file("missing.file", "a")

    def test_download_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "a.mp4"
            self.store.download_file("a.mp4", path)
            self.client.download_file.assert_called_once_with("soloran-picam", "a.mp4", str(path))
            self.assertTrue(path.parent.exists())

    def test_upload_and_download_bytes(self):
        self.store.upload_bytes(b"abc", "a.json", "application/json")
        self.client.put_object.assert_called_once_with(
            Bucket="soloran-picam", Key="a.json", Body=b"abc", ContentType="application/json"
        )

        body = MagicMock()
        body.read.return_value = b"abc"
        self.client.get_object.return_value = {"Body": body}
        self.assertEqual(self.store.download_bytes("a.json"), b"abc")

    def test_delete_object(self):
        self.store.delete_object("a")
        self.client.delete_object.assert_called_once_with(Bucket="soloran-picam", Key="a")

    def test_delete_access_denied(self):
        self.client.delete_object.side_effect = client_error("AccessDenied")
        with self.assertRaises(S3AccessDeniedError):
            self.store.delete_object("a")

    def test_copy_object(self):
        self.store.copy_object("a", "b")
        self.client.copy_object.assert_called_once_with(
            Bucket="soloran-picam",
            Key="b",
            CopySource={"Bucket": "soloran-picam", "Key": "a"},
        )

    def test_move_copies_verifies_then_deletes(self):
        self.client.head_object.return_value = {}
        self.store.move_object("a", "b")
        self.client.copy_object.assert_called_once()
        self.client.head_object.assert_called_once_with(Bucket="soloran-picam", Key="b")
        self.client.delete_object.assert_called_once_with(Bucket="soloran-picam", Key="a")

    def test_move_does_not_delete_if_copy_fails(self):
        self.client.copy_object.side_effect = client_error("AccessDenied")
        with self.assertRaises(S3AccessDeniedError):
            self.store.move_object("a", "b")
        self.client.delete_object.assert_not_called()

    def test_move_does_not_delete_if_destination_verification_fails(self):
        self.client.head_object.side_effect = client_error("404")
        with self.assertRaises(Exception):
            self.store.move_object("a", "b")
        self.client.delete_object.assert_not_called()

    def test_404_download_maps_to_not_found(self):
        self.client.download_file.side_effect = client_error("404")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(S3ObjectNotFoundError):
                self.store.download_file("missing", Path(tmp) / "x")


if __name__ == "__main__":
    unittest.main()
