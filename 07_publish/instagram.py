"""Instagram Graph API integration for publishing Reels."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

import config
from .storage import upload_file

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
BASE_GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Retry transient connection failures at the transport level.
_HTTP_RETRIES = 3


def _make_client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        transport=httpx.AsyncHTTPTransport(retries=_HTTP_RETRIES),
    )


async def create_reel_container(
    video_url: str,
    caption: str,
    cover_url: Optional[str] = None,
) -> str:
    """
    Step 1: Create an Instagram Reel container from a public video URL.
    Returns the container ID (creation_id).
    """
    ig_user_id = config.IG_USER_ID
    access_token = config.IG_ACCESS_TOKEN

    if not ig_user_id or not access_token:
        raise ValueError("IG_USER_ID and IG_ACCESS_TOKEN must be configured in .env")

    endpoint = f"{BASE_GRAPH_URL}/{ig_user_id}/media"
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": access_token,
    }
    if cover_url:
        payload["cover_url"] = cover_url

    async with _make_client(45.0) as client:
        response = await client.post(endpoint, data=payload)
        data = response.json()

        if response.status_code != 200 or "id" not in data:
            error_msg = data.get("error", {}).get("message", response.text)
            logger.error(f"Failed to create Reel container: {error_msg}")
            raise RuntimeError(f"Instagram Container Creation Error: {error_msg}")

        container_id = data["id"]
        logger.info(f"Created Instagram Reel container: {container_id}")
        return container_id


async def wait_for_container_status(
    container_id: str,
    timeout_sec: int = 180,
    poll_interval: int = 5,
) -> Dict[str, Any]:
    """
    Step 2: Poll container status until Meta finishes downloading and transcoding the video.
    Status codes: FINISHED, IN_PROGRESS, ERROR, EXPIRED.
    """
    access_token = config.IG_ACCESS_TOKEN
    endpoint = f"{BASE_GRAPH_URL}/{container_id}"
    params = {
        "fields": "status_code,status",
        "access_token": access_token,
    }

    start_time = time.monotonic()
    async with _make_client(30.0) as client:
        while (time.monotonic() - start_time) < timeout_sec:
            response = await client.get(endpoint, params=params)
            data = response.json()

            if response.status_code != 200:
                error_msg = data.get("error", {}).get("message", response.text)
                raise RuntimeError(f"Failed to check container status: {error_msg}")

            status_code = data.get("status_code", "").upper()
            logger.info(f"Reel Container {container_id} status: {status_code}")

            if status_code == "FINISHED":
                return data
            elif status_code in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Instagram container processing failed with status: {status_code} ({data.get('status', '')})")

            await asyncio.sleep(poll_interval)

    raise TimeoutError(f"Timed out waiting for Instagram Reel container {container_id} to finish processing after {timeout_sec}s.")


async def publish_reel_container(container_id: str) -> str:
    """
    Step 3: Publish the ready Reel container to the user's feed.
    Returns the published media ID.
    """
    ig_user_id = config.IG_USER_ID
    access_token = config.IG_ACCESS_TOKEN

    endpoint = f"{BASE_GRAPH_URL}/{ig_user_id}/media_publish"
    payload = {
        "creation_id": container_id,
        "access_token": access_token,
    }

    async with _make_client(45.0) as client:
        response = await client.post(endpoint, data=payload)
        data = response.json()

        if response.status_code != 200 or "id" not in data:
            error_msg = data.get("error", {}).get("message", response.text)
            logger.error(f"Failed to publish Reel: {error_msg}")
            raise RuntimeError(f"Instagram Publish Error: {error_msg}")

        media_id = data["id"]
        logger.info(f"Reel successfully published! Media ID: {media_id}")
        return media_id


async def get_media_permalink(media_id: str) -> Optional[str]:
    """Fetch direct Instagram URL / permalink for a published media ID."""
    access_token = config.IG_ACCESS_TOKEN
    endpoint = f"{BASE_GRAPH_URL}/{media_id}"
    params = {
        "fields": "permalink,shortcode",
        "access_token": access_token,
    }

    try:
        async with _make_client(20.0) as client:
            response = await client.get(endpoint, params=params)
            if response.status_code == 200:
                data = response.json()
                return data.get("permalink")
    except Exception as e:
        logger.warning(f"Could not retrieve permalink for media {media_id}: {e}")
    return None


async def publish_reel_pipeline(
    video_path: str,
    caption: str,
    job_id: Optional[str] = None,
    cover_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full automated pipeline:
    1. Upload local video (and optional cover) to cloud storage bucket
    2. Create Reel container via Graph API
    3. Poll until container transcoding is FINISHED
    4. Publish Reel
    5. Return public URL and Instagram post link
    """
    if config.DRY_RUN_MODE and (not config.IG_ACCESS_TOKEN or not config.STORAGE_ACCESS_KEY):
        logger.info("[DRY RUN] Simulating Instagram Reel Publishing pipeline...")
        return {
            "status": "dry_run_success",
            "public_url": f"https://mock-storage.example.com/reels/{job_id or 'job'}_reel.mp4",
            "container_id": "mock_container_12345",
            "media_id": "mock_media_67890",
            "permalink": "https://www.instagram.com/reel/mock_preview/",
        }

    # 1. Upload to storage
    object_name = f"reels/{job_id}/reel.mp4" if job_id else f"reels/reel_{int(time.time())}.mp4"
    public_url = upload_file(video_path, object_name=object_name)

    # 1b. Upload the cover image (used as the Reel thumbnail in the feed).
    cover_url: Optional[str] = None
    if cover_path and Path(cover_path).exists():
        cover_object = (
            f"reels/{job_id}/cover.jpg"
            if job_id
            else f"reels/cover_{int(time.time())}.jpg"
        )
        try:
            cover_url = upload_file(cover_path, object_name=cover_object)
        except Exception:
            logger.exception("Cover upload failed; publishing without a custom cover.")

    # 2. Create container
    container_id = await create_reel_container(
        video_url=public_url, caption=caption, cover_url=cover_url
    )

    # 3. Poll status
    await wait_for_container_status(container_id)

    # 4. Publish container
    media_id = await publish_reel_container(container_id)

    # 5. Get permalink
    permalink = await get_media_permalink(media_id)

    return {
        "status": "success",
        "public_url": public_url,
        "cover_url": cover_url,
        "container_id": container_id,
        "media_id": media_id,
        "permalink": permalink or f"https://www.instagram.com/p/{media_id}",
    }
