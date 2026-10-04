import os
import asyncio
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, Depends, BackgroundTasks, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from scraper.config import PDF_DIR, BASE_DIR
from scraper.database import (
    init_db, get_db, get_stats, ScrapedPage, ScrapedPDF, ScrapeRunLog
)
from scraper.scraper import WebScraper

# Initialize DB tables on startup
init_db()

app = FastAPI(
    title="Schemesathi Web Scraper Admin Panel",
    description="Admin Panel for monitoring scraped web pages and PDF documents",
    version="1.0.0"
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount SCRAPED PDF folder as static media endpoint
app.mount("/scraped-pdf", StaticFiles(directory=str(PDF_DIR)), name="scraped_pdf")

# Mount scheme_cleaner cleaned folder static endpoint
CLEANED_DIR = BASE_DIR / "scheme_cleaner" / "data" / "cleaned"
if CLEANED_DIR.exists():
    app.mount("/scheme_cleaner/data/cleaned", StaticFiles(directory=str(CLEANED_DIR)), name="cleaned_data")

# Global scraper status lock
scraper_running = False
current_scraper_logs: List[str] = []


def run_scraper_in_background():
    global scraper_running, current_scraper_logs
    scraper_running = True
    current_scraper_logs.clear()
    
    def on_progress(msg: str):
        current_scraper_logs.append(msg)

    try:
        scraper = WebScraper()
        scraper.run(progress_callback=on_progress)
    except Exception as e:
        current_scraper_logs.append(f"Scraper error: {str(e)}")
    finally:
        scraper_running = False


@app.get("/", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    """Renders the main Admin Dashboard UI."""
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/schemes", response_class=HTMLResponse)
def schemes_dashboard():
    """Renders the Cleaned Schemes Box Grid UI (index.html)."""
    index_path = BASE_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return HTMLResponse("<h1>index.html not found</h1>", status_code=404)


@app.get("/api/stats")
def api_get_stats(db: Session = Depends(get_db)):
    """Returns overview statistics of scraped pages and PDFs."""
    stats = get_stats(db)
    if scraper_running:
        stats["last_scrape"]["status"] = "RUNNING"
    return stats


@app.get("/api/data")
def api_get_data(
    q: Optional[str] = Query(None, description="Search query for title or URL"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    db: Session = Depends(get_db)
):
    """Returns list of scraped SQL pages."""
    query = db.query(ScrapedPage)
    if domain:
        query = query.filter(ScrapedPage.domain.ilike(f"%{domain}%"))
    if q:
        query = query.filter((ScrapedPage.title.ilike(f"%{q}%")) | (ScrapedPage.url.ilike(f"%{q}%")))

    pages = query.order_by(ScrapedPage.id.desc()).limit(100).all()

    return [
        {
            "id": p.id,
            "url": p.url,
            "domain": p.domain,
            "title": p.title,
            "status": p.status,
            "http_status": p.http_status,
            "pdf_count": p.pdf_count,
            "links_count": p.links_count,
            "scraped_at": p.scraped_at.isoformat() if p.scraped_at else None
        }
        for p in pages
    ]


@app.get("/api/data/{page_id}")
def api_get_data_detail(page_id: int, db: Session = Depends(get_db)):
    """Returns full raw data and content of a single scraped page."""
    page = db.query(ScrapedPage).filter(ScrapedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page record not found")
    return {
        "id": page.id,
        "url": page.url,
        "domain": page.domain,
        "title": page.title,
        "status": page.status,
        "content_text": page.content_text,
        "raw_html": page.raw_html,
        "meta_description": page.meta_description,
        "scraped_at": page.scraped_at.isoformat() if page.scraped_at else None
    }


@app.get("/api/pdfs")
def api_get_pdfs(db: Session = Depends(get_db)):
    """Returns list of scraped PDF documents."""
    pdfs = db.query(ScrapedPDF).order_by(ScrapedPDF.id.desc()).all()
    return [
        {
            "id": pdf.id,
            "file_name": pdf.file_name,
            "page_url": pdf.page_url,
            "pdf_url": pdf.pdf_url,
            "file_size_bytes": pdf.file_size_bytes,
            "status": pdf.status,
            "downloaded_at": pdf.downloaded_at.isoformat() if pdf.downloaded_at else None
        }
        for pdf in pdfs
    ]


@app.get("/api/pdf-download/{pdf_id}")
def api_download_pdf(pdf_id: int, db: Session = Depends(get_db)):
    """Streams/Downloads the requested PDF file directly from the SCRAPED PDF folder."""
    pdf = db.query(ScrapedPDF).filter(ScrapedPDF.id == pdf_id).first()
    if not pdf or not pdf.file_path or not os.path.exists(pdf.file_path):
        raise HTTPException(status_code=404, detail="PDF file not found on disk")
    return FileResponse(
        path=pdf.file_path,
        filename=pdf.file_name,
        media_type="application/pdf"
    )


@app.post("/api/scrape")
def api_trigger_scrape(background_tasks: BackgroundTasks):
    """Triggers a background scraping job."""
    global scraper_running
    if scraper_running:
        return {"status": "ALREADY_RUNNING", "message": "Scraper is already running in background"}

    background_tasks.add_task(run_scraper_in_background)
    return {"status": "STARTED", "message": "Scraper process started successfully!"}


@app.get("/api/scrape/status")
def api_scrape_status(db: Session = Depends(get_db)):
    """Returns current status and log summary of the active/latest scraper run."""
    last_log = db.query(ScrapeRunLog).order_by(ScrapeRunLog.id.desc()).first()
    
    summary = "\n".join(current_scraper_logs[-25:]) if current_scraper_logs else (last_log.log_summary if last_log else "No logs available.")
    status = "RUNNING" if scraper_running else (last_log.status if last_log else "IDLE")

    return {
        "status": status,
        "summary": summary
    }
