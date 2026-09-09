"""Session-partitioned object storage manager with pluggable MinIO/S3 and local blob support."""

import os
import shutil
import hashlib
import io
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, BinaryIO, Union
from datetime import datetime
import logging
from PIL import Image

logger = logging.getLogger(__name__)

# Optional MinIO client
try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False


class ObjectStore:
    """Manages session-partitioned object storage for documents and visual artifacts.
    
    Supports local dedicated data storage (data/object_store/) and pluggable MinIO / S3.
    """

    def __init__(
        self,
        base_dir: str = "data/object_store",
        minio_endpoint: Optional[str] = None,
        minio_access_key: Optional[str] = None,
        minio_secret_key: Optional[str] = None,
        minio_bucket: str = "document-intelligence",
        minio_secure: bool = False
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Configure MinIO if environment variables or parameters provided
        self.minio_endpoint = minio_endpoint or os.getenv("MINIO_ENDPOINT")
        self.minio_access_key = minio_access_key or os.getenv("MINIO_ACCESS_KEY")
        self.minio_secret_key = minio_secret_key or os.getenv("MINIO_SECRET_KEY")
        self.minio_bucket = minio_bucket or os.getenv("MINIO_BUCKET", "document-intelligence")
        self.minio_secure = minio_secure or (os.getenv("MINIO_SECURE", "false").lower() == "true")

        self.minio_client: Optional[Any] = None
        if MINIO_AVAILABLE and self.minio_endpoint and self.minio_access_key and self.minio_secret_key:
            try:
                self.minio_client = Minio(
                    self.minio_endpoint,
                    access_key=self.minio_access_key,
                    secret_key=self.minio_secret_key,
                    secure=self.minio_secure
                )
                if not self.minio_client.bucket_exists(self.minio_bucket):
                    self.minio_client.make_bucket(self.minio_bucket)
                logger.info(f"Connected to MinIO object storage at {self.minio_endpoint}, bucket: {self.minio_bucket}")
            except Exception as e:
                logger.warning(f"Could not connect to MinIO ({e}). Falling back to local object storage at {self.base_dir}")
                self.minio_client = None

    def _get_session_dir(self, session_id: str) -> Path:
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def get_documents_dir(self, session_id: str) -> Path:
        path = self._get_session_dir(session_id) / "documents"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_thumbnails_dir(self, session_id: str) -> Path:
        path = self._get_session_dir(session_id) / "thumbnails"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_figures_dir(self, session_id: str) -> Path:
        path = self._get_session_dir(session_id) / "figures"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_tables_dir(self, session_id: str) -> Path:
        path = self._get_session_dir(session_id) / "tables"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_artifacts_dir(self, session_id: str) -> Path:
        path = self._get_session_dir(session_id) / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_document(self, session_id: str, filename: str, file_obj: Union[BinaryIO, bytes]) -> Dict[str, Any]:
        """Save a PDF file into session object storage (local and MinIO)."""
        docs_dir = self.get_documents_dir(session_id)
        target_path = docs_dir / filename

        if isinstance(file_obj, bytes):
            content_bytes = file_obj
        else:
            content_bytes = file_obj.read()

        sha256_hash = hashlib.sha256(content_bytes).hexdigest()
        bytes_written = len(content_bytes)

        with open(target_path, "wb") as f:
            f.write(content_bytes)

        # Upload to MinIO if enabled
        if self.minio_client:
            try:
                object_name = f"{session_id}/documents/{filename}"
                self.minio_client.put_object(
                    bucket_name=self.minio_bucket,
                    object_name=object_name,
                    data=io.BytesIO(content_bytes),
                    length=bytes_written,
                    content_type="application/pdf"
                )
            except Exception as e:
                logger.warning(f"MinIO document upload failed: {e}")

        doc_id = f"doc_{sha256_hash[:12]}"
        return {
            "doc_id": doc_id,
            "filename": filename,
            "file_path": str(target_path),
            "storage_path": f"{session_id}/documents/{filename}",
            "size_bytes": bytes_written,
            "sha256": sha256_hash,
            "stored_at": datetime.now().isoformat()
        }

    def list_session_documents(self, session_id: str) -> List[str]:
        """List filenames of all documents in the session's documents directory."""
        docs_dir = self.get_documents_dir(session_id)
        if not docs_dir.exists():
            return []
        return [f.name for f in docs_dir.iterdir() if f.is_file()]

    def save_page_thumbnail(self, session_id: str, doc_name: str, page_number: int, image_bytes: bytes) -> str:
        """Save a rendered page preview."""
        thumb_dir = self.get_thumbnails_dir(session_id) / Path(doc_name).stem
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"page_{page_number}.png"

        with open(thumb_path, "wb") as f:
            f.write(image_bytes)

        if self.minio_client:
            try:
                object_name = f"{session_id}/thumbnails/{Path(doc_name).stem}/page_{page_number}.png"
                self.minio_client.put_object(
                    bucket_name=self.minio_bucket,
                    object_name=object_name,
                    data=io.BytesIO(image_bytes),
                    length=len(image_bytes),
                    content_type="image/png"
                )
            except Exception as e:
                logger.debug(f"MinIO thumbnail upload skipped: {e}")

        return str(thumb_path)

    def get_page_thumbnail_path(self, session_id: str, doc_name: str, page_number: int) -> Optional[Path]:
        """Retrieve path to a rendered page thumbnail."""
        thumb_path = self.get_thumbnails_dir(session_id) / Path(doc_name).stem / f"page_{page_number}.png"
        return thumb_path if thumb_path.exists() else None

    def save_figure(self, session_id: str, doc_name: str, fig_id: str, image_bytes: bytes) -> str:
        """Save an extracted chart or figure asset."""
        fig_dir = self.get_figures_dir(session_id) / Path(doc_name).stem
        fig_dir.mkdir(parents=True, exist_ok=True)
        fig_path = fig_dir / f"{fig_id}.png"

        # Ensure valid PNG format via Pillow if needed
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                if img.mode in ("CMYK", "P"):
                    img = img.convert("RGB")
                img.save(fig_path, format="PNG")
        except Exception:
            with open(fig_path, "wb") as f:
                f.write(image_bytes)

        if self.minio_client:
            try:
                object_name = f"{session_id}/figures/{Path(doc_name).stem}/{fig_id}.png"
                with open(fig_path, "rb") as f:
                    data = f.read()
                self.minio_client.put_object(
                    bucket_name=self.minio_bucket,
                    object_name=object_name,
                    data=io.BytesIO(data),
                    length=len(data),
                    content_type="image/png"
                )
            except Exception as e:
                logger.debug(f"MinIO figure upload skipped: {e}")

        return str(fig_path)

    def save_figures_meta(self, session_id: str, doc_name: str, figures: List[Dict[str, Any]]) -> None:
        """Save metadata json for figures extracted from a document."""
        fig_dir = self.get_figures_dir(session_id) / Path(doc_name).stem
        fig_dir.mkdir(parents=True, exist_ok=True)
        meta_path = fig_dir / "meta.json"
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(figures, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save figures metadata: {e}")

    def get_figures_meta(self, session_id: str, doc_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve all figure metadata for a session or document."""
        figs_dir = self.get_figures_dir(session_id)
        if not figs_dir.exists():
            return []

        all_meta = []
        if doc_name:
            stems = [Path(doc_name).stem]
        else:
            stems = [d.name for d in figs_dir.iterdir() if d.is_dir()]

        for stem in stems:
            meta_path = figs_dir / stem / "meta.json"
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        if isinstance(meta, list):
                            all_meta.extend(meta)
                except Exception as e:
                    logger.warning(f"Failed to read {meta_path}: {e}")
        return all_meta

    def save_tables_meta(self, session_id: str, doc_name: str, tables: List[Dict[str, Any]]) -> None:
        """Save metadata json for structured tables extracted from a document."""
        tab_dir = self.get_tables_dir(session_id) / Path(doc_name).stem
        tab_dir.mkdir(parents=True, exist_ok=True)
        meta_path = tab_dir / "tables.json"
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(tables, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save tables metadata: {e}")

    def get_tables_meta(self, session_id: str, doc_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve all extracted tables for a session or document."""
        tabs_dir = self.get_tables_dir(session_id)
        if not tabs_dir.exists():
            return []

        all_tables = []
        if doc_name:
            stems = [Path(doc_name).stem]
        else:
            stems = [d.name for d in tabs_dir.iterdir() if d.is_dir()]

        for stem in stems:
            meta_path = tabs_dir / stem / "tables.json"
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        if isinstance(meta, list):
                            all_tables.extend(meta)
                except Exception as e:
                    logger.warning(f"Failed to read {meta_path}: {e}")
        return all_tables

    def delete_document_files(self, session_id: str, doc_name: str) -> bool:
        """Purge all binary assets (PDF, thumbnails, figures, tables) for a specific document."""
        stem = Path(doc_name).stem
        deleted = False

        # 1. Delete original PDF
        pdf_file = self.get_documents_dir(session_id) / doc_name
        if pdf_file.exists():
            try:
                pdf_file.unlink()
                deleted = True
            except Exception as e:
                logger.warning(f"Failed to delete {pdf_file}: {e}")

        # 2. Delete thumbnails folder for this doc
        thumb_dir = self.get_thumbnails_dir(session_id) / stem
        if thumb_dir.exists():
            try:
                shutil.rmtree(thumb_dir)
                deleted = True
            except Exception as e:
                logger.warning(f"Failed to delete {thumb_dir}: {e}")

        # 3. Delete figures folder for this doc
        fig_dir = self.get_figures_dir(session_id) / stem
        if fig_dir.exists():
            try:
                shutil.rmtree(fig_dir)
                deleted = True
            except Exception as e:
                logger.warning(f"Failed to delete {fig_dir}: {e}")

        # 4. Delete tables folder for this doc
        tab_dir = self.get_tables_dir(session_id) / stem
        if tab_dir.exists():
            try:
                shutil.rmtree(tab_dir)
                deleted = True
            except Exception as e:
                logger.warning(f"Failed to delete {tab_dir}: {e}")

        # 5. Delete from MinIO if enabled
        if self.minio_client:
            try:
                prefix = f"{session_id}/"
                for obj in self.minio_client.list_objects(self.minio_bucket, prefix=prefix, recursive=True):
                    if stem in obj.object_name or doc_name in obj.object_name:
                        self.minio_client.remove_object(self.minio_bucket, obj.object_name)
            except Exception as e:
                logger.debug(f"MinIO document cleanup error: {e}")

        logger.info(f"Deleted all object storage files for document '{doc_name}' in session '{session_id}'")
        return deleted

    def get_session_storage_stats(self, session_id: str) -> Dict[str, Any]:
        """Calculate storage utilization for a specific session."""
        session_dir = self.base_dir / session_id
        if not session_dir.exists():
            return {"total_bytes": 0, "file_count": 0, "formatted": "0 MB"}

        total_bytes = 0
        file_count = 0
        for entry in session_dir.rglob("*"):
            if entry.is_file():
                total_bytes += entry.stat().st_size
                file_count += 1

        mb = total_bytes / (1024 * 1024)
        return {
            "session_id": session_id,
            "total_bytes": total_bytes,
            "total_mb": round(mb, 2),
            "file_count": file_count,
            "formatted": f"{mb:.1f} MB" if mb < 1024 else f"{mb/1024:.2f} GB"
        }

    def get_global_storage_stats(self, max_quota_bytes: int = 10 * 1024 * 1024 * 1024) -> Dict[str, Any]:
        """Calculate total storage across all sessions for the storage quota widget."""
        total_bytes = 0
        total_files = 0
        sessions_count = 0

        if self.base_dir.exists():
            for item in self.base_dir.iterdir():
                if item.is_dir():
                    sessions_count += 1
                    for f in item.rglob("*"):
                        if f.is_file():
                            total_bytes += f.stat().st_size
                            total_files += 1

        used_gb = total_bytes / (1024 * 1024 * 1024)
        max_gb = max_quota_bytes / (1024 * 1024 * 1024)
        pct = (total_bytes / max_quota_bytes) * 100 if max_quota_bytes else 0

        return {
            "used_bytes": total_bytes,
            "used_gb": round(used_gb, 2),
            "max_gb": round(max_gb, 1),
            "usage_percentage": min(round(pct, 1), 100.0),
            "display_text": f"{used_gb:.1f} GB of {max_gb:.0f} GB",
            "total_files": total_files,
            "total_sessions": sessions_count
        }

    def delete_session_storage(self, session_id: str) -> bool:
        """Purge all object storage for a session."""
        session_dir = self.base_dir / session_id
        deleted = False
        if session_dir.exists():
            shutil.rmtree(session_dir)
            deleted = True

        if self.minio_client:
            try:
                prefix = f"{session_id}/"
                for obj in self.minio_client.list_objects(self.minio_bucket, prefix=prefix, recursive=True):
                    self.minio_client.remove_object(self.minio_bucket, obj.object_name)
                deleted = True
            except Exception as e:
                logger.debug(f"MinIO session purge error: {e}")

        return deleted


default_object_store = ObjectStore()
