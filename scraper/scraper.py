import os
import sys
import time
import heapq
import logging
from datetime import datetime
from typing import List, Set, Dict, Optional, Callable, Any, Tuple
from urllib.parse import urlparse

from scraper.config import (
    TARGET_URLS, PDF_DIR, MAX_DEPTH, MAX_PAGES_PER_DOMAIN,
    DEFAULT_TIMEOUT, ALLOWED_PORTAL_DOMAINS
)
from scraper.database import (
    SessionLocal, init_db, save_scraped_page, save_scraped_pdf, ScrapeRunLog
)
from scraper.fetcher import fetch_resource
from scraper.parser import parse_html_page, is_pdf_url, sanitize_filename

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SchemesathiScraper")


def is_allowed_domain(url: str, seed_domain: str, is_scheme_or_app: bool = False) -> bool:
    """
    Checks if a target URL's domain is allowed for crawling.
    - Allows internal pages of seed domain and its subdomains.
    - Allows all Karnataka Government portals (*.karnataka.gov.in).
    - If link points to a scheme, application form, or redirect, allows trusted national/state portals.
    """
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    seed_lower = seed_domain.lower()

    if not netloc:
        return False

    # 1. Exact match or subdomain
    if netloc == seed_lower or netloc.endswith(f".{seed_lower}"):
        return True

    # 2. Both belong to Karnataka Government domain ecosystem
    if "karnataka.gov.in" in seed_lower and "karnataka.gov.in" in netloc:
        return True

    # 3. Scheme links, application forms, and official redirects to trusted government portals
    if is_scheme_or_app:
        for portal in ALLOWED_PORTAL_DOMAINS:
            if netloc == portal or netloc.endswith(f".{portal}"):
                return True

    return False


