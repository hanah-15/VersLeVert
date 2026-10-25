import io
import tempfile
from pathlib import Path
from unittest import TestCase, mock

from django.test import TestCase as DjangoTestCase, override_settings
from PIL import Image

from gamification.services.storage import (
    CloudinaryProofStorage,
    LocalProofStorage,
    StorageError,
    StoredFile,
    delete_legacy_file,
)


def jpeg_bytes():
    image = Image.new("RGB", (32, 24), color="green")
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


class LocalProofStorageTests(TestCase):
    def test_round_trip_and_delete_stays_outside_media_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with override_settings(BASE_DIR=base, DEBUG=True):
                storage = LocalProofStorage()
                saved = storage.save(15, jpeg_bytes())
                path = base / "private_proofs" / "15" / f"{saved.public_id.rsplit('/', 1)[-1]}.jpg"

                self.assertTrue(path.is_file())
                self.assertEqual(storage.read(saved), jpeg_bytes())
                storage.delete(saved)
                self.assertFalse(path.exists())

    def test_rejects_malformed_local_public_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(BASE_DIR=Path(temp_dir), DEBUG=True):
                with self.assertRaises(StorageError):
                    LocalProofStorage().read(
                        StoredFile(
                            public_id="unexpected/path",
                            version=None,
                            bytes=0,
                            width=0,
                            height=0,
                        )
                    )

    def test_deletes_legacy_media_and_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir) / "media"
            legacy_file = media_root / "eco_proofs" / "old.jpg"
            legacy_file.parent.mkdir(parents=True)
            legacy_file.write_bytes(b"old")

            with override_settings(MEDIA_ROOT=media_root):
                delete_legacy_file("eco_proofs/old.jpg")
                self.assertFalse(legacy_file.exists())
                with self.assertRaises(StorageError):
                    delete_legacy_file("../outside.jpg")


class CloudinaryProofStorageTests(DjangoTestCase):
    @override_settings(
        PROOF_CLOUDINARY_FOLDER="test/proofs",
        PROOF_UPLOAD_RETRIES=1,
        PROOF_STORAGE_TIMEOUT_SECONDS=7,
    )
    @mock.patch("gamification.services.storage.time.sleep")
    @mock.patch("cloudinary.uploader.upload")
    def test_upload_uses_authenticated_asset_and_retries(self, upload, sleep):
        upload.side_effect = [
            RuntimeError("temporary failure"),
            {
                "public_id": "test/proofs/42/asset",
                "version": 123,
                "bytes": 456,
                "width": 320,
                "height": 240,
                "format": "jpg",
            },
        ]

        result = CloudinaryProofStorage().save(42, b"clean jpeg")

        self.assertEqual(result.public_id, "test/proofs/42/asset")
        self.assertEqual(result.version, 123)
        self.assertEqual(upload.call_count, 2)
        self.assertEqual(upload.call_args.kwargs["type"], "authenticated")
        self.assertEqual(upload.call_args.kwargs["resource_type"], "image")
        self.assertEqual(upload.call_args.kwargs["folder"], "test/proofs/42")
        self.assertEqual(upload.call_args.kwargs["timeout"], 7)
        sleep.assert_called_once_with(1)

    @mock.patch("urllib.request.urlopen")
    @mock.patch("cloudinary.utils.cloudinary_url")
    def test_read_downloads_signed_authenticated_asset(self, cloudinary_url, urlopen):
        cloudinary_url.return_value = ("https://cloudinary.test/private", {})
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"private bytes"
        urlopen.return_value = response
        stored = StoredFile("proof/private-id", 123, 456, 320, 240)

        result = CloudinaryProofStorage().read(stored, width=800)

        self.assertEqual(result, b"private bytes")
        self.assertEqual(cloudinary_url.call_args.kwargs["type"], "authenticated")
        self.assertTrue(cloudinary_url.call_args.kwargs["sign_url"])
        self.assertEqual(cloudinary_url.call_args.kwargs["version"], 123)
        urlopen.assert_called_once()

    @mock.patch("cloudinary.uploader.destroy")
    def test_delete_uses_authenticated_asset(self, destroy):
        CloudinaryProofStorage().delete(StoredFile("proof/private-id", 123, 456, 320, 240))

        destroy.assert_called_once_with(
            "proof/private-id",
            type="authenticated",
            resource_type="image",
            invalidate=True,
        )
