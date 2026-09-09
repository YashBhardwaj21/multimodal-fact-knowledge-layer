"""Figure, diagram, and chart asset extractor with hybrid vector and raster support."""

import io
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import fitz
import logging
from PIL import Image

from src.storage.object_store import ObjectStore, default_object_store

logger = logging.getLogger(__name__)


class FigureExtractor:
    """Extracts graphical figures, vector charts, and raster image assets from PDF documents."""

    def __init__(self, object_store: Optional[ObjectStore] = None):
        self.object_store = object_store or default_object_store

    def extract_figures_from_pdf(
        self,
        pdf_path: str,
        session_id: str,
        max_pages: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Extract embedded images and render vector charts to session object store."""
        doc_path = Path(pdf_path)
        if not doc_path.exists():
            return []

        doc_name = doc_path.name
        doc_stem = doc_path.stem
        figures: List[Dict[str, Any]] = []

        try:
            doc = fitz.open(str(doc_path))
            total_pages = len(doc)
            limit = min(total_pages, max_pages) if max_pages else total_pages

            for page_idx in range(limit):
                page = doc[page_idx]
                page_num = page_idx + 1

                # 1. Detect and render Vector Charts & Diagrams
                blocks = page.get_text("blocks")
                drawings = page.get_drawings()
                chart_boxes = []

                for b in blocks:
                    text = b[4].strip()
                    m = re.match(
                        r'^(Chart|Figure|Fig\.|Exhibit)\s+([I|V|X|\d]+[\.\d\w\s-]*):?\s*(.*)',
                        text,
                        re.IGNORECASE
                    )
                    if m:
                        caption = text.split("\n")[0].strip()
                        cap_rect = fitz.Rect(b[:4])

                        # Drawings in proximity to caption
                        chart_drawings = [
                            d["rect"] for d in drawings
                            if d["rect"].y1 > cap_rect.y0 - 20 and d["rect"].y0 < cap_rect.y1 + 480
                        ]

                        if chart_drawings:
                            box = fitz.Rect(cap_rect)
                            for dr in chart_drawings:
                                box.include_rect(dr)

                            # Include nearby source/note text blocks at bottom of chart
                            for ob in blocks:
                                ob_rect = fitz.Rect(ob[:4])
                                if ob_rect.y0 >= cap_rect.y1 and ob_rect.y1 <= box.y1 + 45 and ob_rect.y0 < box.y1 + 25:
                                    if any(k in ob[4].lower() for k in ["source:", "note:", "source :", "note :"]):
                                        box.include_rect(ob_rect)

                            # Apply padding
                            box.x0 = max(0, box.x0 - 6)
                            box.y0 = max(0, cap_rect.y0 - 6)
                            box.x1 = min(page.rect.x1, box.x1 + 6)
                            box.y1 = min(page.rect.y1, box.y1 + 8)

                            if box.width >= 100 and box.height >= 70:
                                # Avoid duplicate or heavily overlapping chart boxes
                                is_dup = False
                                for existing in chart_boxes:
                                    if box.intersects(existing) and box.intersect(existing).get_area() > 0.4 * box.get_area():
                                        is_dup = True
                                        break

                                if not is_dup:
                                    chart_boxes.append(box)
                                    pix = page.get_pixmap(clip=box, dpi=150)
                                    png_bytes = pix.tobytes("png")
                                    fig_idx = len(figures) + 1
                                    fig_id = f"fig_p{page_num}_chart_{fig_idx}"

                                    saved_path = self.object_store.save_figure(
                                        session_id=session_id,
                                        doc_name=doc_name,
                                        fig_id=fig_id,
                                        image_bytes=png_bytes
                                    )

                                    figures.append({
                                        "figure_id": fig_id,
                                        "document_name": doc_name,
                                        "document": doc_stem,
                                        "page_number": page_num,
                                        "type": "chart",
                                        "width": pix.width,
                                        "height": pix.height,
                                        "format": "png",
                                        "file_path": saved_path,
                                        "url": f"/api/sessions/{session_id}/figures/{doc_stem}/{fig_id}",
                                        "caption": caption
                                    })

                # 2. Extract Embedded Raster Images
                image_list = page.get_images(full=True)
                for img_idx, img_info in enumerate(image_list):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    raw_bytes = base_image.get("image")
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Filter out tiny icon / 1-px spacer elements
                    if (width < 40 or height < 40) or (width * height < 2000):
                        continue

                    fig_idx = len(figures) + 1
                    fig_id = f"fig_p{page_num}_img_{fig_idx}"

                    # Normalize color space and format to RGB PNG via Pillow
                    try:
                        with Image.open(io.BytesIO(raw_bytes)) as pil_img:
                            if pil_img.mode in ("CMYK", "P", "LA"):
                                pil_img = pil_img.convert("RGB")
                            buf = io.BytesIO()
                            pil_img.save(buf, format="PNG")
                            png_bytes = buf.getvalue()
                    except Exception:
                        png_bytes = raw_bytes

                    saved_path = self.object_store.save_figure(
                        session_id=session_id,
                        doc_name=doc_name,
                        fig_id=fig_id,
                        image_bytes=png_bytes
                    )

                    figures.append({
                        "figure_id": fig_id,
                        "document_name": doc_name,
                        "document": doc_stem,
                        "page_number": page_num,
                        "type": "image",
                        "width": width,
                        "height": height,
                        "format": "png",
                        "file_path": saved_path,
                        "url": f"/api/sessions/{session_id}/figures/{doc_stem}/{fig_id}",
                        "caption": f"Embedded Visual on Page {page_num} ({width}x{height}px)"
                    })

            doc.close()

            # Save full metadata manifest to object store
            self.object_store.save_figures_meta(session_id, doc_name, figures)
            return figures

        except Exception as e:
            logger.warning(f"Figure extraction error for '{pdf_path}': {e}")
            return []