class WebScraper:
    """
    Intelligent Deep Web Scraper for Karnataka Government Schemes.
    Follows multi-level hierarchy:
    Home Page -> Scheme Listing -> Scheme Detail -> Application Form Pages & Direct Application Redirects.
    """

    def __init__(
        self,
        target_urls: List[str] = None,
        max_depth: int = MAX_DEPTH,
        max_pages_per_domain: int = MAX_PAGES_PER_DOMAIN
    ):
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

        run_log = ScrapeRunLog(started_at=datetime.utcnow(), status="RUNNING")
        db.add(run_log)
        db.commit()
        db.refresh(run_log)

        total_pages = 0
        total_pdfs = 0
        counter = 0  # Tie-breaker for heap queue

        self.log(f"Starting Multi-Level Deep Scraper across {len(self.target_urls)} seed URLs (Max Depth: {self.max_depth}, Cap/Domain: {self.max_pages_per_domain})")
        if progress_callback:
            progress_callback(f"Starting multi-level scraper for: {', '.join(self.target_urls)}")

        try:
            for seed_url in self.target_urls:
                seed_domain = urlparse(seed_url).netloc
                self.log(f"--- Processing Seed Portal: {seed_url} ({seed_domain}) ---")

                # Priority Queue item format:
                # (priority, depth, counter, current_url, parent_url, context_dict)
                # Priorities:
                #   0 = Application Forms / Apply Links / Direct Redirects (TOP)
                #   1 = Individual Scheme Detail Pages
                #   2 = Scheme Listings / Department Categories
                #   3 = Other Internal Portal Pages
                queue: List[Tuple[int, int, int, str, Optional[str], Dict[str, Any]]] = []
                counter += 1
                heapq.heappush(queue, (2, 0, counter, seed_url, None, {"type": "home", "label": "Seed Homepage"}))

                domain_page_count = 0

                while queue:
                    if domain_page_count >= self.max_pages_per_domain:
                        self.log(f"Reached domain page limit ({self.max_pages_per_domain}) for seed {seed_domain}")
                        break

                    priority, depth, _, current_url, parent_url, context = heapq.heappop(queue)

                    if current_url in self.visited_urls:
                        continue

                    self.visited_urls.add(current_url)

                    # Handle direct PDF URLs
                    if is_pdf_url(current_url):
                        pdf_record = self._download_pdf(db, current_url, page_url=parent_url or seed_url)
                        if pdf_record:
                            total_pdfs += 1
                        continue

                    ctx_label = context.get("label", "Page")
                    ctx_type = context.get("type", "general")
                    
                    if ctx_type == "application_form":
                        tag = "📝 [APP FORM]"
                    elif ctx_type == "scheme":
                        tag = "🏛️ [SCHEME]"
                    elif ctx_type == "redirect":
                        tag = "↪️ [REDIRECT]"
                    else:
                        tag = "🌐 [PAGE]"

                    msg = f"{tag} Scraping (Depth {depth}, Prio {priority}): {current_url} | Context: {ctx_label}"
                    self.log(msg)
                    if progress_callback:
                        progress_callback(f"{tag} {current_url}")

                    try:
                        status_code, content, content_type, final_url = fetch_resource(current_url, timeout=DEFAULT_TIMEOUT)

                        # Detect and log redirects
                        target_redirect_url = None
                        if final_url and final_url != current_url:
                            target_redirect_url = final_url
                            self.visited_urls.add(final_url)
                            self.log(f"  ↪️ Redirect followed: {current_url} -> {final_url}")

                        # Check if response is a PDF directly
                        if 'application/pdf' in content_type.lower():
                            pdf_record = self._download_pdf(db, final_url, page_url=parent_url or current_url, content_bytes=content)
                            if pdf_record:
                                total_pdfs += 1
                            continue

                        # Strict filter: skip non-HTML content (css, js, images, fonts, binaries)
                        if content_type and not any(ct in content_type.lower() for ct in ['text/html', 'text/plain', 'application/xhtml']):
                            continue

                        html_text = content.decode('utf-8', errors='ignore')
                        parsed_data = parse_html_page(final_url, html_text)

                        # Determine actual page type:
                        # Prioritize context type if it was an application form or scheme link
                        page_type = parsed_data["page_type"]
                        if ctx_type == "application_form" and page_type == "GENERAL":
                            page_type = "APPLICATION_FORM"
                        elif ctx_type == "scheme" and page_type == "GENERAL":
                            page_type = "SCHEME"

                        # Download all PDFs / application documents discovered on this page
                        for pdf_link in parsed_data["pdf_links"]:
                            if pdf_link not in self.downloaded_pdf_urls:
                                pdf_rec = self._download_pdf(db, pdf_link, page_url=final_url)
                                if pdf_rec:
                                    total_pdfs += 1

                        # Save HTML page into Database
                        page_domain = urlparse(final_url).netloc
                        save_scraped_page(
                            db_session=db,
                            url=final_url,
                            domain=page_domain,
                            title=parsed_data["title"],
                            content_text=parsed_data["content_text"],
                            raw_html=html_text,
                            meta_description=parsed_data["meta_description"],
                            page_type=page_type,
                            parent_url=parent_url,
                            target_redirect_url=target_redirect_url,
                            http_status=status_code,
                            pdf_count=len(parsed_data["pdf_links"]),
                            links_count=len(parsed_data["all_links"]),
                            status="SUCCESS"
                        )
                        total_pages += 1
                        domain_page_count += 1

                        # ============================================================
                        # DISCOVER & QUEUE NEXT LEVEL:
                        # Flow: Home -> Scheme Page -> Application Form of Scheme -> Redirects
                        # ============================================================
                        if depth < self.max_depth:
                            next_depth = depth + 1

                            # 1. High Priority: Application Form Links & Action Endpoints (Priority 0)
                            for app_link in parsed_data["application_links"]:
                                app_url = app_link["url"]
                                if app_url not in self.visited_urls:
                                    if is_allowed_domain(app_url, seed_domain, is_scheme_or_app=True):
                                        counter += 1
                                        heapq.heappush(queue, (
                                            0, next_depth, counter, app_url, final_url,
                                            {"type": "application_form", "label": app_link["text"]}
                                        ))

                            # 2. Priority: Scheme Detail Links (Priority 1)
                            for sch_link in parsed_data["scheme_links"]:
                                sch_url = sch_link["url"]
                                if sch_url not in self.visited_urls:
                                    if is_allowed_domain(sch_url, seed_domain, is_scheme_or_app=True):
                                        counter += 1
                                        heapq.heappush(queue, (
                                            1, next_depth, counter, sch_url, final_url,
                                            {"type": "scheme", "label": sch_link["text"]}
                                        ))

                            # 3. Priority: JavaScript & Meta Redirect URLs (Priority 0)
                            for red_url in parsed_data["redirect_links"]:
                                if red_url not in self.visited_urls:
                                    if is_allowed_domain(red_url, seed_domain, is_scheme_or_app=True):
                                        counter += 1
                                        heapq.heappush(queue, (
                                            0, next_depth, counter, red_url, final_url,
                                            {"type": "redirect", "label": "Portal Redirection"}
                                        ))

                            # 4. Standard internal links on same portal domain (Priority 3)
                            for gen_url in parsed_data["all_links"]:
                                if gen_url not in self.visited_urls:
                                    if is_allowed_domain(gen_url, seed_domain, is_scheme_or_app=False):
                                        counter += 1
                                        heapq.heappush(queue, (
                                            3, next_depth, counter, gen_url, final_url,
                                            {"type": "general", "label": "Internal Page"}
                                        ))

                    except Exception as e:
                        err_msg = f"Failed to scrape {current_url}: {str(e)}"
                        self.log(err_msg, level="ERROR")
                        save_scraped_page(
                            db_session=db,
                            url=current_url,
                            domain=urlparse(current_url).netloc,
                            title="Error Scraping Page",
                            content_text="",
                            raw_html="",
                            page_type=context.get("type", "GENERAL").upper(),
                            parent_url=parent_url,
                            http_status=500,
                            status="ERROR",
                            error_message=str(e)
                        )

            # Automatically run Scheme Cleaner Pipeline for newly scraped pages
            if total_pages > 0:
                try:
                    self.log("🧹 Running Scheme Cleaner Pipeline for newly scraped pages...")
                    if progress_callback:
                        progress_callback("Structuring and validating scraped schemes with AI pipeline...")
                    from scheme_cleaner.pipeline import SchemeDataPipeline
                    cleaner_pipe = SchemeDataPipeline()
                    clean_res = cleaner_pipe.process_scraped_data_db()
                    cleaned_num = clean_res.get('cleaned_records', 0)
                    new_db_num = clean_res.get('inserted_db_records', 0)
                    self.log(f"✨ Cleaning complete! {cleaned_num} schemes structured & saved to Database ({new_db_num} new)")
                    if progress_callback:
                        progress_callback(f"Cleaning complete: {cleaned_num} schemes ready in database and UI.")
                except Exception as auto_clean_err:
                    self.log(f"Auto-cleaning warning: {auto_clean_err}", level="ERROR")

            # Update Run Log
            run_log.ended_at = datetime.utcnow()
            run_log.pages_scraped = total_pages
            run_log.pdfs_downloaded = total_pdfs
            run_log.status = "COMPLETED"
            run_log.log_summary = "\n".join(self.log_messages[-30:])
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
        """Downloads a PDF / document and saves it to SCRAPED PDF folder and DB."""
        if pdf_url in self.downloaded_pdf_urls:
            return None

        self.downloaded_pdf_urls.add(pdf_url)
        self.log(f"📥 Downloading PDF/Document: {pdf_url}")

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

            # Record in Database
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
