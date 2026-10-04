import re
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
from typing import Dict, List, Any, Set, Tuple


def parse_html_page(base_url: str, html_content: str) -> Dict[str, Any]:
    """
    Parses HTML content, extracting title, text content, meta description,
    internal/external links, and PDF links.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extract Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.h1:
        title = soup.h1.get_text().strip()
    if not title:
        title = urlparse(base_url).path.strip('/') or base_url

    # Extract Meta Description
    meta_desc = ""
    meta_tag = soup.find('meta', attrs={'name': re.compile(r'description', re.I)})
    if meta_tag and meta_tag.get('content'):
        meta_desc = meta_tag['content'].strip()

    # Extract Clean Plain Text Content
    # Remove script, style, header, footer elements for cleaner text extraction
    for elem in soup(['script', 'style', 'noscript', 'header', 'footer', 'nav', 'svg']):
        elem.decompose()

    text_lines = [line.strip() for line in soup.get_text(separator='\n').splitlines() if line.strip()]
    content_text = '\n'.join(text_lines)

    # Extract all <a> links
    all_links: Set[str] = set()
    pdf_links: Set[str] = set()

    for a_tag in soup.find_all(['a', 'link', 'iframe', 'embed'], href=True):
        href = a_tag.get('href') or a_tag.get('src')
        if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
            continue

        abs_url = urljoin(base_url, href)
        cleaned_url = clean_url(abs_url)

        if is_pdf_url(cleaned_url):
            pdf_links.add(cleaned_url)
        elif is_crawlable_url(cleaned_url):
            all_links.add(cleaned_url)

    # Also check tags with src (like pdf embeds)
    for tag in soup.find_all(['embed', 'object', 'iframe'], src=True):
        src = tag.get('src')
        if src:
            abs_url = urljoin(base_url, src)
            cleaned_url = clean_url(abs_url)
            if is_pdf_url(cleaned_url):
                pdf_links.add(cleaned_url)

    return {
        "title": title,
        "meta_description": meta_desc,
        "content_text": content_text,
        "all_links": list(all_links),
        "pdf_links": list(pdf_links)
    }


def is_pdf_url(url: str) -> bool:
    """Checks if a URL points to a PDF file."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()

    if path.endswith('.pdf'):
        return True
    if '.pdf' in path or 'format=pdf' in query or 'type=pdf' in query:
        return True
    if 'downloadpdf' in path or 'viewpdf' in path or 'getpdf' in path:
        return True
    return False


def is_crawlable_url(url: str) -> bool:
    """Checks if a URL is an HTML/Web page worth crawling (ignoring static images/styles)."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    ignored_exts = (
        '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico',
        '.svg', '.woff', '.woff2', '.ttf', '.eot', '.mp3', '.mp4',
        '.zip', '.rar', '.7z', '.tar', '.gz', '.xml', '.json'
    )
    if any(path.endswith(ext) for ext in ignored_exts):
        return False
    return True


def clean_url(url: str) -> str:
    """Removes trailing anchors and normalizes URL."""
    parsed = urlparse(url)
    # Reconstruct without fragment (#)
    cleaned = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if parsed.query:
        cleaned += f"?{parsed.query}"
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
    return name[:150]  # Limit length
