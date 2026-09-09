# Meridian — Fact Knowledge Layer

A system that ingests PDF documents, extracts grounded numerical and semantic facts, links each fact to verbatim source evidence, and identifies cross-document corroborations, contradictions, and reconciliations.

---

## Overview

Organizations scatter critical information across annual reports, presentations, prospectuses, and whitepapers. The same metric may appear in different units, scopes, or time periods, making it difficult to determine consistency.

Meridian parses PDF documents into structured page layouts, text blocks, tables, and figures. It extracts typed facts (financial metrics, percentages, counts) using both deterministic regex patterns and optional LLM-augmented extraction, then runs a cross-document reconciliation engine to discover where documents agree, disagree, or require contextual resolution. Results are explorable through a REST API and a React-based workspace UI.

---

## Core Capabilities

- **PDF ingestion** with per-page text, layout block, and structured table extraction (PyMuPDF)
- **Page thumbnail rendering** and embedded figure/chart asset extraction
- **Deterministic fact extraction** via domain-aware regex patterns (currency amounts, percentages, counts, unit metrics)
- **LLM-augmented fact extraction** using Gemini, OpenAI, or local Ollama backends (auto-detected)
- **Verbatim evidence grounding** — every extracted fact carries its source document name, page number, verbatim quote, and optional table/image citation
- **Cross-document reconciliation** — pairwise comparison of clustered facts with classification into corroboration, contradiction, reconciled-by-context, or extraction failure
- **Session-isolated workspaces** — documents, facts, embeddings, and chat histories are partitioned per workspace
- **RAG-based conversational Q&A** over workspace documents with vector retrieval (ChromaDB) and source citations
- **Multimodal OCR** via Qwen3-VL vision-language model (optional, for scanned/image-heavy PDFs)

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    React SPA (Vite)                   │
│          Workspace Manager · Document Viewer          │
│       Facts Explorer · Reconciliation Dashboard       │
│                 Ask / Chat Panel                      │
└────────────────────────┬─────────────────────────────┘
                         │ HTTP (REST)
┌────────────────────────▼─────────────────────────────┐
│               FastAPI Application Server              │
│                   (src/api/app.py)                     │
├───────────┬───────────┬───────────┬──────────────────┤
│ Ingestion │   Facts   │  Reconc.  │   RAG / Chat     │
│ PDFLoader │ Extractor │  Engine   │  ChatEngine      │
│ FigExtract│ LLMProvide│           │  VectorStore     │
├───────────┴───────────┴───────────┴──────────────────┤
│                   Session Manager                     │
│              (SQLite — normalized schema)              │
├───────────────────────┬──────────────────────────────┤
│      SQLite DB        │       Object Store            │
│  workspaces           │  data/object_store/           │
│  documents            │    {session}/documents/       │
│  document_pages       │    {session}/thumbnails/      │
│  facts + evidence     │    {session}/figures/         │
│  fact_relationships   │    {session}/chroma/          │
│  messages             │  (+ optional MinIO/S3)        │
└───────────────────────┴──────────────────────────────┘
```

---

## Data Models

| Model | Location | Description |
|---|---|---|
| `Fact` | `src/facts/models.py` | Subject, attribute, value, normalized_value, unit, temporal_scope, context_scope, confidence, evidence |
| `Evidence` | `src/facts/models.py` | Document name, page number, verbatim_quote, char_offset, table_citation, image_citation |
| `FactComparison` | `src/facts/models.py` | Relationship type (corroboration/contradiction/reconciled/extraction_failure), paired facts, explanation, reconciliation_factor |
| `KnowledgeLayer` | `src/facts/models.py` | Aggregate container: all documents, facts, comparisons, statistics |
| `CanonicalDocument` | `src/ingestion/pdf_loader.py` | Unified document: doc_id, pages, text blocks, table observations, figures, tags |
| `WorkspaceSession` | `src/sessions/session_manager.py` | Isolated workspace: documents, messages, knowledge layer |

---

## Evidence & Reconciliation Logic

### Evidence Grounding

Every `Fact` object includes an `Evidence` struct with:
- `document_name` — source PDF filename
- `page_number` — exact page
- `verbatim_quote` — surrounding sentence(s) from the source text
- `table_citation` / `image_citation` — optional table or figure reference (e.g., "Consolidated Statement of Profit & Loss (Table on Page 22)")

### Reconciliation Types

| Type | Meaning |
|---|---|
| `corroboration` | Two facts from different documents report consistent values for the same metric within tolerance (default 0.5%) |
| `contradiction` | Same metric, same scope, same period — values diverge beyond tolerance |
| `reconciled` | Apparent contradiction resolved by differing temporal scope, reporting boundary (standalone vs. consolidated), or unit conversion |
| `extraction_failure` | Documents a known extraction edge case and the system's mitigation (e.g., parenthesized accounting negatives) |

The reconciliation engine (`src/reconciliation/engine.py`) clusters facts by `(subject, attribute)`, then performs pairwise comparison using normalized values, temporal scopes, and context scopes.

---

## Storage Architecture

### SQLite (Metadata + Knowledge)

Location: `data/database/document_intelligence.db`

Seven normalized tables with foreign key cascades:

| Table | Purpose |
|---|---|
| `workspaces` | Workspace metadata (id, title, timestamps) |
| `documents` | Document metadata (filename, hash, page_count, tags, processing status) |
| `document_pages` | Full text per page |
| `facts` | Extracted facts (subject, predicate, value, normalized_value, unit, time, scope) |
| `evidence` | Source grounding per fact (document, page, verbatim quote, citations) |
| `fact_relationships` | Cross-document reconciliations (type, title, reasoning, reconciliation_factor) |
| `messages` | Chat history with serialized citations |

### Object Store (Binary Assets)

Location: `data/object_store/{session_id}/`

Stores PDFs, page thumbnail PNGs, extracted figure PNGs, and ChromaDB vector indices. Optionally syncs to MinIO/S3 when `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, and `MINIO_SECRET_KEY` environment variables are set.

