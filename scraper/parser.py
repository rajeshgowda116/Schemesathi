import re
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
from typing import Dict, List, Any, Set, Tuple, Optional

from scraper.config import SCHEME_KEYWORDS, APPLICATION_KEYWORDS, DOCUMENT_KEYWORDS


def parse_html_page(base_url: str, html_content: str) -> Dict[str, Any]:
    """
    Parses HTML content, extracting title, text content, meta description,
    categorized internal/external links (schemes, application forms, redirects),
    forms, and PDF links.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. Extract Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.h1:
        title = soup.h1.get_text().strip()
    if not title:
        title = urlparse(base_url).path.strip('/') or base_url

    # 2. Extract Meta Description
    meta_desc = ""
    meta_tag = soup.find('meta', attrs={'name': re.compile(r'description', re.I)})
    if meta_tag and meta_tag.get('content'):
        meta_desc = meta_tag['content'].strip()

    # 3. Detect Meta Refresh Redirects
    redirect_links: Set[str] = set()
    for meta in soup.find_all('meta', attrs={'http-equiv': re.compile(r'^refresh$', re.I)}):
        content = meta.get('content', '')
        m = re.search(r'url\s*=\s*([^;]+)', content, re.I)
        if m:
            t_url = clean_url(urljoin(base_url, m.group(1).strip()))
            if is_crawlable_url(t_url):
                redirect_links.add(t_url)

    # 4. Detect Interactive Elements & Links
    all_links: Set[str] = set()
    pdf_links: Set[str] = set()
    application_links: List[Dict[str, str]] = []
    scheme_links: List[Dict[str, str]] = []
    form_actions: List[Dict[str, str]] = []

    # 4a. Standard <a> tags
    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '').strip()
        if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#', 'data:')):
            continue

        link_text = a_tag.get_text(separator=' ', strip=True)
        title_attr = a_tag.get('title', '')
        aria_label = a_tag.get('aria-label', '')
        combined_meta = f"{link_text} {title_attr} {aria_label} {href}".strip()

        abs_url = urljoin(base_url, href)
        cleaned_url = clean_url(abs_url)

        if is_pdf_url(cleaned_url):
            pdf_links.add(cleaned_url)
        elif is_crawlable_url(cleaned_url):
            all_links.add(cleaned_url)
            # Check for application form links
            if is_application_form_link(combined_meta, cleaned_url):
                application_links.append({"url": cleaned_url, "text": link_text or "Apply / Form Link", "type": "link"})
            elif is_scheme_link(combined_meta, cleaned_url):
                scheme_links.append({"url": cleaned_url, "text": link_text or "Scheme Link", "type": "link"})

    # 4b. Form action endpoints (often the direct application submission or form page)
    for form in soup.find_all('form', action=True):
        action = form.get('action', '').strip()
        method = form.get('method', 'GET').upper()
        if action and not action.startswith(('javascript:', '#', 'mailto:')):
            abs_action = clean_url(urljoin(base_url, action))
            if is_crawlable_url(abs_action):
                all_links.add(abs_action)
                form_actions.append({"url": abs_action, "method": method})
                application_links.append({"url": abs_action, "text": f"Form Endpoint ({method})", "type": "form_action"})

    # 4c. Onclick JavaScript buttons/redirects (common on government portal "Apply Now" buttons)
    for elem in soup.find_all(attrs={"onclick": True}):
        onclick_code = elem.get('onclick', '')
        extracted_url = extract_url_from_onclick(onclick_code)
        if extracted_url:
            abs_url = clean_url(urljoin(base_url, extracted_url))
            btn_text = elem.get_text(separator=' ', strip=True)
            if is_pdf_url(abs_url):
                pdf_links.add(abs_url)
            elif is_crawlable_url(abs_url):
                all_links.add(abs_url)
                redirect_links.add(abs_url)
                combined = f"{btn_text} {abs_url}"
                if is_application_form_link(combined, abs_url):
                    application_links.append({"url": abs_url, "text": btn_text or "Apply Button", "type": "onclick"})
                elif is_scheme_link(combined, abs_url):
                    scheme_links.append({"url": abs_url, "text": btn_text or "Scheme Action", "type": "onclick"})

    # 4d. Check embed, object, iframe for embedded PDFs
    for tag in soup.find_all(['embed', 'object', 'iframe'], src=True):
        src = tag.get('src', '').strip()
        if src:
            abs_url = clean_url(urljoin(base_url, src))
            if is_pdf_url(abs_url):
                pdf_links.add(abs_url)

    # 5. Extract Clean Plain Text Content
    for elem in soup(['script', 'style', 'noscript', 'header', 'footer', 'nav', 'svg']):
        elem.decompose()

    text_lines = [line.strip() for line in soup.get_text(separator='\n').splitlines() if line.strip()]
    content_text = '\n'.join(text_lines)

    # 6. Determine Page Classification (HOME, SCHEME, APPLICATION_FORM, GENERAL)
    page_type = classify_page(base_url, title, content_text, len(form_actions) > 0)

    return {
        "title": title,
        "meta_description": meta_desc,
        "content_text": content_text,
        "page_type": page_type,
        "all_links": list(all_links),
        "pdf_links": list(pdf_links),
        "application_links": application_links,
        "scheme_links": scheme_links,
        "redirect_links": list(redirect_links),
        "form_actions": form_actions
    }


def classify_page(url: str, title: str, content: str, has_form: bool = False) -> str:
    """Classifies a page into HOME, APPLICATION_FORM, SCHEME, or GENERAL."""
    parsed = urlparse(url)
    path = parsed.path.lower().strip('/')
    query = parsed.query.lower()
    combined = f"{path} {query} {title} {content[:1500]}".lower()

    # Check for Home Page
    if path in ('', 'index.html', 'home', 'homepage', 'gl-sp', 'default', 'default.aspx'):
        if not any(k in query for k in ('scheme', 'service', 'apply', 'form', 'login')):
            return "HOME"

    # Check for Application Form / Apply Page
    app_indicators = [
        'application form', 'apply online', 'online application', 'student login',
        'create new account', 'citizen registration', 'registration form',
        'apply now', 'application status', 'serviceplus', 'post_sa', 'ssppre',
        'fill application', 'enter applicant details', 'upload documents'
    ]
    if any(ind in combined for ind in app_indicators) or (has_form and any(k in combined for k in APPLICATION_KEYWORDS)):
        return "APPLICATION_FORM"

    # Check for Scheme Page
    scheme_indicators = [
        'scheme', 'yojana', 'scholarship', 'welfare', 'eligibility criteria',
        'benefits of scheme', 'objective of scheme', 'departmentservices',
        'knowyoureligibility', 'schemes.aspx', 'yojane'
    ]
    if any(ind in combined for ind in scheme_indicators):
        return "SCHEME"

    return "GENERAL"


def is_application_form_link(text_context: str, url: str) -> bool:
    """Detects if a link points to an application form, apply button, or login-to-apply portal."""
    combined = f"{text_context} {url}".lower()
    return any(keyword in combined for keyword in APPLICATION_KEYWORDS)


def is_scheme_link(text_context: str, url: str) -> bool:
    """Detects if a link points to a scheme details or scheme listing page."""
    combined = f"{text_context} {url}".lower()
    return any(keyword in combined for keyword in SCHEME_KEYWORDS)


def extract_url_from_onclick(onclick_str: str) -> Optional[str]:
    """Extracts redirect URLs from JavaScript onclick handlers."""
    if not onclick_str:
        return None
    # Matches window.location.href = '...', location.href = '...', window.open('...')
    m = re.search(r"(?:window\.)?location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]", onclick_str)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"window\.open\s*\(\s*['\"]([^'\"]+)['\"]", onclick_str)
    if m2:
        return m2.group(1).strip()
    return None


def is_pdf_url(url: str) -> bool:
    """Checks if a URL points to a PDF or document file."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()

    if path.endswith(('.pdf', '.doc', '.docx', '.odt', '.rtf')):
        return True
    if '.pdf' in path or 'format=pdf' in query or 'type=pdf' in query:
        return True
    if 'downloadpdf' in path or 'viewpdf' in path or 'getpdf' in path or 'downloadfile' in path:
        return True
    return False


