import asyncio
from io import BytesIO
import unittest

from fastapi import UploadFile
from starlette.datastructures import Headers

from app.api.routes.documents import _read_and_rewind_upload


class UploadStreamTests(unittest.TestCase):
    def test_read_and_rewind_preserves_full_payload_for_minio(self):
        payload = b"%PDF-1.4\nreal uploaded PDF bytes\n%%EOF"
        upload = UploadFile(
            file=BytesIO(payload),
            filename="chapter.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )

        content_length, stream = asyncio.run(_read_and_rewind_upload(upload))
        uploaded_payload = stream.read(content_length)

        self.assertEqual(content_length, len(payload))
        self.assertEqual(uploaded_payload, payload)
        self.assertEqual(len(uploaded_payload), len(payload))
        self.assertNotEqual(uploaded_payload, b"")
        self.assertEqual(upload.filename, "chapter.pdf")
        self.assertEqual(upload.content_type, "application/pdf")
