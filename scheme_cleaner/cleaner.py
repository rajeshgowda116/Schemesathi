import re
from bs4 import BeautifulSoup, Comment
from typing import Union, List, Dict, Any


class DataCleaner:
    """
    Cleans raw web HTML/text for government schemes.
    Focuses on removing UI boilerplate (headers, footers, scripts, navs),
    normalizing whitespace, and preserving complete factual text for RAG.
    """

    @staticmethod
    def clean_html(raw_html: str) -> str:
        """Removes HTML tags and UI boilerplate elements, extracting clean plain text."""
        if not raw_html or not isinstance(raw_html, str):
            return ""

        # Parse with BeautifulSoup
        soup = BeautifulSoup(raw_html, "html.parser")

        # 1. Remove script, style, header, footer, nav, noscript, svg, button, form elements
        boilerplate_tags = [
            "script", "style", "header", "footer", "nav", "noscript",
            "svg", "button", "form", "iframe", "aside", "input", "meta"
        ]
        for tag in soup(boilerplate_tags):
            tag.decompose()

        # Remove HTML comments
        for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove element with common boilerplate classes or ids
        for elem in soup.find_all(class_=re.compile(r'(menu|nav|sidebar|footer|header|breadcrumb|social|cookie)', re.I)):
            elem.decompose()

        # Extract text separated by newlines
        text = soup.get_text(separator="\n")
        return DataCleaner.clean_text(text)

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Normalizes raw text:
        - Replaces non-breaking spaces
        - Cleans line breaks and excessive whitespace
        - Deduplicates repeated lines/blocks
        """
        if not text or not isinstance(text, str):
            return ""

        # Normalize non-breaking spaces and zero-width spaces
        text = text.replace("\xa0", " ").replace("\u200b", " ").replace("\t", " ")

        # Remove common web boilerplate patterns
        boilerplate_patterns = [
            r'Copyright\s*©\s*\d{4}.*$',
            r'All\s*Rights\s*Reserved.*$',
            r'Skip\s*to\s*main\s*content',
            r'Screen\s*Reader\s*Access',
            r'Font\s*Size\s*:\s*\+?\s*-?',
            r'Terms\s*&\s*Conditions',
            r'Privacy\s*Policy',
        ]
        for pattern in boilerplate_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)

        # Normalize whitespace line by line
        lines = [line.strip() for line in text.splitlines()]
        
        # Deduplicate consecutive identical lines while preserving meaningful structure
        cleaned_lines = []
        prev_line = None
        for line in lines:
            if not line:
                continue
            # Strip bullet icons or bullets if redundant
            clean_line = re.sub(r'^[•\-\*\>\–\—]\s*', '', line).strip()
            if clean_line and clean_line != prev_line:
                cleaned_lines.append(clean_line)
                prev_line = clean_line

        return "\n".join(cleaned_lines)

    @staticmethod
    def clean_list(items: Union[List[Any], str]) -> List[str]:
        """Cleans and deduplicates a list of text items."""
        if not items:
            return []
        if isinstance(items, str):
            items = [items]

        cleaned_items = []
        seen = set()

        for item in items:
            if not item:
                continue
            # If item is HTML, clean it
            if "<" in str(item) and ">" in str(item):
                cleaned = DataCleaner.clean_html(str(item))
            else:
                cleaned = DataCleaner.clean_text(str(item))

            # Split multiline items into individual bullet points if necessary
            sub_lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
            for line in sub_lines:
                norm_key = line.lower()
                if norm_key not in seen and len(line) > 1:
                    seen.add(norm_key)
                    cleaned_items.append(line)

        return cleaned_items
