# 🌐 Schemesathi Web Scraper & FastAPI Admin Panel

A robust web scraping system built to extract raw web page data, structured content, and PDF files from Karnataka Government portals, complete with a modern **FastAPI Admin Panel** dashboard.

---

## 🎯 Target Portals Scraped
1. **Seva Sindhu**: `https://sevasindhugs1.karnataka.gov.in/gl-sp/`
2. **State Scholarship Portal (SSP)**: `https://ssp.karnataka.gov.in/`
3. **Government of Karnataka**: `https://www.karnataka.gov.in/`

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

## 💻 Admin Panel Features (`http://127.0.0.1:8000/admin`)

- **Dashboard Overview**: Displays total scraped pages count, total downloaded PDFs count, total storage size, and last run status.
- **Scraped Data (SQL)**: Interactive, paginated table of scraped HTML pages. Filter by domain or search by title/URL. Click **"View Raw Data"** to view clean text and raw HTML source.
- **Scraped PDFs**: Lists all downloaded PDF files stored in `scraper/SCRAPED PDF`. Click **"Download PDF"** to preview or download any PDF file directly.
- **Scraper Control Panel**: Trigger new scraping jobs with a single click and watch live execution logs.
- **API Documentation**: Interactive Swagger docs available at `http://127.0.0.1:8000/docs`.
