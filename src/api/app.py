"""Document Intelligence REST API and Web Server."""

import os
import io
import shutil
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.storage.object_store import default_object_store
from src.sessions.session_manager import default_session_manager, WorkspaceSession
from src.ingestion.pdf_loader import PDFLoader
from src.ingestion.figure_extractor import FigureExtractor
from src.facts.extractor import FactExtractor
from src.reconciliation.engine import ReconciliationEngine
from src.facts.models import KnowledgeLayer, RelationshipType
from src.rag.vector_store import SessionVectorStore
from src.rag.chat_engine import ChatEngine

app = FastAPI(
    title="Document Intelligence API",
    description="Cross-document fact extraction, evidence grounding, and chat-wise reconciliation platform.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

object_store = default_object_store
session_manager = default_session_manager
pdf_loader = PDFLoader(object_store=object_store)
figure_extractor = FigureExtractor(object_store=object_store)
fact_extractor = FactExtractor()
reconciler = ReconciliationEngine()
chat_engine = ChatEngine()

SESSION_VECTOR_STORES: Dict[str, SessionVectorStore] = {}
SESSION_CANONICAL_DOCS: Dict[str, Dict[str, Any]] = {}


def get_session_vector_store(session_id: str) -> SessionVectorStore:
    if session_id not in SESSION_VECTOR_STORES:
        SESSION_VECTOR_STORES[session_id] = SessionVectorStore(session_id)
    return SESSION_VECTOR_STORES[session_id]




class CreateSessionRequest(BaseModel):
    title: str
    description: Optional[str] = ""


class ChatQueryRequest(BaseModel):
    query: str
    document_name: Optional[str] = None
    doc_id: Optional[str] = None


@app.get("/api/sessions")
def list_sessions():
    """List all chat workspaces."""
    return session_manager.list_sessions()


@app.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    """Create a new isolated workspace."""
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="Workspace title cannot be empty")
    new_session = session_manager.create_session(title=req.title, description=req.description)
    return new_session.to_dict()


@app.get("/api/sessions/{session_id}")
def get_session_details(session_id: str):
    """Get workspace details and metadata."""
    session = session_manager.get_session(session_id, include_knowledge=True)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found")
    data = session.to_dict(include_knowledge=True)
    data["storage"] = object_store.get_session_storage_stats(session_id)
    return data


class RenameSessionRequest(BaseModel):
    title: str


@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, req: RenameSessionRequest):
    """Rename an existing workspace session."""
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    success = session_manager.rename_session(session_id, req.title)
    if not success:
        raise HTTPException(status_code=404, detail="Workspace session not found")
    return {"message": "Workspace renamed", "id": session_id, "title": req.title.strip()}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    """Delete a workspace and purge its isolated storage."""
    success = session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workspace session not found")
    if session_id in SESSION_VECTOR_STORES:
        del SESSION_VECTOR_STORES[session_id]
    if session_id in SESSION_CANONICAL_DOCS:
        del SESSION_CANONICAL_DOCS[session_id]
    return {"message": f"Workspace {session_id} and storage purged successfully"}


