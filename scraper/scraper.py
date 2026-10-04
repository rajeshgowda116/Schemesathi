import os
import sys
import time
import logging
from datetime import datetime
from typing import List, Set, Dict, Optional, Callable, Any
from urllib.parse import urlparse

from scraper.config import TARGET_URLS, PDF_DIR, MAX_DEPTH, MAX_PAGES_PER_DOMAIN, DEFAULT_TIMEOUT
from scraper.database import (
    SessionLocal, init_db, save_scraped_page, save_scraped_pdf, ScrapeRunLog
)
from scraper.fetcher import fetch_resource
from scraper.parser import parse_html_page, is_pdf_url, sanitize_filename

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SchemesathiScraper")


class WebScraper:
    def __init__(self, target_urls: List[str] = None, max_depth: int = MAX_DEPTH, max_pages_per_domain: int = MAX_PAGES_PER_DOMAIN):
        self.target_urls = target_urls or TARGET_URLS
        self.max_depth = max_depth
        self.max_pages_per_domain = max_pages_per_domain
        self.visited_urls: Set[str] = set()
        self.downloaded_pdf_urls: Set[str] = set()
        self.log_messages: List[str] = []

    def log(self, message: str, level: str = "INFO"):
        log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}"
        self.log_messages.append(log_entry)
        if level == "ERROR":
            logger.error(message)
        else:
            logger.info(message)

    def run(self, progress_callback: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        init_db()
        db = SessionLocal()

        # Create ScrapeRunLog entry
        run_log = ScrapeRunLog(started_at=datetime.utcnow(), status="RUNNING")
        db.add(run_log)
        db.commit()
        db.refresh(run_log)

        total_pages = 0
        total_pdfs = 0

        self.log(f"Starting Scraper Job across {len(self.target_urls)} target seed URLs")
        if progress_callback:
            progress_callback(f"Starting scraper for URLs: {', '.join(self.target_urls)}")

        try:
            for seed_url in self.target_urls:
                domain = urlparse(seed_url).netloc
                self.log(f"--- Processing Domain / Seed URL: {seed_url} ---")
                
                # Queue item format: (url, depth)
                queue = [(seed_url, 0)]
                domain_page_count = 0

                while queue:
                    current_url, depth = queue.pop(0)

                    if current_url in self.visited_urls:
                        continue
                    if domain_page_count >= self.max_pages_per_domain:
                        self.log(f"Reached max pages limit ({self.max_pages_per_domain}) for domain {domain}")
                        break

                    self.visited_urls.add(current_url)

                    # Check if this URL is a PDF directly
                    if is_pdf_url(current_url):
                        pdf_record = self._download_pdf(db, current_url, page_url=seed_url)
                        if pdf_record:
                            total_pdfs += 1
                        continue

                    # Fetch HTML Page
                    self.log(f"Scraping [Depth {depth}]: {current_url}")
                    if progress_callback:
                        progress_callback(f"Scraping: {current_url}")

                    try:
                        status_code, content, content_type, final_url = fetch_resource(current_url, timeout=DEFAULT_TIMEOUT)

                        if 'application/pdf' in content_type.lower():
                            pdf_record = self._download_pdf(db, current_url, page_url=seed_url, content_bytes=content)
                            if pdf_record:
                                total_pdfs += 1
                            continue

                        # Decode HTML content
                        html_text = content.decode('utf-8', errors='ignore')
                        parsed_data = parse_html_page(final_url, html_text)

                        # Download PDFs found on page
                        pdf_count_for_page = 0
                        for pdf_link in parsed_data["pdf_links"]:
                            if pdf_link not in self.downloaded_pdf_urls:
                                pdf_rec = self._download_pdf(db, pdf_link, page_url=final_url)
                                if pdf_rec:
                                    total_pdfs += 1
                                    pdf_count_for_page += 1

                        # Save HTML page raw data into SQLite DB
                        page_rec = save_scraped_page(
                            db_session=db,
                            url=final_url,
                            domain=domain,
                            title=parsed_data["title"],
                            content_text=parsed_data["content_text"],
                            raw_html=html_text,
                            meta_description=parsed_data["meta_description"],
                            http_status=status_code,
                            pdf_count=len(parsed_data["pdf_links"]),
                            links_count=len(parsed_data["all_links"]),
                            status="SUCCESS"
                        )
                        total_pages += 1
                        domain_page_count += 1

                        # Queue internal links for next depth level crawl
                        if depth < self.max_depth:
                            for link in parsed_data["all_links"]:
                                # Stay on same domain or trusted domains
                                link_domain = urlparse(link).netloc
                                if link_domain == domain and link not in self.visited_urls:
                                    queue.append((link, depth + 1))

                    except Exception as e:
                        err_msg = f"Failed to scrape {current_url}: {str(e)}"
                        self.log(err_msg, level="ERROR")
                        save_scraped_page(
                            db_session=db,
                            url=current_url,
                            domain=domain,
                            title="Error Scraping Page",
                            content_text="",
                            raw_html="",
                            http_status=500,
                            status="ERROR",
                            error_message=str(e)
                        )

            # Update Run Log
            run_log.ended_at = datetime.utcnow()
            run_log.pages_scraped = total_pages
            run_log.pdfs_downloaded = total_pdfs
            run_log.status = "COMPLETED"
            run_log.log_summary = "\n".join(self.log_messages[-30:])  # Last 30 log lines
            db.commit()

            self.log(f"Scraper finished cleanly! Pages scraped: {total_pages}, PDFs downloaded: {total_pdfs}")
            return {
                "pages_scraped": total_pages,
                "pdfs_downloaded": total_pdfs,
                "status": "COMPLETED"
            }

        except Exception as global_err:
            run_log.ended_at = datetime.utcnow()
            run_log.status = "FAILED"
            run_log.log_summary = f"Global Scraper Failure: {str(global_err)}\n" + "\n".join(self.log_messages[-10:])
            db.commit()
            self.log(f"Global Scraper Failure: {global_err}", level="ERROR")
            raise global_err
        finally:
            db.close()

    def _download_pdf(self, db, pdf_url: str, page_url: str, content_bytes: Optional[bytes] = None) -> Optional[Any]:
        """Downloads a PDF file and saves it to SCRAPED PDF folder and DB."""
        if pdf_url in self.downloaded_pdf_urls:
            return None

        self.downloaded_pdf_urls.add(pdf_url)
        self.log(f"Downloading PDF: {pdf_url}")

        try:
            if not content_bytes:
                status_code, content_bytes, content_type, _ = fetch_resource(pdf_url, timeout=DEFAULT_TIMEOUT)
                if status_code != 200 or len(content_bytes) < 100:
                    raise ValueError(f"HTTP Status {status_code}, content size {len(content_bytes)} bytes")

            # Determine clean file name
            parsed_path = urlparse(pdf_url).path
            raw_filename = os.path.basename(parsed_path) or "document"
            file_name = sanitize_filename(raw_filename)

            # Prevent overwriting existing file with same name
            save_path = PDF_DIR / file_name
            counter = 1
            stem = save_path.stem
            while save_path.exists():
                file_name = f"{stem}_{counter}.pdf"
                save_path = PDF_DIR / file_name
                counter += 1

            # Write file to disk in SCRAPED PDF folder
            with open(save_path, "wb") as f:
                f.write(content_bytes)

            file_size = len(content_bytes)
            self.log(f"Saved PDF to '{save_path.name}' ({file_size} bytes)")

            # Record in SQLite Database
            pdf_rec = save_scraped_pdf(
                db_session=db,
                pdf_url=pdf_url,
                page_url=page_url,
                file_name=file_name,
                file_path=str(save_path.resolve()),
                file_size_bytes=file_size,
                status="DOWNLOADED"
            )
            return pdf_rec

        except Exception as e:
            err_msg = f"Failed downloading PDF {pdf_url}: {str(e)}"
            self.log(err_msg, level="ERROR")
            save_scraped_pdf(
                db_session=db,
                pdf_url=pdf_url,
                page_url=page_url,
                file_name=os.path.basename(pdf_url),
                file_path="",
                file_size_bytes=0,
                status="FAILED",
                error_message=str(e)
            )
            return None


if __name__ == "__main__":
    scraper = WebScraper()
    results = scraper.run()
    print("Scraper Execution Results:", results)
