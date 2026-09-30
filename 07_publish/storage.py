"""Cloud storage uploader supporting Supabase S3, AWS S3, Cloudflare R2, and mock mode."""

import logging
import mimetypes
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


def get_public_url(object_name: str) -> str:
    """Generate the public URL for an uploaded object."""
    base_url = (config.STORAGE_PUBLIC_BASE_URL or "").rstrip("/")
    if base_url:
        return f"{base_url}/{object_name.lstrip('/')}"
    bucket = config.STORAGE_BUCKET
    endpoint = (config.STORAGE_ENDPOINT_URL or "").rstrip("/")
    return f"{endpoint}/{bucket}/{object_name.lstrip('/')}"


def upload_file(
    file_path: str,
    object_name: Optional[str] = None,
    content_type: Optional[str] = None,
) -> str:
    """
    Upload a local file to configured cloud storage (Supabase S3 / AWS S3 / R2).
    Returns the public URL of the uploaded object.
    """
    path_obj = Path(file_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Local file not found for upload: {file_path}")

    if object_name is None:
        object_name = path_obj.name

    provider = (config.STORAGE_PROVIDER or "mock").lower()

    if provider == "mock" or (config.DRY_RUN_MODE and not config.STORAGE_ACCESS_KEY):
        logger.info(f"[MOCK STORAGE] Uploaded {file_path} as {object_name}")
        return f"https://mock-storage.example.com/{config.STORAGE_BUCKET or 'reels'}/{object_name}"

    import boto3
    from botocore.client import Config

    if not config.STORAGE_ACCESS_KEY or not config.STORAGE_SECRET_KEY:
        raise ValueError("STORAGE_ACCESS_KEY and STORAGE_SECRET_KEY must be set in .env")

    if not config.STORAGE_BUCKET:
        raise ValueError("STORAGE_BUCKET must be set in .env")

    # Detect mime-type
    if not content_type:
        mime, _ = mimetypes.guess_type(str(path_obj))
        content_type = mime or "video/mp4"

    s3_kwargs = {
        "aws_access_key_id": config.STORAGE_ACCESS_KEY,
        "aws_secret_access_key": config.STORAGE_SECRET_KEY,
        "config": Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
    }

    if config.STORAGE_ENDPOINT_URL:
        s3_kwargs["endpoint_url"] = config.STORAGE_ENDPOINT_URL
        s3_kwargs["region_name"] = "us-east-1"

    s3_client = boto3.client("s3", **s3_kwargs)

    logger.info(f"Uploading {file_path} to bucket '{config.STORAGE_BUCKET}' as '{object_name}'...")

    with open(path_obj, "rb") as file_stream:
        s3_client.put_object(
            Bucket=config.STORAGE_BUCKET,
            Key=object_name,
            Body=file_stream,
            ContentType=content_type,
        )

    public_url = get_public_url(object_name)
    logger.info(f"Upload successful. Public URL: {public_url}")
    return public_url
