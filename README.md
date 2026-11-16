# 🌐 Schemesathi Web Scraper & FastAPI Admin Panel

A robust multi-level web scraping system built to extract raw web page data, structured scheme content, application forms, and PDF documents from Karnataka Government portals, complete with a modern **FastAPI Admin Panel** dashboard.

---

## 🎯 Target Portals & Multi-Level Crawling Hierarchy

The scraper implements intelligent, priority-based deep crawling:
`Home Page ➔ Scheme Catalog/Details ➔ Application Form Pages ➔ Redirected Service Portals`

1. **Seva Sindhu**: `https://sevasindhugs1.karnataka.gov.in/gl-sp/`
   - Crawls home page, scheme requirements, eligibility forms, and follows redirects to ServicePlus application portals (`serviceonline.gov.in`).
2. **State Scholarship Portal (SSP)**: `https://ssp.karnataka.gov.in/`
   - Crawls home page, scheme listings, downloads, and follows links/redirects to Pre-Matric & Post-Matric application & student login portals (`ssp.postmatric.karnataka.gov.in/ca/`, `ssppre/`).
3. **Government of Karnataka Portal**: `https://www.karnataka.gov.in/`
   - Crawls welfare schemes, department citizen services, and redirects to official departmental service desks (`sevasindhuservices.karnataka.gov.in`, `sakala.kar.nic.in`).

### 🔍 Key Scraping Features
- **Deep Multi-Level Traversal**: Configured default `MAX_DEPTH = 5` and `MAX_PAGES_PER_DOMAIN = 500`.
- **Application Form & Redirect Detection**: Automatically detects online application pages, `<form>` actions, JavaScript `onclick` redirects, and follows HTTP 301/302 redirects to destination application endpoints.
- **Priority Queue Crawling**: Priority 0 for Application Forms & Apply buttons, Priority 1 for Schemes, Priority 2 for Category listings, Priority 3 for general pages.
- **Strict Asset Filtering**: Prevents crawling CSS, JavaScript, image, or font assets.
- **PDF & Blank Form Extraction**: Downloads all application form PDFs, guidelines, and annexures to `scraper/SCRAPED PDF/`.
- **Page Classification**: Categorizes each page into `HOME`, `SCHEME`, `APPLICATION_FORM`, or `GENERAL`.

---

## 📁 Folder Structure

```
Schemsathi/
├── scraper/                     # Scraper module folder
│   ├── SCRAPED PDF/             # Folder containing all downloaded PDF documents
│   ├── config.py                # Target URLs, paths, timeouts, and DB config
│   ├── database.py              # SQLite / SQLAlchemy models (Pages, PDFs, Logs, Hashes)
│   ├── fetcher.py               # HTTP fetcher with custom SSL/SNI fallback
│   ├── parser.py                # BeautifulSoup HTML parser & link/PDF extractor
│   ├── scraper.py               # Core WebScraper crawling engine
│   ├── periodic_scraper.py      # 24-Hour periodic incremental scraper (updates ONLY if content changes)
│   └── scraped_data.db          # SQLite Database storing all scraped raw data
├── admin/                       # FastAPI Admin Panel module
│   ├── app.py                   # FastAPI server endpoints & background tasks
│   ├── templates/
│   │   └── dashboard.html       # Responsive Bootstrap 5 Admin Dashboard UI
│   └── static/                  # Optional static assets
├── main.py                      # Main launcher script for FastAPI Admin Panel
├── run_scraper.py               # Standalone CLI script to trigger scraper
└── README.md                    # System documentation
```

---

## 🚀 Quick Start Instructions

### 1. Run 24-Hour Periodic Incremental Scraper
To run the automated 24-hour periodic scraper that checks target websites and updates SQL **ONLY if new/updated content or PDFs are detected** (using SHA-256 content hashing):

- **Continuous 24-Hour Daemon Mode**:
```bash
.\env\Scripts\python.exe -m scraper.periodic_scraper
```

- **Single Test Cycle Run**:
```bash
.\env\Scripts\python.exe -m scraper.periodic_scraper --run-once
```

### 1. Activate Environment & Install Dependencies
```bash
.\env\Scripts\activate
pip install requests beautifulsoup4 fastapi uvicorn jinja2 sqlalchemy lxml urllib3
```

### 2. Run the Web Scraper (Standalone CLI)
To scrape the target websites and save all raw data to SQL and PDFs to `scraper/SCRAPED PDF/`:
```bash
.\env\Scripts\python.exe run_scraper.py
```

### 3. Launch the FastAPI Admin Panel
To start the Admin Dashboard server:
```bash
.\env\Scripts\python.exe main.py
```
Or with custom host/port:
```bash
.\env\Scripts\python.exe main.py --host 127.0.0.1 --port 8000
```

---

## 🏛️ Public Citizen Portal & AI Studio (`http://127.0.0.1:8000/`)

