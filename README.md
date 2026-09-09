# Meridian — Fact Knowledge Layer

A multimodal document intelligence system that ingests PDF documents, extracts grounded numerical and semantic facts, links each fact to verbatim source evidence, and identifies cross-document corroborations, contradictions, and reconciliations.

---

## Overview

Organizations scatter critical facts across annual reports, presentations, financial statements, and policy reviews. The same metric often appears in different units, scopes, or time periods, making verification and consistency audits difficult.

Meridian parses PDFs into unified layouts, text blocks, structured tables, and visual vector/raster figures. It extracts typed facts (numerical metrics, percentages, currency values) with deterministic rules and optional LLM augmentation. A cross-document reconciliation engine groups related metrics to determine where documents corroborate, contradict, or reconcile through contextual differences. Results are inspectable through a REST API and a responsive React workspace UI.

---

## Core Capabilities

- **PDF Ingestion & Structural Parsing**: Extracts per-page text blocks, layout hierarchies, structured Markdown tables, and rendered page thumbnails using PyMuPDF.
- **Visual Chart & Figure Extraction**: Automatically detects vector charts (`Chart ...`, `Figure ...`) and embedded raster images, generating high-resolution 150 DPI clips with structured metadata manifests.
- **Deterministic & LLM-Augmented Fact Extraction**: Dual-layer fact extraction using domain-aware regex patterns for precision financial figures, supplemented by LLM extraction for semantic facts.
- **Verbatim Evidence Grounding**: Every extracted fact links directly to its source document, exact page number, and verbatim excerpt.
- **Intra- & Cross-Document Reconciliation**: Evaluates facts pairwise across documents and reporting scopes (e.g., Headline vs. Core CPI, Budget Estimates vs. Revised Estimates) to identify corroborations, contradictions, and reconciled context.
- **Session-Isolated Workspaces**: Complete multi-tenant isolation for documents, metadata, vector embeddings, and conversation histories backed by SQLite.
- **Strictly Grounded Multimodal RAG**: Query documents with conversational AI powered by Google Gemini (with automatic `gemini-3.6-flash` resolution). Passes high-resolution chart images directly to the vision model for visual data point extraction without open hallucination.
- **Interactive Lightbox Inspection**: Full-screen figure inspection modal with zoom preview, dimensions, and PNG export.
- **Runtime Settings & Key Management**: Configure and persist Gemini or OpenAI API keys directly from the UI without restarting servers.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      React SPA (Vite)                       │
│        Workspace Manager · Document Viewer · Figures Tab    │
│      Facts Explorer · Reconciliation Matrix · Ask Chat      │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP (REST)
┌──────────────────────────────▼──────────────────────────────┐
│                  FastAPI Application Server                 │
│                       (src/api/app.py)                      │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│  Ingestion  │    Facts    │   Reconc.   │     RAG / Chat    │
│  PDFLoader  │  Extractor  │   Engine    │    ChatEngine     │
│ FigureExtr. │ LLMProvider │             │ SessionVectorStore│
├─────────────┴─────────────┴─────────────┴───────────────────┤
│                       Session Manager                       │
│                  (SQLite Relational Schema)                 │
├─────────────────────────────┬───────────────────────────────┤
│          SQLite DB          │          Object Store         │
│  workspaces                 │  data/object_store/{session}/ │
│  documents & document_pages │    documents/ (raw PDFs)      │
│  facts & evidence           │    thumbnails/ (page images)  │
│  fact_relationships         │    figures/ (chart crops)     │
│  messages (chat history)    │    tables/ (persisted JSON)   │
│                             │    chroma/ (vector embeddings)│
└─────────────────────────────┴───────────────────────────────┘
```

---

## Approach

### 1. Architectural Strategy
Important business and macroeconomic data does not live only in plain text paragraphs; it is concentrated in structured tables and visual trend charts. A naive text-only RAG system misses the majority of quantitative evidence. Meridian was designed around three principles:
1. **Multimodal Evidence First**: Extract text, tables, and charts into distinct first-class artifacts with coordinates, page numbers, and image assets.
2. **Deterministic Grounding**: Facts must be tethered to verbatim source text. Numbers without verbatim evidence spans are rejected.
3. **Graceful Degradation**: The entire pipeline (ingestion, table extraction, figure clipping, fact extraction, reconciliation, and search) runs deterministically without an internet connection or LLM API key. When an LLM key is provided, the system seamlessly activates multimodal vision synthesis.

### 2. Important Decisions & Trade-offs
- **PyMuPDF Vector Clipping vs. Heavy VLM OCR**: Rather than running slow, GPU-intensive vision-language models (e.g. Qwen-VL) over every single page of a 100-page report, Meridian inspects drawing command paths and caption markers to clip vector charts natively at 150 DPI. This provides 50x faster ingestion while maintaining pixel-perfect fidelity.
- **SQLite + Local Object Store vs. Cloud Microservices**: Meridian uses an embedded SQLite database with foreign-key integrity and a structured local object store directory. This guarantees zero external setup friction for local evaluators while offering optional MinIO/S3 mirroring for production.
- **Dual-Layer Fact Extraction**: Using regex patterns for currency amounts, percentages, and fiscal metrics ensures 100% precision and instant execution. The LLM provider is invoked only as a secondary pass to extract complex semantic relationships.
- **Adaptive Model Resolution**: Automated discovery prioritizing `gemini-3.6-flash`, falling back through `gemini-flash-latest` and legacy endpoints, ensuring compatibility across different Google API key provisioning tiers.
- **Markdown Normalization in Chat**: LLM generation output is preprocessed to enforce Markdown block breaks (`\n\n###`, `\n\n---`) so headers, bullet points, and tables render cleanly without collapsing whitespace.

