import asyncio
from io import BytesIO
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.api.routes.documents import _read_and_rewind_upload
from app.api.routes.health import health_check
from app.core.config import Settings


class SecurityHardeningTests(unittest.TestCase):
    def _upload(self, payload):
        return UploadFile(file=BytesIO(payload), filename="book.pdf", headers=Headers({"content-type": "application/pdf"}))

    def test_upload_rejects_non_pdf_magic_and_oversize_content(self):
        with self.assertRaises(HTTPException) as invalid:
            asyncio.run(_read_and_rewind_upload(self._upload(b"not a pdf")))
        self.assertEqual(invalid.exception.status_code, 415)
        with patch("app.api.routes.documents.settings.MAX_UPLOAD_BYTES", 8):
            with self.assertRaises(HTTPException) as oversized:
                asyncio.run(_read_and_rewind_upload(self._upload(b"%PDF-1.4 too large")))
        self.assertEqual(oversized.exception.status_code, 413)

    def test_health_reports_safe_dependency_statuses(self):
        class BrokenDb:
            async def execute(self, _statement):
                raise RuntimeError("postgres://sensitive-host")

        async def unavailable():
            raise RuntimeError("internal endpoint")

        with patch("app.api.routes.health.llm_service.check_availability", unavailable):
            result = asyncio.run(health_check(BrokenDb()))
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["services"], {"postgres": "unavailable", "ollama": "unavailable"})

    def test_configuration_rejects_wildcard_cookie_cors(self):
        with self.assertRaises(ValueError):
            Settings(CORS_ORIGINS=["*"])
