import hashlib
import io
import json

from minio import Minio

from gov_notice.config import settings

_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=False,
)


def object_key(agency_code: str, source_url: str) -> str:
    """source_url 해시 기반 키 — 같은 공고 재크롤링해도 같은 키라 자연히 멱등."""
    digest = hashlib.sha256(source_url.encode()).hexdigest()
    return f"{agency_code}/{digest}.html"


def put_html(key: str, html: str) -> None:
    data = html.encode("utf-8")
    _client.put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type="text/html; charset=utf-8",
    )


def trace_key(announcement_id: int, profile_label: str) -> str:
    """(announcement_id, profile_label) 조합 기반 키 — 재판별해도 같은 키라 멱등 덮어쓰기."""
    return f"traces/{announcement_id}_{profile_label}.json"


def put_json(key: str, data: object) -> None:
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    _client.put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(body),
        length=len(body),
        content_type="application/json; charset=utf-8",
    )