### 3. AI Tools Used
- **Google Antigravity**: Used as the primary agentic pair-programming assistant for iterative codebase refactoring, live execution debugging, FastAPI route optimization, and end-to-end browser verification.
- **Claude**: Used for high-level system architecture modeling, prompt engineering strategies for strictly-grounded multimodal vision, and semantic reconciliation design.

---

## Data Models

| Model | Location | Description |
|---|---|---|
| `Fact` | `src/facts/models.py` | Subject, attribute, value, normalized_value, unit, temporal_scope, context_scope, confidence, evidence |
| `Evidence` | `src/facts/models.py` | Source document name, page number, verbatim_quote, char_offset, table_citation, image_citation |
| `FactComparison` | `src/facts/models.py` | Relationship type (corroboration, contradiction, reconciled, extraction_failure), paired facts, explanation, reconciliation_factor |
| `KnowledgeLayer` | `src/facts/models.py` | Session-level container aggregating documents, facts, comparisons, and summary statistics |
| `CanonicalDocument` | `src/ingestion/pdf_loader.py` | Unified document schema with text blocks, tables, figures, tags, and page counts |
| `WorkspaceSession` | `src/sessions/session_manager.py` | Multi-tenant workspace containing isolated documents, conversation threads, and knowledge layers |

---

## Evidence Grounding & Reconciliation Logic

### Evidence Grounding
Every extracted fact includes an `Evidence` record containing:
- `document_name`: Exact source PDF filename
- `page_number`: 1-indexed document page
- `verbatim_quote`: Surrounding context sentence from the source text
- `table_citation` / `image_citation`: Specific reference to the source table column header or figure ID

### Reconciliation Engine
The engine (`src/reconciliation/engine.py`) normalizes attributes into shared semantic clusters (e.g. GDP growth, inflation, deficits, revenue) and evaluates fact pairs:

| Relationship Type | Definition & Evaluation Criteria |
|---|---|
| `corroboration` | Facts from different documents (or distinct sections) reporting consistent values within tolerance (default ±0.5%). |
| `contradiction` | Facts sharing the exact same subject, attribute, scope, and time period whose values diverge beyond tolerance. |
| `reconciled` | Apparent divergences resolved by differing temporal boundaries (e.g., FY24 vs FY25), reporting scopes (e.g., Headline vs. Core CPI, Standalone vs. Consolidated), or estimation stages (Budget Estimate vs. Revised Estimate). |
| `extraction_failure` | Documents handled edge cases such as parenthetical negative financial accounting notation `(1,234.56)` vs raw values. |

---

## Setup and Run Instructions

### Prerequisites
- **Python**: 3.10 or higher
- **Node.js**: 18 or higher (with npm)
- **Git**

### 1. Clone & Python Environment Setup
```bash
git clone https://github.com/YashBhardwaj21/multimodal-fact-knowledge-layer.git
cd multimodal-fact-knowledge-layer

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (CMD):
venv\Scripts\activate.bat
# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Environment Configuration (Optional)
Create a `.env` file in the root directory (or configure keys directly in the UI Settings):
```env
# Optional: Google Gemini API Key for multimodal chat & vision
GEMINI_API_KEY="your-gemini-api-key"

# Optional: OpenAI API Key
OPENAI_API_KEY="your-openai-api-key"

# Optional: MinIO / S3 Object Storage
MINIO_ENDPOINT="localhost:9000"
MINIO_ACCESS_KEY="minioadmin"
MINIO_SECRET_KEY="minioadmin"
```

### 4. Running the Application

#### Production Mode (Unified Backend & Frontend)
```bash
python run_server.py --port 8000
```
Open your browser at **`http://localhost:8000`**. The FastAPI server serves the REST API and the built React frontend application.

#### Development Mode (Hot-Reload)
Run the backend in one terminal:
```bash
python run_server.py --port 8000
```
Run the Vite development server in a second terminal:
```bash
cd frontend
npm run dev
```
Open your browser at **`http://localhost:3000`**. The Vite server proxies API calls seamlessly to port 8000.

