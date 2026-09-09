"""Multimodal document ingestion and canonical layout parsing."""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
import fitz
import logging

from src.storage.object_store import ObjectStore, default_object_store

logger = logging.getLogger(__name__)


@dataclass
class TextBlock:
    """A layout-aware block of text within a page."""
    id: str
    page_number: int
    text: str
    bbox: List[float]
    block_type: str = "paragraph"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TableObservation:
    """Structured table extracted from a page."""
    id: str
    page_number: int
    headers: List[str]
    rows: List[List[str]]
    row_count: int
    col_count: int
    markdown: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PDFPage:
    """Extracted PDF page with text and layout structures."""

    def __init__(
        self,
        document_name: str,
        page_number: int,
        text: str,
        tables: List[List[List[str]]] = None,
        blocks: List[TextBlock] = None,
        thumbnail_url: Optional[str] = None
    ):
        self.document_name = document_name
        self.page_number = page_number
        self.text = text
        self.tables = tables or []
        self.blocks = blocks or []
        self.thumbnail_url = thumbnail_url

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_name": self.document_name,
            "page_number": self.page_number,
            "text": self.text,
            "char_count": len(self.text),
            "table_count": len(self.tables),
            "block_count": len(self.blocks),
            "thumbnail_url": self.thumbnail_url
        }


@dataclass
class CanonicalDocument:
    """Unified multimodal representation of an ingested document."""
    doc_id: str
    filename: str
    title: str
    total_pages: int
    size_bytes: int
    pages: List[PDFPage] = field(default_factory=list)
    blocks: List[TextBlock] = field(default_factory=list)
    tables: List[TableObservation] = field(default_factory=list)
    figures_count: int = 0
    summary: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "filename": self.filename,
            "title": self.title,
            "total_pages": self.total_pages,
            "size_bytes": self.size_bytes,
            "blocks_count": len(self.blocks),
            "tables_count": len(self.tables),
            "figures_count": self.figures_count,
            "summary": self.summary,
            "tags": self.tags,
            "pages": [p.to_dict() for p in self.pages]
        }