The unified citizen-facing frontend (`index.html`) blends all system modules into an interactive, all-in-one portal:
- **Verified Schemes Catalog**: Real-time search, category filtering (Education, Women, Farmers, Youth, Energy, Food), department filters, and eligibility tags for authenticated Karnataka schemes.
- **Personalized Smart Profile Matcher**: Configure citizen profile (Age, Occupation, Caste/Category, Annual Income) to calculate immediate eligibility matches with a 1-click "Show Only Eligible" toggle.
- **Scheme Details Modal**: In-depth breakdowns of overview, financial benefits, eligibility conditions, required documents checklist, and official apply procedures.
- **SchemeSathi AI Assistant Studio**: Integrated RAG chatbot powered by Qdrant vector retrieval and `/api/rag/chat`. Features recent chat history, the animated SchemeSathi robot mascot, profile-grounded answers, and official citations.
- **Official Forms & Scraped PDFs**: Direct preview and downloads for official circulars and RTI application documents (`/api/pdfs`, `/api/pdf-download/{id}`).
- **Slide-Over & Floating AI Drawer**: Quick AI assistant available from any card or scroll position.

---

## 💻 Admin Panel Features (`http://127.0.0.1:8000/admin`)

- **Dashboard Overview**: Displays total scraped pages count, total downloaded PDFs count, total storage size, and last run status.
- **Scraped Data (SQL)**: Interactive, paginated table of scraped HTML pages. Filter by domain or search by title/URL. Click **"View Raw Data"** to view clean text and raw HTML source.
- **Scraped PDFs**: Lists all downloaded PDF files stored in `scraper/SCRAPED PDF`. Click **"Download PDF"** to preview or download any PDF file directly.
- **Scraper Control Panel**: Trigger new scraping jobs with a single click and watch live execution logs.
- **API Documentation**: Interactive Swagger docs available at `http://127.0.0.1:8000/docs`.

---

## 🧠 SchemeSathi SQL-to-RAG Ingestion & Synchronization Pipeline

A robust, production-conscious RAG pipeline that synchronizes validated and cleaned scheme records from MySQL into the **Qdrant Vector Database**, enabling grounded, citizen-friendly question answering via **Ollama / LLMs**.

### 🔄 End-to-End Pipeline Architecture

```
MySQL Clean Scheme Records (schemes table)
               │
               ▼
   [SchemeDeduplicator]  (ID ➔ Official ID ➔ URL ➔ Name+Dept+State)
               │
               ▼
   [SchemeHasher]        (Deterministic SHA-256 Content Hash)
               │
               ▼
   [Change Detection]
   ├── Case A: New Scheme           ➔ Chunk ➔ Embed ➔ Insert Qdrant ➔ Status: INDEXED
   ├── Case B: Unchanged Content    ➔ Skip Embedding & Vector insertion ➔ Status: UNCHANGED
   ├── Case C: Updated Content      ➔ Delete Old Vectors ➔ Re-chunk ➔ Re-embed ➔ Status: UPDATED
   └── Case D: Missing from Source  ➔ Preserve Vectors ➔ Flag as REVIEW_REQUIRED
               │
               ▼
   [SchemeChunker]       (Section-aware: Overview, Eligibility, Benefits, Documents, Apply Process)
               │
               ▼
   [EmbeddingService]    (SentenceTransformers / Ollama / Built-in Fallback Vectorizer)
               │
               ▼
   [QdrantStore]         (Deterministic UUIDv5 IDs, Cosine Similarity, Filtered Search)
               │
               ▼
   [Retriever & RAGChain]➔ Ollama LLM / Grounded Synthesis ➔ Accurate Citizen Answer with Source Citations
```

### 📡 RAG API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/rag/sync` | Triggers SQL-to-Qdrant synchronization for new and updated schemes |
| `POST` | `/api/rag/chat` | Citizen QA endpoint: takes question & optional profile, returns grounded answer + official sources |
| `GET` | `/api/rag/status` | Returns metrics: total SQL schemes, indexed schemes, unchanged, pending, failed, vectors in Qdrant |
| `GET` | `/api/rag/scheme/{id}` | Returns sync status, content hash, timestamps, and source details for a specific scheme |

#### Example Chat Request:
```bash
curl -X POST "http://127.0.0.1:8000/api/rag/chat" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "What are the eligibility criteria and benefits for Post-Matric Scholarship?",
       "profile": {
         "category": "SC",
         "income": 200000,
         "occupation": "Student",
         "state": "Karnataka"
       }
     }'
```

### 🧪 Running the RAG Pipeline Tests
Run the comprehensive 12-test validation suite covering all synchronization cases, deduplication, vector replacement, and failure modes:

```powershell
.\env\Scripts\python.exe -m unittest tests/test_rag_pipeline.py -v
```
