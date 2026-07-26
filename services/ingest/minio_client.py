"""MinIO blob upload helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from minio import Minio
from minio.error import S3Error

from paths import CONTEXTMAP_CONFIG

CONFIG_PATH = CONTEXTMAP_CONFIG


def load_minio_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONFIG_PATH
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    cfg = dict(data.get("minio") or {})
    env_secret = os.getenv("MINIO_SECRET_KEY")
    if env_secret:
        cfg["secret_key"] = env_secret
    return cfg


def get_minio_client(config: dict[str, Any] | None = None) -> Minio:
    cfg = config or load_minio_config()
    return Minio(
        cfg["endpoint"],
        access_key=cfg["access_key"],
        secret_key=cfg["secret_key"],
        secure=bool(cfg.get("secure", False)),
    )


def ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def upload_file(
    client: Minio,
    bucket: str,
    object_key: str,
    file_path: Path,
    content_type: str = "application/octet-stream",
) -> str:
    ensure_bucket(client, bucket)
    client.fput_object(bucket, object_key, str(file_path), content_type=content_type)
    return object_key


def delete_prefix(client: Minio, bucket: str, prefix: str) -> int:
    ensure_bucket(client, bucket)
    deleted = 0
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        client.remove_object(bucket, obj.object_name)
        deleted += 1
    return deleted


def object_key_for_unit(
    config: dict[str, Any],
    *,
    asset_uuid: str,
    filename: str,
    modality: str,
) -> str:
    keys = config.get("keys") or {}
    if modality == "pdf":
        template = keys.get("pdf_image", "pdf/{asset_uuid}/{filename}")
    else:
        template = keys.get("video_frame", "video/{asset_uuid}/{filename}")
    return template.format(asset_uuid=asset_uuid, filename=filename)


def guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    return "application/octet-stream"