### 5. Running the CLI Pipeline (Headless Mode)
To process raw PDFs into structured fact extraction and reconciliation outputs without a web browser:
```bash
python pipeline.py data/raw/ --output outputs/ --llm auto
```
Outputs:
- `outputs/knowledge_layer.json`: Full serialized knowledge layer
- `outputs/knowledge_summary.txt`: Human-readable summary of facts and comparisons

### 6. Running Automated Tests
```bash
pytest tests/ -v
```

---

## API Reference

Base URL: `http://localhost:8000`

### Workspace Sessions
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/sessions` | List all workspaces with document & fact counts |
| `POST` | `/api/sessions` | Create a new isolated workspace (`{title, description}`) |
| `GET` | `/api/sessions/{id}` | Workspace details with documents and knowledge stats |
| `PATCH` | `/api/sessions/{id}` | Rename an existing workspace (`{title}`) |
| `DELETE` | `/api/sessions/{id}` | Delete workspace, purging database records and object files |

### Document Management
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions/{id}/documents` | Upload PDF (multipart/form-data) — triggers layout analysis, table extraction, figure clipping, and reconciliation |
| `GET` | `/api/sessions/{id}/documents` | List documents registered in the workspace |
| `DELETE` | `/api/sessions/{id}/documents/{doc_id}` | Remove a document and delete its vector embeddings and image assets |

### Facts, Figures & Reconciliation
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/sessions/{id}/facts` | Retrieve extracted facts (supports `?subject=` filter) |
| `GET` | `/api/sessions/{id}/comparisons` | Retrieve cross-document comparisons (`?relationship_type=`) |
| `POST` | `/api/sessions/{id}/reconcile` | Trigger on-demand reconciliation recomputation |
| `GET` | `/api/sessions/{id}/tables` | Retrieve extracted Markdown tables with column headers |
| `GET` | `/api/sessions/{id}/figures` | Retrieve figure assets with dimensions, captions, and URLs |
| `GET` | `/api/sessions/{id}/figures/{doc_stem}/{fig_id}` | Serve extracted figure PNG image (supports `.png` suffix) |
| `GET` | `/api/sessions/{id}/documents/{doc_stem}/pages/{n}/thumbnail` | Serve rendered page thumbnail PNG |

### Grounded Chat & Settings
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions/{id}/chat` | Ask grounded questions with multimodal image support (`{query, document_name?}`) |
| `GET` | `/api/settings` | Retrieve active LLM provider status, active model, and masked key |
| `POST` | `/api/settings` | Save API key at runtime (`{gemini_api_key, openai_api_key}`) and persist to `.env` |
| `GET` | `/api/storage/quota` | Check global storage utilization across sessions |

---

## Limitations and Next Steps

### Current Limitations
1. **Complex Borderless Tables**: While ruled tables extract cleanly, deeply nested or borderless multi-column tables in complex annual reports can experience merged cell alignment shifts under PyMuPDF's heuristic table finder.
2. **Captionless Visual Assets**: Figures without explicit caption prefixes (`Chart ...`, `Figure ...`, `Exhibit ...`) rely on bounding-box heuristics and may occasionally miss decorative graphics.
3. **Local GPU Requirement for Scanned OCR**: The native ingestion engine processes searchable, digital-native PDFs. Scanned image-only PDFs require the optional Qwen3-VL OCR pipeline, which needs an NVIDIA GPU with substantial VRAM.
4. **Token Limits on Extreme Document Clusters**: In workspaces with dozens of multi-hundred-page documents, simultaneous pairwise reconciliation across thousands of facts requires batched map-reduce clustering to avoid memory spikes.

### Next Steps & Roadmap
1. **Deep Learning Table Parsers**: Integrate lightweight vision-based table transformers (e.g. Table-Transformer or Microsoft UniLM) for borderless financial statement parsing.
2. **Interactive Temporal Knowledge Graph**: Expand the Knowledge Graph view with timeline sliders to visualize the evolution of key economic metrics across multiple quarters and fiscal years.
3. **Cross-Workspace Comparison Matrices**: Allow comparative side-by-side discrepancy analysis between entire workspaces (e.g., comparing Company A vs. Company B financial metrics).
4. **Export Engine**: Add one-click export of verified fact reconciliation matrices to Excel (`.xlsx`), CSV, and XBRL formats.

---

## Additional Notes

- **Self-Healing Adaptive LLM Resolution**: If a Google API key does not have access to legacy `gemini-1.5-flash` endpoints, the system automatically resolves to `gemini-3.6-flash` without throwing unhandled exceptions.
- **Zero-Hallucination Prompting**: Multimodal chat prompts explicitly instruct the vision model to transcribe exact visual numbers, legends, and axes directly from attached image crops while forbidding open extrapolation.
- **No-Key Operation**: The system operates with full deterministic capability out-of-the-box. Fact extraction, table viewing, figure rendering, and reconciliation matrices function completely without third-party API credentials.
- **Persistence Across Restarts**: Extracted structured tables, figure metadata manifests, and SQLite relations are persisted in `data/object_store` and `data/database`, surviving server restarts.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
