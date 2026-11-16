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

# Mount RAG and Synchronization Routers
from backend.app.api.sync import router as rag_sync_router
from backend.app.api.rag import router as rag_chat_router

app.include_router(rag_sync_router)
app.include_router(rag_chat_router)

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
@app.get("/schemes", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
def citizen_portal():
    """Renders the main SchemeSathi Citizen Portal UI (index.html)."""
    index_path = BASE_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return HTMLResponse("<h1>index.html not found</h1>", status_code=404)


@app.get("/chatbot", response_class=HTMLResponse)
@app.get("/chatbot.html", response_class=HTMLResponse)
@app.get("/chat", response_class=HTMLResponse)
def chatbot_portal():
    """Renders the dedicated SchemeSathi Scheme Chatbot UI (chatbot.html)."""
    chat_path = BASE_DIR / "chatbot.html"
    if chat_path.exists():
        return FileResponse(str(chat_path))
    return HTMLResponse("<h1>chatbot.html not found</h1>", status_code=404)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    """Renders the main Admin Dashboard UI."""
    return templates.TemplateResponse(request=request, name="dashboard.html")


def categorize_scheme_record(s: dict) -> str:
    """Categorizes a scheme record into a standard citizen-friendly domain."""
    name = (s.get("scheme_name") or "").lower()
    dept = (s.get("department") or "").lower()
    desc = (s.get("description") or "").lower()
    occ = [str(o).lower() for o in s.get("occupation") or []]

    if "shakti" in name or "lakshmi" in name or "women" in name or "widow" in occ:
        return "Women & Child Welfare"
    if "yuva nidhi" in name or "cmegp" in name or "unemployed youth" in occ:
        return "Youth & Employment"
    if "ganga kalyana" in name or "krishi" in name or "farmer" in name or "agriculture" in dept:
        if "vidya" in name or "scholarship" in name:
            return "Education & Scholarships"
        return "Agriculture & Farmers"
    if any(k in name or k in desc for k in ["scholarship", "vidya", "education", "arivu", "post-matric"]) or "student" in occ:
        return "Education & Scholarships"
    if "jyoti" in name or "energy" in dept or "electricity" in desc:
        return "Energy & Utilities"
    if "anna bhagya" in name or "food" in dept or "ration" in desc:
        return "Food & Civil Supplies"
    if any(k in name or k in desc for k in ["pension", "differently abled", "disability", "senior"]):
        return "Social Security & Welfare"
    return "Citizen Services & Portals"


@app.get("/api/schemes")
def api_get_schemes(
    q: Optional[str] = Query(None, description="Search query for name, description, benefits"),
    category: Optional[str] = Query(None, description="Category filter"),
    department: Optional[str] = Query(None, description="Department filter"),
    occupation: Optional[str] = Query(None, description="Occupation filter"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Returns clean, structured schemes list with search and filter capabilities."""
    from backend.app.ingestion.mysql_scheme_loader import MySQLSchemeLoader
    loader = MySQLSchemeLoader()
    raw_schemes = loader.load_clean_schemes()

    # Normalize parameters if invoked directly
    q_val = q.strip().lower() if isinstance(q, str) and q.strip() else None
    cat_val = category.strip().lower() if isinstance(category, str) and category.strip() and category.strip().lower() != "all" else None
    dept_val = department.strip().lower() if isinstance(department, str) and department.strip() and department.strip().lower() != "all" else None
    occ_val = occupation.strip().lower() if isinstance(occupation, str) and occupation.strip() and occupation.strip().lower() != "all" else None
    limit_val = limit if isinstance(limit, int) else 100
    offset_val = offset if isinstance(offset, int) else 0

    enriched = []
    for s in raw_schemes:
        s["computed_category"] = categorize_scheme_record(s)
        enriched.append(s)

    # Search filter
    if q_val:
        enriched = [
            s for s in enriched
            if q_val in (s.get("scheme_name") or "").lower()
            or q_val in (s.get("description") or "").lower()
            or q_val in (s.get("department") or "").lower()
            or any(q_val in str(b).lower() for b in s.get("benefits") or [])
            or any(q_val in str(e).lower() for e in s.get("eligibility") or [])
        ]

    # Category filter
    if cat_val:
        enriched = [s for s in enriched if cat_val in s["computed_category"].lower()]

    # Department filter
    if dept_val:
        enriched = [s for s in enriched if dept_val in (s.get("department") or "").lower()]

    # Occupation filter
    if occ_val:
        enriched = [
            s for s in enriched
            if any(occ_val in str(o).lower() for o in s.get("occupation") or [])
            or occ_val in (s.get("description") or "").lower()
        ]

    total = len(enriched)
    paginated = enriched[offset_val:offset_val + limit_val]

    # Count categories for filter badges
    cat_counts = {}
    for s in raw_schemes:
        cat = categorize_scheme_record(s)
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    return {
        "status": "SUCCESS",
        "total": total,
        "category_counts": cat_counts,
        "schemes": paginated
    }
    cat_counts = {}
    for s in raw_schemes:
        cat = categorize_scheme_record(s)
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    return {
        "status": "SUCCESS",
        "total": total,
        "category_counts": cat_counts,
        "schemes": paginated
    }


@app.get("/api/schemes/{scheme_id}")
def api_get_scheme_detail(scheme_id: int):
    """Returns full details of a specific cleaned scheme."""
    from backend.app.ingestion.mysql_scheme_loader import MySQLSchemeLoader
    loader = MySQLSchemeLoader()
    scheme = loader.get_scheme_by_id(scheme_id)
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")
    scheme["computed_category"] = categorize_scheme_record(scheme)
    return {
        "status": "SUCCESS",
        "scheme": scheme
    }


@app.get("/api/departments")
def api_get_departments():
    """Returns unique departments list across all active schemes."""
    from backend.app.ingestion.mysql_scheme_loader import MySQLSchemeLoader
    loader = MySQLSchemeLoader()
    schemes = loader.load_clean_schemes()
    depts = sorted(list(set(s.get("department") for s in schemes if s.get("department"))))
    return {
        "status": "SUCCESS",
        "departments": depts
    }


@app.get("/api/stats")
def api_get_stats(db: Session = Depends(get_db)):
    """Returns overview statistics of scraped pages, PDFs, and cleaned schemes."""
    stats = get_stats(db)
    if scraper_running:
        stats["last_scrape"]["status"] = "RUNNING"

    # Query cleaned schemes count from database
    try:
        from scheme_cleaner.database import SessionLocal as CleanedSession, SchemeModel
        c_db = CleanedSession()
        stats["total_cleaned_schemes"] = c_db.query(SchemeModel).count()
        c_db.close()
    except Exception:
        stats["total_cleaned_schemes"] = 0

    return stats


@app.post("/api/clean")
def api_trigger_clean():
    """Triggers the SchemeCleaner Pipeline to re-clean and synchronize all scraped schemes."""
    try:
        from scheme_cleaner.pipeline import SchemeDataPipeline
        pipeline = SchemeDataPipeline()
        res = pipeline.run_pipeline()
        return {
            "status": "SUCCESS",
            "message": f"Pipeline completed! Cleaned {res.get('cleaned_records', 0)} schemes, {res.get('total_schemes_exported', 0)} total live in DB and UI."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
            "page_type": getattr(p, "page_type", "GENERAL") or "GENERAL",
            "parent_url": getattr(p, "parent_url", None),
            "target_redirect_url": getattr(p, "target_redirect_url", None),
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
        "page_type": getattr(page, "page_type", "GENERAL") or "GENERAL",
        "parent_url": getattr(page, "parent_url", None),
        "target_redirect_url": getattr(page, "target_redirect_url", None),
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