def is_crawlable_url(url: str) -> bool:
    """
    Checks if a URL is an HTML/Web page worth crawling.
    Strictly filters out static assets (css, js, images, fonts, media, archives).
    """
    if not url or not url.startswith(('http://', 'https://')):
        return False

    parsed = urlparse(url)
    path = parsed.path.lower()
    url_lower = url.lower()

    # Reject non-web assets
    ignored_exts = (
        '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico',
        '.svg', '.webp', '.bmp', '.woff', '.woff2', '.ttf', '.eot',
        '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.mkv',
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
        '.xml', '.json', '.map', '.wasm'
    )
    if any(path.endswith(ext) or f"{ext}?" in url_lower or f"{ext}&" in url_lower for ext in ignored_exts):
        return False

    return True


def clean_url(url: str) -> str:
    """Removes trailing anchors (#), normalizes slashes, and strips tracking/session query params."""
    parsed = urlparse(url)
    path = parsed.path or '/'
    
    # Strip common session IDs from query
    cleaned_query = ""
    if parsed.query:
        params = parsed.query.split('&')
        filtered_params = [
            p for p in params 
            if not re.match(r'^(jsessionid|phpsessid|aspsessionid|sid)=', p, re.I)
        ]
        cleaned_query = "&".join(filtered_params)

    cleaned = f"{parsed.scheme}://{parsed.netloc}{path}"
    if cleaned_query:
        cleaned += f"?{cleaned_query}"
    return cleaned


def sanitize_filename(name: str) -> str:
    """Sanitizes a string to be a valid Windows file name."""
    name = unquote(name)
    name = re.sub(r'[\\/*?:"<>|]', '_', name)
    name = re.sub(r'\s+', '_', name).strip('_')
    if not name:
        name = "scraped_document"
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    return name[:150]