---

## API Reference

Base URL: `http://localhost:8000`

### Workspaces

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/sessions` | List all workspaces |
| `POST` | `/api/sessions` | Create workspace (`{title, description}`) |
| `GET` | `/api/sessions/{id}` | Workspace details with knowledge layer |
| `PATCH` | `/api/sessions/{id}` | Rename workspace (`{title}`) |
| `DELETE` | `/api/sessions/{id}` | Delete workspace and purge all storage |

### Documents

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions/{id}/documents` | Upload PDF (multipart) — triggers ingestion, extraction, reconciliation |
| `GET` | `/api/sessions/{id}/documents` | List documents in workspace |
| `DELETE` | `/api/sessions/{id}/documents/{doc_id}` | Delete document from DB, object store, and vector index |

### Knowledge

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/sessions/{id}/facts` | Extracted facts (optional `?subject=` filter) |
| `GET` | `/api/sessions/{id}/comparisons` | Reconciliations (optional `?relationship_type=` filter) |
| `GET` | `/api/sessions/{id}/tables` | Extracted structured tables |
| `GET` | `/api/sessions/{id}/figures` | Extracted figure assets |
| `GET` | `/api/sessions/{id}/structure` | Page-level block layout |

### Chat & Assets

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions/{id}/chat` | RAG query (`{query, document_name?}`) |
| `GET` | `/api/sessions/{id}/documents/{stem}/pages/{n}/thumbnail` | Page thumbnail PNG |
| `GET` | `/api/sessions/{id}/figures/{stem}/{fig_id}` | Extracted figure PNG |
| `GET` | `/api/storage/quota` | Global storage utilization |

---

## LLM Provider Support

The `LLMProvider` (`src/facts/llm_provider.py`) auto-detects available backends in this order:

1. **Gemini** — if `GEMINI_API_KEY` env var is set (uses `gemini-1.5-flash` by default)
2. **OpenAI** — if `OPENAI_API_KEY` env var is set (uses `gpt-4o-mini` by default)
3. **Ollama** — if a local Ollama server is running on `localhost:11434` (uses the first available model)
4. **Built-in** — deterministic regex-only extraction (no LLM calls)

The system extracts facts with or without an LLM. Deterministic extraction covers currency amounts, percentages, numeric metrics, and tabular cell values. LLM augmentation adds up to 3 additional high-importance facts per page when available.

---

## Frontend

Single-page React application (Vite + React 18) with:

- **Workspace management** — create, rename, delete isolated workspaces
- **Document upload** — drag-and-drop PDF ingestion with real-time processing feedback
- **Document viewer** — page thumbnails, text blocks, extracted tables
- **Facts explorer** — browsable extracted facts with evidence links
- **Reconciliation dashboard** — corroborations, contradictions, and reconciled pairs with full explanations
- **Ask panel** — conversational RAG queries with source citations and page thumbnail previews
- **Storage quota widget** — global storage utilization tracking

Tech stack: React 18, Lucide icons, vanilla CSS, Vite dev server with API proxy to FastAPI backend.

---

## Project Structure