@app.post("/api/sessions/{session_id}/documents")
async def upload_document(session_id: str, file: UploadFile = File(...)):
    """Upload and process a PDF document into session storage."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    saved_info = object_store.save_document(session_id, file.filename, file.file)
    pdf_path = saved_info["file_path"]

    try:
        canonical_doc = pdf_loader.load_canonical_document(
            pdf_path=pdf_path,
            session_id=session_id,
            render_thumbnails=True
        )

        figures = figure_extractor.extract_figures_from_pdf(
            pdf_path=pdf_path,
            session_id=session_id,
            max_pages=None
        )
        canonical_doc.figures_count = len(figures)

        new_facts = fact_extractor.extract_from_pages(canonical_doc.pages)

        vstore = get_session_vector_store(session_id)
        vstore.add_blocks(
            doc_name=file.filename,
            blocks=[b.to_dict() for b in canonical_doc.blocks]
        )

        doc_entry = {
            "doc_id": canonical_doc.doc_id,
            "filename": file.filename,
            "title": canonical_doc.title,
            "pages_count": canonical_doc.total_pages,
            "blocks_count": len(canonical_doc.blocks),
            "tables_count": len(canonical_doc.tables),
            "figures_count": canonical_doc.figures_count,
            "summary": canonical_doc.summary,
            "tags": canonical_doc.tags,
            "status": "Processed",
            "processed_time": "Just now",
            "size_bytes": saved_info["size_bytes"]
        }
        session.documents.append(doc_entry)

        if session_id not in SESSION_CANONICAL_DOCS:
            SESSION_CANONICAL_DOCS[session_id] = {}
        SESSION_CANONICAL_DOCS[session_id][file.filename] = canonical_doc

        all_session_facts = session.knowledge_layer.facts + new_facts
        all_session_docs = sorted(list(set([d["filename"] for d in session.documents])))
        session.knowledge_layer = reconciler.reconcile(all_session_facts, all_session_docs)

        # Persist document, pages, facts, and relationships into SQLite database
        session_manager.add_document(
            session_id=session_id,
            doc_entry=doc_entry,
            pages=canonical_doc.pages,
            facts=new_facts,
            comparisons=session.knowledge_layer.comparisons
        )
        session_manager.save_knowledge_layer(session_id, session.knowledge_layer)

        return {
            "message": f"Successfully processed '{file.filename}'",
            "doc_id": canonical_doc.doc_id,
            "pages": canonical_doc.total_pages,
            "blocks": len(canonical_doc.blocks),
            "tables": len(canonical_doc.tables),
            "figures": canonical_doc.figures_count,
            "new_facts": len(new_facts),
            "total_session_facts": len(session.knowledge_layer.facts),
            "total_comparisons": len(session.knowledge_layer.comparisons)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


@app.get("/api/sessions/{session_id}/documents")
def list_session_documents(session_id: str):
    """List all documents in the session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found")
    return session.documents


@app.delete("/api/sessions/{session_id}/documents/{doc_id}")
def delete_session_document(session_id: str, doc_id: str):
    """Delete a document from a workspace, database, object store, and vector store."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found")

    # Find matching document to get filename
    target_doc = next((d for d in session.documents if d.get("id") == doc_id or d.get("doc_id") == doc_id or d.get("filename") == doc_id), None)
    doc_filename = target_doc.get("filename") if target_doc else doc_id

    # Purge vectors
    try:
        vstore = get_session_vector_store(session_id)
        vstore.delete_document(doc_filename)
    except Exception as e:
        logger.warning(f"Error purging vectors for {doc_filename}: {e}")

    # Remove from canonical cache
    if session_id in SESSION_CANONICAL_DOCS:
        SESSION_CANONICAL_DOCS[session_id].pop(doc_filename, None)

    # Purge from SQLite and Object Store
    success = session_manager.delete_document(session_id, doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": f"Document {doc_id} deleted successfully"}


@app.get("/api/sessions/{session_id}/documents/{doc_stem}/pages/{page_num}/thumbnail")
def get_page_thumbnail(session_id: str, doc_stem: str, page_num: int):
    """Serve a page preview thumbnail image."""
    thumb_path = object_store.get_page_thumbnail_path(session_id, doc_stem, page_num)
    if thumb_path and thumb_path.exists():
        return FileResponse(str(thumb_path), media_type="image/png")
    return JSONResponse(status_code=404, content={"detail": "Thumbnail not found"})


@app.get("/api/sessions/{session_id}/figures/{doc_stem}/{fig_id}")
def get_figure_image(session_id: str, doc_stem: str, fig_id: str):
    """Serve an extracted figure image."""
    fig_path = object_store.get_figures_dir(session_id) / doc_stem / f"{fig_id}.png"
    if fig_path.exists():
        return FileResponse(str(fig_path), media_type="image/png")
    return JSONResponse(status_code=404, content={"detail": "Figure not found"})


@app.get("/api/sessions/{session_id}/facts")
def get_session_facts(session_id: str, subject: Optional[str] = None):
    """Retrieve grounded facts extracted from documents in this session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found")
    facts = session.knowledge_layer.facts
    if subject:
        facts = [f for f in facts if subject.lower() in f.subject.lower()]
    return [f.to_dict() for f in facts]