class PDFLoader:
    """PDF parser extracting text, blocks, tables, and thumbnails."""

    def __init__(
        self,
        max_pages_per_doc: Optional[int] = None,
        extract_tables: bool = True,
        object_store: Optional[ObjectStore] = None
    ):
        self.max_pages = max_pages_per_doc
        self.extract_tables = extract_tables
        self.object_store = object_store or default_object_store

    def load_pdf(self, pdf_path: str) -> List[PDFPage]:
        """Extract pages and text blocks from a PDF."""
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc_name = path.name
        pages: List[PDFPage] = []

        try:
            doc = fitz.open(str(path))
            total_pages = len(doc)
            limit = min(total_pages, self.max_pages) if self.max_pages else total_pages

            for page_idx in range(limit):
                page = doc[page_idx]
                page_text = page.get_text("text")

                tables_data = []
                if self.extract_tables:
                    try:
                        tabs = page.find_tables()
                        for t in tabs:
                            extracted = t.extract()
                            if extracted:
                                tables_data.append(extracted)
                    except Exception:
                        pass

                pages.append(
                    PDFPage(
                        document_name=doc_name,
                        page_number=page_idx + 1,
                        text=page_text.strip(),
                        tables=tables_data
                    )
                )

            doc.close()
            return pages

        except Exception as e:
            logger.error(f"Failed to load PDF '{pdf_path}': {e}")
            raise

    def load_canonical_document(
        self,
        pdf_path: str,
        session_id: str,
        render_thumbnails: bool = True
    ) -> CanonicalDocument:
        """Process a PDF into a CanonicalDocument with layout blocks, tables, and thumbnails."""
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc_name = path.name
        doc_id = f"doc_{path.stem.lower()[:20]}"
        file_size = path.stat().st_size

        doc = fitz.open(str(path))
        total_pages = len(doc)
        limit = min(total_pages, self.max_pages) if self.max_pages else total_pages

        pages_list: List[PDFPage] = []
        all_blocks: List[TextBlock] = []
        all_tables: List[TableObservation] = []

        for page_idx in range(limit):
            page = doc[page_idx]
            page_num = page_idx + 1

            thumb_url = None
            if render_thumbnails:
                try:
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                    img_bytes = pix.tobytes("png")
                    self.object_store.save_page_thumbnail(
                        session_id=session_id,
                        doc_name=doc_name,
                        page_number=page_num,
                        image_bytes=img_bytes
                    )
                    thumb_url = f"/api/sessions/{session_id}/documents/{Path(doc_name).stem}/pages/{page_num}/thumbnail"
                except Exception as e:
                    logger.debug(f"Thumbnail render skipped on page {page_num}: {e}")

            page_blocks: List[TextBlock] = []
            raw_blocks = page.get_text("blocks")
            for b_idx, b in enumerate(raw_blocks):
                b_text = b[4].strip()
                if not b_text:
                    continue
                block_type = "heading" if len(b_text) < 80 and b_text.isupper() else "paragraph"
                tb = TextBlock(
                    id=f"{doc_id}_p{page_num}_b{b_idx}",
                    page_number=page_num,
                    text=b_text,
                    bbox=[round(b[0], 1), round(b[1], 1), round(b[2], 1), round(b[3], 1)],
                    block_type=block_type
                )
                page_blocks.append(tb)
                all_blocks.append(tb)

            table_grids = []
            try:
                tabs = page.find_tables()
                for t_idx, t in enumerate(tabs):
                    grid = t.extract()
                    if grid and len(grid) > 1:
                        # Sanitize cells and clean multiple spaces/newlines
                        cleaned_grid = [
                            [re.sub(r'\s+', ' ', str(c or '').replace('\r', ' ').replace('\n', ' ')).strip() for c in r]
                            for r in grid
                        ]
                        num_cols = max(len(r) for r in cleaned_grid)
                        cleaned_grid = [r + [""] * (num_cols - len(r)) for r in cleaned_grid]

                        # Prune columns that are 100% empty across header and all rows
                        valid_col_indices = [
                            c_i for c_i in range(num_cols)
                            if any(len(r[c_i]) > 0 for r in cleaned_grid)
                        ]
                        if len(valid_col_indices) >= 2:
                            cleaned_grid = [[r[c_i] for c_i in valid_col_indices] for r in cleaned_grid]

                        # Prune rows that are completely empty
                        cleaned_grid = [r for r in cleaned_grid if any(len(c) > 0 for c in r)]

                        if len(cleaned_grid) > 1:
                            table_grids.append(cleaned_grid)
                            headers = cleaned_grid[0]
                            rows = cleaned_grid[1:]

                            md_lines = ["| " + " | ".join(headers) + " |"]
                            md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                            for r in rows:
                                md_lines.append("| " + " | ".join(r) + " |")
                            markdown_table = "\n".join(md_lines)

                            all_tables.append(TableObservation(
                                id=f"{doc_id}_p{page_num}_t{t_idx}",
                                page_number=page_num,
                                headers=headers,
                                rows=rows,
                                row_count=len(rows),
                                col_count=len(headers),
                                markdown=markdown_table
                            ))
            except Exception as e:
                logger.debug(f"Table extraction skipped for p.{page_num}: {e}")

            page_text = page.get_text("text").strip()
            pages_list.append(PDFPage(
                document_name=doc_name,
                page_number=page_num,
                text=page_text,
                tables=table_grids,
                blocks=page_blocks,
                thumbnail_url=thumb_url
            ))

        doc.close()

        tags = ["PDF Document"]
        if all_tables:
            tags.append("Structured Tables")
        if total_pages > 1:
            tags.append(f"{total_pages} Pages")

        title = path.stem.replace("-", " ").replace("_", " ").title()

        return CanonicalDocument(
            doc_id=doc_id,
            filename=doc_name,
            title=title,
            total_pages=total_pages,
            size_bytes=file_size,
            pages=pages_list,
            blocks=all_blocks,
            tables=all_tables,
            figures_count=0,
            summary=f"Processed {len(pages_list)} pages with {len(all_blocks)} text blocks and {len(all_tables)} structured tables.",
            tags=tags
        )

    def load_directory(self, dir_path: str, recursive: bool = True) -> Dict[str, List[PDFPage]]:
        path = Path(dir_path)
        pattern = "**/*.pdf" if recursive else "*.pdf"
        pdf_files = sorted(list(path.glob(pattern)))

        results = {}
        for pdf_file in pdf_files:
            results[pdf_file.name] = self.load_pdf(str(pdf_file))

        return results