```
├── config/
│   └── config.yaml              # OCR, storage, MinIO configuration
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main SPA component (~69KB)
│   │   ├── index.css            # Full design system
│   │   └── main.jsx             # React entry point
│   ├── public/                  # Static assets (logo, images)
│   ├── vite.config.js           # Vite config with API proxy
│   └── package.json             # React 18, Lucide, Vite
├── src/
│   ├── api/
│   │   └── app.py               # FastAPI routes and SPA serving
│   ├── ingestion/
│   │   ├── pdf_loader.py        # PDF → CanonicalDocument with blocks, tables, thumbnails
│   │   └── figure_extractor.py  # Embedded image asset extraction
│   ├── facts/
│   │   ├── models.py            # Fact, Evidence, FactComparison, KnowledgeLayer
│   │   ├── extractor.py         # Deterministic + LLM fact extraction
│   │   └── llm_provider.py      # Gemini / OpenAI / Ollama abstraction
│   ├── reconciliation/
│   │   └── engine.py            # Cross-document reconciliation engine
│   ├── rag/
│   │   ├── vector_store.py      # ChromaDB session-isolated vector index
│   │   └── chat_engine.py       # RAG chat with grounded citations
│   ├── ocr/
│   │   └── ocr_extractor.py     # Qwen3-VL vision-language OCR
│   ├── preprocessing/
│   │   └── image_preprocessor.py # Image resize/normalization utilities
│   ├── sessions/
│   │   └── session_manager.py   # SQLite-backed workspace + CRUD operations
│   ├── storage/
│   │   └── object_store.py      # Local + MinIO/S3 binary asset manager
│   └── utils/
│       └── config.py            # YAML configuration loader
├── tests/
│   ├── test_session_isolation.py # Multi-tenant isolation tests (metadata, vectors, chat)
│   ├── test_arbitrary_e2e.py     # End-to-end test with synthetic PDF
│   └── test_preprocessing.py     # Image preprocessing tests
├── pipeline.py                  # CLI pipeline: extract → reconcile → JSON output
├── demo_cases.py                # Demonstration script for reconciliation cases
├── run_server.py                # Uvicorn launcher with auto-reload
└── requirements.txt             # Python dependencies
```

---

## Setup & Running

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)

### Installation

```bash
# Clone repository
git clone https://github.com/YashBhardwaj21/multimodal-fact-knowledge-layer.git
cd multimodal-fact-knowledge-layer

# Python dependencies
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Frontend
cd frontend
npm install
npm run build
cd ..
```

### Running the Server

```bash
python run_server.py --port 8000
```

The application serves both the API and the built frontend at `http://localhost:8000`.

For frontend development with hot-reload:

```bash
cd frontend
npm run dev
```

The Vite dev server runs on port 3000 and proxies `/api` requests to the backend on port 8000.

### CLI Pipeline (headless)

```bash
python pipeline.py data/raw/ --output outputs/ --llm auto
```

Outputs `outputs/knowledge_layer.json` and `outputs/knowledge_summary.txt`.

### Optional: LLM Configuration

```bash
# Gemini
export GEMINI_API_KEY=your_key

# OpenAI
export OPENAI_API_KEY=your_key

# Ollama (just start the server)
ollama serve
```

### Optional: MinIO Object Storage

```bash
export MINIO_ENDPOINT=localhost:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin
```

---

## Testing

```bash
pytest tests/ -v
```

Test coverage includes:
- **Session isolation** — verifies documents, vector embeddings, and chat responses never leak between workspaces
- **End-to-end pipeline** — creates a synthetic PDF, uploads via API, verifies fact extraction and chat
- **Preprocessing** — image resize utilities

---

## Known Limitations

- Table extraction depends on PyMuPDF's `find_tables()`, which can miss tables without explicit ruling or merge cells incorrectly
- Deterministic regex patterns in `extractor.py` include domain-specific rules tuned to the starter dataset; novel document types benefit from LLM augmentation
- OCR module (Qwen3-VL) requires a CUDA GPU and significant VRAM; it is not used in the default ingestion path (PyMuPDF handles text-native PDFs)
- The reconciliation engine's `_generate_case_demonstrations()` method contains hardcoded comparisons for the starter Delhivery dataset as demonstration examples
- Frontend is a single-file React component (`App.jsx`, ~69KB); no component decomposition or routing library

---

## Dependencies

| Category | Packages |
|---|---|
| Server | FastAPI, Uvicorn, Pydantic, python-multipart |
| Document Processing | PyMuPDF, pdf2image, Pillow, OpenCV, NumPy |
| ML / Embeddings | PyTorch, Transformers, Accelerate, qwen-vl-utils, ChromaDB |
| Frontend | React 18, Lucide React, Vite |
| Storage | SQLite (stdlib), MinIO (optional) |
| Config | PyYAML |

---

## License

MIT — see [LICENSE](LICENSE).
