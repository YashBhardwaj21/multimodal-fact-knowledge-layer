"""Figure, diagram, and chart asset extractor."""

import io
from pathlib import Path
from typing import List, Dict, Any, Optional
import fitz
import logging
from PIL import Image

from src.storage.object_store import ObjectStore, default_object_store

logger = logging.getLogger(__name__)


class FigureExtractor:
    """Extracts graphical figures and chart assets from PDF documents."""

    def __init__(self, object_store: Optional[ObjectStore] = None):
        self.object_store = object_store or default_object_store

    def extract_figures_from_pdf(
        self,
        pdf_path: str,
        session_id: str,
        max_pages: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Extract embedded image assets and save to session object store."""
        doc_path = Path(pdf_path)
        if not doc_path.exists():
            return []

        doc_name = doc_path.name
        figures: List[Dict[str, Any]] = []

        try:
            doc = fitz.open(str(doc_path))
            total_pages = len(doc)
            limit = min(total_pages, max_pages) if max_pages else total_pages

            for page_idx in range(limit):
                page = doc[page_idx]
                page_num = page_idx + 1

                image_list = page.get_images(full=True)
                for img_idx, img_info in enumerate(image_list):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image.get("image")
                    image_ext = base_image.get("ext", "png")
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    if width < 80 or height < 80:
                        continue

                    fig_id = f"fig_p{page_num}_{img_idx + 1}"
                    saved_path = self.object_store.save_figure(
                        session_id=session_id,
                        doc_name=doc_name,
                        fig_id=fig_id,
                        image_bytes=image_bytes
                    )

                    figures.append({
                        "figure_id": fig_id,
                        "document_name": doc_name,
                        "page_number": page_num,
                        "width": width,
                        "height": height,
                        "format": image_ext,
                        "file_path": saved_path,
                        "url": f"/api/sessions/{session_id}/figures/{Path(doc_name).stem}/{fig_id}",
                        "caption": f"Figure on Page {page_num} ({width}x{height}px)"
                    })

            doc.close()
            return figures

        except Exception as e:
            logger.warning(f"Figure extraction error for '{pdf_path}': {e}")
            return []
