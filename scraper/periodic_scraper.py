import os
import sys
import time
import heapq
import hashlib
import logging
import argparse
from datetime import datetime
from typing import List, Dict, Set, Optional, Callable, Any, Tuple
from urllib.parse import urlparse

from scraper.config import TARGET_URLS, PDF_DIR, MAX_DEPTH, MAX_PAGES_PER_DOMAIN, DEFAULT_TIMEOUT
from scraper.database import (
    SessionLocal, init_db, save_scraped_page, save_scraped_pdf, ScrapeRunLog, ScrapedPage
)
from scraper.fetcher import fetch_resource
from scraper.parser import parse_html_page, is_pdf_url, sanitize_filename
from scraper.scraper import is_allowed_domain

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PeriodicScraper")

# Default 24 Hours interval in seconds
CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # 86400 seconds


class PeriodicIncrementalScraper:
    def __init__(
        self,
        target_urls: List[str] = None,
        max_depth: int = MAX_DEPTH,
        max_pages_per_domain: int = MAX_PAGES_PER_DOMAIN,
        interval_seconds: int = CHECK_INTERVAL_SECONDS
    ):
        self.target_urls = target_urls or TARGET_URLS
        self.max_depth = max_depth
        self.max_pages_per_domain = max_pages_per_domain
        self.interval_seconds = interval_seconds
        self.downloaded_pdf_urls: Set[str] = set()
        self.log_messages: List[str] = []

    def log(self, message: str, level: str = "INFO"):
        log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}"
        self.log_messages.append(log_entry)
        if level == "ERROR":
            logger.error(message)
        else:
            logger.info(message)

    def compute_hash(self, title: str, content_text: str) -> str:
        """Computes SHA-256 hash of page content for delta detection."""
        payload = f"{title.strip()}\n{content_text.strip()}"
        return hashlib.sha256(payload.encode('utf-8', errors='ignore')).hexdigest()

    def run_single_check_cycle(self, progress_callback: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        """
        Runs one cycle of incremental scraping:
        Only updates SQL row data if page content has changed or is new!
        """
        init_db()
        db = SessionLocal()

        run_log = ScrapeRunLog(started_at=datetime.utcnow(), status="RUNNING")
        db.add(run_log)
        db.commit()
        db.refresh(run_log)

        pages_checked = 0
        pages_updated = 0
        pages_unchanged = 0
        pdfs_downloaded = 0
        visited_urls: Set[str] = set()
        counter = 0

        self.log(f"🔄 Starting 24h Incremental Check Cycle across {len(self.target_urls)} portals...")

        try:
            for seed_url in self.target_urls:
                seed_domain = urlparse(seed_url).netloc
                self.log(f"--- Checking Domain: {seed_url} ---")
                queue: List[Tuple[int, int, int, str, Optional[str], Dict[str, Any]]] = []
                counter += 1
                heapq.heappush(queue, (2, 0, counter, seed_url, None, {"type": "home", "label": "Seed Homepage"}))
                domain_page_count = 0

                while queue:
                    if domain_page_count >= self.max_pages_per_domain:
                        break

                    priority, depth, _, current_url, parent_url, context = heapq.heappop(queue)

                    if current_url in visited_urls:
                        continue

                    visited_urls.add(current_url)

                    # Handle direct PDF URLs
                    if is_pdf_url(current_url):
                        pdf_rec = self._download_pdf_if_new(db, current_url, page_url=parent_url or seed_url)
                        if pdf_rec:
                            pdfs_downloaded += 1
                        continue

                    ctx_label = context.get("label", "Page")
                    ctx_type = context.get("type", "general")
                    msg = f"Checking [Depth {depth}, Prio {priority}]: {current_url} ({ctx_label})"
                    self.log(msg)
                    if progress_callback:
                        progress_callback(msg)

                    try:
                        status_code, content, content_type, final_url = fetch_resource(current_url, timeout=DEFAULT_TIMEOUT)

                        target_redirect_url = None
                        if final_url and final_url != current_url:
                            target_redirect_url = final_url
                            visited_urls.add(final_url)
                            self.log(f"  ↪️ Redirect followed: {current_url} -> {final_url}")

                        if 'application/pdf' in content_type.lower():
                            pdf_rec = self._download_pdf_if_new(db, final_url, page_url=parent_url or current_url, content_bytes=content)
                            if pdf_rec:
                                pdfs_downloaded += 1
                            continue

                        # Filter out non-HTML content (e.g. css/images/fonts)
                        if content_type and not any(ct in content_type.lower() for ct in ['text/html', 'text/plain', 'application/xhtml']):
                            continue

                        html_text = content.decode('utf-8', errors='ignore')
                        parsed_data = parse_html_page(final_url, html_text)

                        # Determine actual page type
                        page_type = parsed_data["page_type"]
                        if ctx_type == "application_form" and page_type == "GENERAL":
                            page_type = "APPLICATION_FORM"
                        elif ctx_type == "scheme" and page_type == "GENERAL":
                            page_type = "SCHEME"

                        # Check for new PDFs on page
                        for pdf_link in parsed_data["pdf_links"]:
                            pdf_rec = self._download_pdf_if_new(db, pdf_link, page_url=final_url)
                            if pdf_rec:
                                pdfs_downloaded += 1

                        # Calculate content hash
                        content_hash = self.compute_hash(parsed_data["title"], parsed_data["content_text"])

                        # Check if DB entry exists & hash matches
                        existing_page = db.query(ScrapedPage).filter(ScrapedPage.url == final_url).first()

                        if existing_page and existing_page.content_hash == content_hash:
                            pages_unchanged += 1
                            pages_checked += 1
                            self.log(f"  [NO CHANGE] Content unchanged for: {final_url}")
                        else:
                            page_domain = urlparse(final_url).netloc
                            page_rec, was_updated = save_scraped_page(
                                db_session=db,
                                url=final_url,
                                domain=page_domain,
                                title=parsed_data["title"],
                                content_text=parsed_data["content_text"],
                                raw_html=html_text,
                                meta_description=parsed_data["meta_description"],
                                content_hash=content_hash,
                                page_type=page_type,
                                parent_url=parent_url,
                                target_redirect_url=target_redirect_url,
                                http_status=status_code,
                                pdf_count=len(parsed_data["pdf_links"]),
                                links_count=len(parsed_data["all_links"]),
                                status="SUCCESS",
                                only_if_updated=True
                            )
                            pages_checked += 1
                            if was_updated:
                                pages_updated += 1
                                action_type = "UPDATED" if existing_page else "NEW ENTRY"
                                self.log(f"  [{action_type}] Saved updated row to SQL: {final_url}")

                                # >>> AUTOMATIC CLEANING HOOK <<<
                                try:
                                    from scheme_cleaner.pipeline import SchemeDataPipeline
                                    cleaner_pipe = SchemeDataPipeline()
                                    raw_item = {
                                        "scheme_name": parsed_data["title"],
                                        "title": parsed_data["title"],
                                        "state": "Karnataka",
                                        "department": cleaner_pipe.infer_department(page_domain, parsed_data["title"]),
                                        "official_url": final_url,
                                        "content_text": parsed_data["content_text"],
                                        "raw_html": html_text,
                                        "source_date": datetime.utcnow().strftime("%Y-%m-%d")
                                    }
                                    cleaned_scheme, is_new_scheme = cleaner_pipe.clean_and_save_item(raw_item)
                                    if cleaned_scheme:
                                        self.log(f"  ✨ [AUTO-CLEANED] Scheme '{parsed_data['title']}' structured and saved to MySQL/Cleaned DB!")
                                except Exception as clean_err:
                                    self.log(f"  ⚠️ Error auto-cleaning scheme for {final_url}: {clean_err}", level="ERROR")

                        domain_page_count += 1

                        # Queue links for next depth crawl (Home -> Scheme -> Application Form -> Redirects)
                        if depth < self.max_depth:
                            next_depth = depth + 1

                            for app_link in parsed_data["application_links"]:
                                app_url = app_link["url"]
                                if app_url not in visited_urls and is_allowed_domain(app_url, seed_domain, is_scheme_or_app=True):
                                    counter += 1
                                    heapq.heappush(queue, (
                                        0, next_depth, counter, app_url, final_url,
                                        {"type": "application_form", "label": app_link["text"]}
                                    ))

                            for sch_link in parsed_data["scheme_links"]:
                                sch_url = sch_link["url"]
                                if sch_url not in visited_urls and is_allowed_domain(sch_url, seed_domain, is_scheme_or_app=True):
                                    counter += 1
                                    heapq.heappush(queue, (
                                        1, next_depth, counter, sch_url, final_url,
                                        {"type": "scheme", "label": sch_link["text"]}
                                    ))

                            for red_url in parsed_data["redirect_links"]:
                                if red_url not in visited_urls and is_allowed_domain(red_url, seed_domain, is_scheme_or_app=True):
                                    counter += 1
                                    heapq.heappush(queue, (
                                        0, next_depth, counter, red_url, final_url,
                                        {"type": "redirect", "label": "Portal Redirection"}
                                    ))

                            for gen_url in parsed_data["all_links"]:
                                if gen_url not in visited_urls and is_allowed_domain(gen_url, seed_domain, is_scheme_or_app=False):
                                    counter += 1
                                    heapq.heappush(queue, (
                                        3, next_depth, counter, gen_url, final_url,
                                        {"type": "general", "label": "Internal Page"}
                                    ))

                    except Exception as page_err:
                        self.log(f"Error checking {current_url}: {page_err}", level="ERROR")

            # Synchronize cleaned JSON export if any pages were updated
            if pages_updated > 0:
                try:
                    from scheme_cleaner.pipeline import SchemeDataPipeline
                    exported_total = SchemeDataPipeline().export_cleaned_schemes_json()
                    self.log(f"✨ Synchronized cleaned_schemes.json ({exported_total} total schemes live for frontend)")
                except Exception as export_err:
                    self.log(f"⚠️ Error exporting cleaned JSON: {export_err}", level="ERROR")

            # Finalize run log
            run_log.ended_at = datetime.utcnow()
            run_log.pages_scraped = pages_updated
            run_log.pdfs_downloaded = pdfs_downloaded
            run_log.status = "COMPLETED"
            run_log.log_summary = (
                f"24h Incremental Scrape Summary:\n"
                f"- Total Pages Checked: {pages_checked}\n"
                f"- Pages Updated/Inserted in SQL: {pages_updated}\n"
                f"- Pages Unchanged (Skipped): {pages_unchanged}\n"
                f"- New PDFs Downloaded: {pdfs_downloaded}\n\n"
                + "\n".join(self.log_messages[-25:])
            )
            db.commit()

            self.log(
                f"✅ 24h Cycle Complete! Checked: {pages_checked}, "
                f"Updated in SQL: {pages_updated}, Unchanged: {pages_unchanged}, "
                f"New PDFs: {pdfs_downloaded}"
            )
            return {
                "pages_checked": pages_checked,
                "pages_updated": pages_updated,
                "pages_unchanged": pages_unchanged,
                "pdfs_downloaded": pdfs_downloaded
            }

        except Exception as global_err:
            run_log.ended_at = datetime.utcnow()
            run_log.status = "FAILED"
            run_log.log_summary = f"Failure: {global_err}\n" + "\n".join(self.log_messages[-10:])
            db.commit()
            self.log(f"Cycle Failure: {global_err}", level="ERROR")
            raise global_err
        finally:
            db.close()

    def start_periodic_scheduler(self):
        """Runs continuous loop checking for updates every 24 hours."""
        self.log(f"🚀 Periodic 24-Hour Scraper Daemon Started. Interval: {self.interval_seconds} seconds (24 hours)")
        try:
            while True:
                start_time = datetime.now()
                self.log(f"⏰ Initiating 24-hour scheduled check run at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

                try:
                    stats = self.run_single_check_cycle()
                    self.log(f"Cycle stats: {stats}")
                except Exception as cycle_err:
                    self.log(f"Error during cycle: {cycle_err}", level="ERROR")

                next_run = datetime.now().timestamp() + self.interval_seconds
                next_run_str = datetime.fromtimestamp(next_run).strftime('%Y-%m-%d %H:%M:%S')
                self.log(f"💤 Sleeping for 24 hours. Next scheduled run: {next_run_str}")
                
                time.sleep(self.interval_seconds)
        except KeyboardInterrupt:
            self.log("🛑 Periodic Scraper Daemon stopped by user.")

    def _download_pdf_if_new(self, db, pdf_url: str, page_url: str, content_bytes: Optional[bytes] = None) -> Optional[Any]:
        """Downloads PDF only if it does not already exist in DB and disk."""
        if pdf_url in self.downloaded_pdf_urls:
            return None

        # Check DB if PDF url already saved
        from scraper.database import ScrapedPDF
        existing_pdf = db.query(ScrapedPDF).filter(ScrapedPDF.pdf_url == pdf_url).first()
        if existing_pdf and existing_pdf.file_path and os.path.exists(existing_pdf.file_path):
            self.downloaded_pdf_urls.add(pdf_url)
            return None

        self.downloaded_pdf_urls.add(pdf_url)
        self.log(f"📥 New PDF detected! Downloading: {pdf_url}")

        try:
            if not content_bytes:
                status_code, content_bytes, content_type, _ = fetch_resource(pdf_url, timeout=DEFAULT_TIMEOUT)
                if status_code != 200 or len(content_bytes) < 100:
                    raise ValueError(f"HTTP Status {status_code}, content size {len(content_bytes)} bytes")

            parsed_path = urlparse(pdf_url).path
            raw_filename = os.path.basename(parsed_path) or "document"
            file_name = sanitize_filename(raw_filename)

            save_path = PDF_DIR / file_name
            counter = 1
            stem = save_path.stem
            while save_path.exists():
                file_name = f"{stem}_{counter}.pdf"
                save_path = PDF_DIR / file_name
                counter += 1

            with open(save_path, "wb") as f:
                f.write(content_bytes)

            file_size = len(content_bytes)
            self.log(f"  Saved PDF to 'scraper/SCRAPED PDF/{save_path.name}' ({file_size} bytes)")

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
            self.log(f"Failed downloading PDF {pdf_url}: {e}", level="ERROR")
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
    parser = argparse.ArgumentParser(description="24-Hour Periodic Incremental Web Scraper")
    parser.add_argument("--run-once", action="store_true", help="Run a single 24-hour incremental check cycle and exit")
    parser.add_argument("--interval", type=int, default=CHECK_INTERVAL_SECONDS, help="Check interval in seconds (default: 86400 / 24 hours)")
    args = parser.parse_args()

    scraper = PeriodicIncrementalScraper(interval_seconds=args.interval)
    if args.run_once:
        print("Running single incremental check cycle...")
        res = scraper.run_single_check_cycle()
        print("Cycle Results:", res)
    else:
        scraper.start_periodic_scheduler()
