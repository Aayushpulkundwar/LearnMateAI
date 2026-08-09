import io
from typing import BinaryIO
from minio import Minio
from minio.error import S3Error
from app.core.config import settings


class MinioService:
    """Service wrapping MinIO SDK for textbook raw PDF storage."""

    def __init__(self):
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket = settings.MINIO_BUCKET

    def ensure_bucket_exists(self) -> None:
        """Create configured bucket if not already existing."""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error as exc:
            # TODO: Add structured logging for bucket initialization warnings
            print(f"MinIO bucket check warning: {exc}")

    def upload_file(self, object_name: str, file_data: BinaryIO, length: int, content_type: str = "application/pdf") -> str:
        """Upload raw textbook PDF into MinIO bucket and return minio_path."""
        self.ensure_bucket_exists()
        self.client.put_object(
            bucket_name=self.bucket,
            object_name=object_name,
            data=file_data,
            length=length,
            content_type=content_type
        )
        return f"{self.bucket}/{object_name}"

    def download_file(self, object_name: str) -> bytes:
        """Retrieve raw textbook PDF bytes from MinIO for parsing."""
        # Strip bucket prefix if provided
        clean_object_name = object_name.replace(f"{self.bucket}/", "")
        response = self.client.get_object(self.bucket, clean_object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


minio_service = MinioService()