@app.get("/api/sessions/{session_id}/comparisons")
def get_session_comparisons(session_id: str, relationship_type: Optional[str] = None):
    """Retrieve cross-document reconciliations computed within this session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found")
    comps = session.knowledge_layer.comparisons
    if relationship_type:
        comps = [c for c in comps if c.relationship_type.value == relationship_type.lower()]
    return [c.to_dict() for c in comps]


@app.get("/api/sessions/{session_id}/tables")
def get_session_tables(session_id: str):
    """Retrieve extracted tables for documents in this session."""
    canonical_dict = SESSION_CANONICAL_DOCS.get(session_id, {})
    all_tables = []
    for doc_name, cdoc in canonical_dict.items():
        for t in cdoc.tables:
            td = t.to_dict()
            td["document_name"] = doc_name
            all_tables.append(td)
    return all_tables


@app.get("/api/sessions/{session_id}/figures")
def get_session_figures(session_id: str):
    """Retrieve list of extracted figures and diagrams with rich metadata."""
    meta_list = object_store.get_figures_meta(session_id)
    if meta_list:
        return meta_list

    figs_dir = object_store.get_figures_dir(session_id)
    figures = []
    for fig_file in figs_dir.glob("*/*.png"):
        doc_stem = fig_file.parent.name
        fig_id = fig_file.stem
        figures.append({
            "figure_id": fig_id,
            "document": doc_stem,
            "document_name": f"{doc_stem}.pdf",
            "file_name": fig_file.name,
            "url": f"/api/sessions/{session_id}/figures/{doc_stem}/{fig_id}",
            "caption": f"Visual Asset: {fig_id.replace('_', ' ').title()}",
            "size_kb": round(fig_file.stat().st_size / 1024, 1)
        })
    return figures


@app.post("/api/sessions/{session_id}/reconcile")
def recompute_reconciliation(session_id: str):
    """Recompute cross-document and intra-document fact reconciliation."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found")
    all_session_facts = session.knowledge_layer.facts
    all_session_docs = sorted(list(set([d["filename"] for d in session.documents])))
    session.knowledge_layer = reconciler.reconcile(all_session_facts, all_session_docs)
    session_manager.save_knowledge_layer(session_id, session.knowledge_layer)
    return {
        "status": "success",
        "total_facts": len(all_session_facts),
        "comparisons_count": len(session.knowledge_layer.comparisons),
        "comparisons": [c.to_dict() for c in session.knowledge_layer.comparisons],
        "statistics": session.knowledge_layer.statistics
    }


