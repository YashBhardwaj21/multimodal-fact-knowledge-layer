"""Session-partitioned object storage manager."""

import os
import shutil
import hashlib
import io
from pathlib import Path
from typing import Dict, List, Optional, Any, BinaryIO, Union
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ObjectStore:
    """Manages session-partitioned storage for documents and visual artifacts."""

    def __init__(self, base_dir: str = "storage/buckets"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

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
        """Save a PDF file into session object storage."""
        docs_dir = self.get_documents_dir(session_id)
        target_path = docs_dir / filename

        if isinstance(file_obj, bytes):
            file_obj = io.BytesIO(file_obj)

        sha256_hash = hashlib.sha256()
        bytes_written = 0

        with open(target_path, "wb") as f:
            while chunk := file_obj.read(1024 * 1024):
                sha256_hash.update(chunk)
                f.write(chunk)
                bytes_written += len(chunk)

        doc_id = f"doc_{sha256_hash.hexdigest()[:12]}"
        return {
            "doc_id": doc_id,
            "filename": filename,
            "file_path": str(target_path),
            "size_bytes": bytes_written,
            "sha256": sha256_hash.hexdigest(),
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

        with open(fig_path, "wb") as f:
            f.write(image_bytes)

        return str(fig_path)

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
        """Purge storage for a session."""
        session_dir = self.base_dir / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)
            return True
        return False


default_object_store = ObjectStore()
