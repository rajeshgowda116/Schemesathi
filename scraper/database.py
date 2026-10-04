from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from scraper.config import SQLALCHEMY_DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ScrapedPage(Base):
    __tablename__ = "scraped_pages"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True, nullable=False)
    domain = Column(String, index=True)
    title = Column(String)
    content_text = Column(Text)
    raw_html = Column(Text)
    meta_description = Column(Text)
    content_hash = Column(String, index=True, nullable=True)
    http_status = Column(Integer, default=200)
    pdf_count = Column(Integer, default=0)
    links_count = Column(Integer, default=0)
    status = Column(String, default="SUCCESS")  # SUCCESS, ERROR
    error_message = Column(Text, nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)

    pdfs = relationship("ScrapedPDF", back_populates="page", cascade="all, delete-orphan")


class ScrapedPDF(Base):
    __tablename__ = "scraped_pdfs"

    id = Column(Integer, primary_key=True, index=True)
    page_id = Column(Integer, ForeignKey("scraped_pages.id"), nullable=True)
    page_url = Column(String)
    pdf_url = Column(String, unique=True, index=True, nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size_bytes = Column(Integer, default=0)
    downloaded_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="DOWNLOADED")  # DOWNLOADED, FAILED
    error_message = Column(Text, nullable=True)

    page = relationship("ScrapedPage", back_populates="pdfs")


class ScrapeRunLog(Base):
    __tablename__ = "scrape_run_logs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    pages_scraped = Column(Integer, default=0)
    pdfs_downloaded = Column(Integer, default=0)
    status = Column(String, default="RUNNING")  # RUNNING, COMPLETED, FAILED
    log_summary = Column(Text, nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)
    # Ensure content_hash column exists on SQLite table
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE scraped_pages ADD COLUMN content_hash VARCHAR;"))
            conn.commit()
        except Exception:
            pass  # Column already exists


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_scraped_page(
    db_session,
    url: str,
    domain: str,
    title: str,
    content_text: str,
    raw_html: str,
    meta_description: str = "",
    content_hash: str = "",
    http_status: int = 200,
    pdf_count: int = 0,
    links_count: int = 0,
    status: str = "SUCCESS",
    error_message: str = None,
    only_if_updated: bool = False
) -> Tuple[ScrapedPage, bool]:
    """
    Saves or updates a scraped page.
    If only_if_updated is True, skips updating if content_hash matches existing record.
    Returns: (ScrapedPage record, is_new_or_updated: bool)
    """
    existing = db_session.query(ScrapedPage).filter(ScrapedPage.url == url).first()
    if existing:
        if only_if_updated and existing.content_hash and existing.content_hash == content_hash:
            # Content is identical, skip updating row data in SQL
            return existing, False

        existing.title = title
        existing.content_text = content_text
        existing.raw_html = raw_html
        existing.meta_description = meta_description
        existing.content_hash = content_hash
        existing.http_status = http_status
        existing.pdf_count = pdf_count
        existing.links_count = links_count
        existing.status = status
        existing.error_message = error_message
        existing.scraped_at = datetime.utcnow()
        db_session.commit()
        db_session.refresh(existing)
        return existing, True
    else:
        page = ScrapedPage(
            url=url,
            domain=domain,
            title=title,
            content_text=content_text,
            raw_html=raw_html,
            meta_description=meta_description,
            content_hash=content_hash,
            http_status=http_status,
            pdf_count=pdf_count,
            links_count=links_count,
            status=status,
            error_message=error_message,
            scraped_at=datetime.utcnow()
        )
        db_session.add(page)
        db_session.commit()
        db_session.refresh(page)
        return page, True


def save_scraped_pdf(
    db_session,
    pdf_url: str,
    page_url: str,
    file_name: str,
    file_path: str,
    file_size_bytes: int = 0,
    status: str = "DOWNLOADED",
    error_message: str = None,
    page_id: Optional[int] = None
) -> ScrapedPDF:
    existing = db_session.query(ScrapedPDF).filter(ScrapedPDF.pdf_url == pdf_url).first()
    if existing:
        existing.page_url = page_url
        existing.file_name = file_name
        existing.file_path = file_path
        existing.file_size_bytes = file_size_bytes
        existing.status = status
        existing.error_message = error_message
        existing.downloaded_at = datetime.utcnow()
        if page_id:
            existing.page_id = page_id
        db_session.commit()
        db_session.refresh(existing)
        return existing
    else:
        pdf_rec = ScrapedPDF(
            pdf_url=pdf_url,
            page_url=page_url,
            file_name=file_name,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            status=status,
            error_message=error_message,
            page_id=page_id,
            downloaded_at=datetime.utcnow()
        )
        db_session.add(pdf_rec)
        db_session.commit()
        db_session.refresh(pdf_rec)
        return pdf_rec


def get_stats(db_session) -> Dict[str, Any]:
    total_pages = db_session.query(ScrapedPage).count()
    successful_pages = db_session.query(ScrapedPage).filter(ScrapedPage.status == "SUCCESS").count()
    failed_pages = db_session.query(ScrapedPage).filter(ScrapedPage.status == "ERROR").count()
    total_pdfs = db_session.query(ScrapedPDF).filter(ScrapedPDF.status == "DOWNLOADED").count()
    
    # Calculate total PDF storage size
    pdfs = db_session.query(ScrapedPDF).all()
    total_pdf_size = sum(p.file_size_bytes or 0 for p in pdfs)

    # Last scrape run
    last_log = db_session.query(ScrapeRunLog).order_by(ScrapeRunLog.id.desc()).first()

    return {
        "total_pages_scraped": total_pages,
        "successful_pages": successful_pages,
        "failed_pages": failed_pages,
        "total_pdfs": total_pdfs,
        "total_pdf_size_bytes": total_pdf_size,
        "total_pdf_size_formatted": format_bytes(total_pdf_size),
        "last_scrape": {
            "id": last_log.id if last_log else None,
            "started_at": last_log.started_at.isoformat() if last_log and last_log.started_at else None,
            "ended_at": last_log.ended_at.isoformat() if last_log and last_log.ended_at else None,
            "status": last_log.status if last_log else "NEVER_RUN",
            "pages_scraped": last_log.pages_scraped if last_log else 0,
            "pdfs_downloaded": last_log.pdfs_downloaded if last_log else 0,
            "summary": last_log.log_summary if last_log else ""
        }
    }


def format_bytes(bytes_size: int) -> str:
    if bytes_size == 0:
        return "0 B"
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    i = 0
    size = float(bytes_size)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.2f} {units[i]}"