@app.post("/api/sessions/{session_id}/reprocess")
def reprocess_session_documents(session_id: str):
    """Reprocess all documents in this session with the upgraded figure & fact extractors."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found")

    docs_dir = object_store.get_documents_dir(session_id)
    pdf_files = list(docs_dir.glob("*.pdf"))
    processed = []

    for pdf_path in pdf_files:
        fname = pdf_path.name
        canonical_doc = pdf_loader.load_canonical_document(
            pdf_path=str(pdf_path),
            session_id=session_id,
            render_thumbnails=False
        )

        figures = figure_extractor.extract_figures_from_pdf(
            pdf_path=str(pdf_path),
            session_id=session_id,
            max_pages=None
        )
        canonical_doc.figures_count = len(figures)

        new_facts = fact_extractor.extract_from_pages(canonical_doc.pages)

        # Update canonical doc cache
        if session_id not in SESSION_CANONICAL_DOCS:
            SESSION_CANONICAL_DOCS[session_id] = {}
        SESSION_CANONICAL_DOCS[session_id][fname] = canonical_doc

        # Replace facts for this document
        remaining_facts = [f for f in session.knowledge_layer.facts if f.evidence and f.evidence.document_name != fname]
        all_session_facts = remaining_facts + new_facts
        session.knowledge_layer.facts = all_session_facts

        # Update or add doc entry in session
        existing_doc = next((d for d in session.documents if d.get("filename") == fname), None)
        if existing_doc:
            existing_doc["figures_count"] = len(figures)
            existing_doc["blocks_count"] = len(canonical_doc.blocks)
            existing_doc["tables_count"] = len(canonical_doc.tables)
            existing_doc["summary"] = f"Processed {canonical_doc.total_pages} pages with {len(canonical_doc.blocks)} text blocks, {len(canonical_doc.tables)} structured tables, and {len(figures)} figures."
        else:
            doc_entry = {
                "doc_id": canonical_doc.doc_id,
                "filename": fname,
                "title": canonical_doc.title,
                "pages_count": canonical_doc.total_pages,
                "blocks_count": len(canonical_doc.blocks),
                "tables_count": len(canonical_doc.tables),
                "figures_count": canonical_doc.figures_count,
                "summary": f"Processed {canonical_doc.total_pages} pages with {len(canonical_doc.blocks)} text blocks, {len(canonical_doc.tables)} structured tables, and {len(figures)} figures.",
                "tags": canonical_doc.tags,
                "status": "Processed",
                "processed_time": "Just now",
                "size_bytes": pdf_path.stat().st_size
            }
            session.documents.append(doc_entry)

        # Persist to database
        session_manager.add_document(
            session_id=session_id,
            doc_entry=existing_doc or doc_entry,
            pages=canonical_doc.pages,
            facts=new_facts,
            comparisons=[]
        )
        session_manager.update_document_figures_count(session_id, fname, len(figures))

        processed.append({"filename": fname, "figures": len(figures), "facts": len(new_facts)})

    all_session_docs = sorted(list(set([d["filename"] for d in session.documents])))
    session.knowledge_layer = reconciler.reconcile(session.knowledge_layer.facts, all_session_docs)
    session_manager.save_knowledge_layer(session_id, session.knowledge_layer)

    return {
        "status": "reprocessed",
        "documents": processed,
        "total_figures": sum(p["figures"] for p in processed),
        "total_facts": len(session.knowledge_layer.facts),
        "comparisons": len(session.knowledge_layer.comparisons)
    }


@app.get("/api/sessions/{session_id}/structure")
def get_session_document_structure(session_id: str):
    """Retrieve page-by-page layout block structure and hierarchy."""
    canonical_dict = SESSION_CANONICAL_DOCS.get(session_id, {})
    structure = {}
    for doc_name, cdoc in canonical_dict.items():
        structure[doc_name] = {
            "total_pages": cdoc.total_pages,
            "total_blocks": len(cdoc.blocks),
            "blocks_by_page": {
                p.page_number: [b.to_dict() for b in p.blocks]
                for p in cdoc.pages
            }
        }
    return structure


@app.post("/api/sessions/{session_id}/chat")
def session_chat(session_id: str, req: ChatQueryRequest):
    """Process natural language query strictly grounded in this session's documents."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found")

    vstore = get_session_vector_store(session_id)
    canonical_dict = SESSION_CANONICAL_DOCS.get(session_id, {})
    result = chat_engine.process_chat(
        session=session,
        vector_store=vstore,
        user_query=req.query,
        document_name=req.document_name,
        canonical_docs=canonical_dict
    )
    for m in session.messages[-2:]:
        session_manager.persist_message(session_id, m)
    return result


@app.get("/api/storage/quota")
def get_storage_quota():
    """Retrieve storage capacity and usage stats across sessions."""
    return object_store.get_global_storage_stats()


FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    if FRONTEND_DIST.exists():
        if full_path:
            requested_file = (FRONTEND_DIST / full_path).resolve()
            dist_resolved = FRONTEND_DIST.resolve()
            try:
                requested_file.relative_to(dist_resolved)
                if requested_file.is_file():
                    return FileResponse(requested_file)
            except ValueError:
                pass

        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(index_file)

    return HTMLResponse("<h1>Document Intelligence</h1><p>Frontend is building...</p>")
