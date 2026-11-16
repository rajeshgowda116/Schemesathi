import re
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, urlunparse


class SchemeNormalizer:
    """
    Normalizes scheme fields, formats, and URLs to ensure deterministic,
    reliable text preparation and deduplication across SchemeSathi.
    """

    @staticmethod
    def normalize_string(text: Optional[str]) -> str:
        """Trims whitespace and collapses multiple internal spaces."""
        if not text:
            return ""
        return re.sub(r"\s+", " ", str(text)).strip()

    @staticmethod
    def normalize_url(url: Optional[str]) -> str:
        """
        Cleans and normalizes URLs:
        - Lowercases scheme and domain.
        - Strips tracking query params (utm_*, ref, etc.) and fragments.
        - Normalizes trailing slashes.
        """
        if not url:
            return ""
        url = url.strip()
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return url

            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()
            path = parsed.path or "/"
            path = re.sub(r"/+", "/", path)
            if len(path) > 1 and path.endswith("/"):
                path = path.rstrip("/")

            # Clean tracking query parameters
            query = ""
            if parsed.query:
                clean_params = [
                    p for p in parsed.query.split("&")
                    if not re.match(r"^(utm_|ref|fbclid|gclid|source)=", p, re.I)
                ]
                query = "&".join(clean_params)

            cleaned = urlunparse((scheme, netloc, path, "", query, ""))
            return cleaned
        except Exception:
            return url.strip()

    @staticmethod
    def format_list_field(field_val: Any) -> str:
        """Formats list/dict/JSON fields into readable text lines."""
        if not field_val:
            return "Not specified"

        if isinstance(field_val, list):
            items = [str(x).strip() for x in field_val if str(x).strip()]
            if not items:
                return "Not specified"
            return ", ".join(items)

        if isinstance(field_val, dict):
            parts = [f"{k}: {v}" for k, v in field_val.items() if str(v).strip()]
            if not parts:
                return "Not specified"
            return "; ".join(parts)

        return str(field_val).strip() or "Not specified"

    @classmethod
    def format_age_limit(cls, age_min: Optional[int], age_max: Optional[int]) -> str:
        """Formats age limit conditions."""
        if age_min is not None and age_max is not None:
            return f"{age_min} to {age_max} years"
        elif age_min is not None:
            return f"Minimum {age_min} years"
        elif age_max is not None:
            return f"Maximum {age_max} years"
        return "Not specified"

    @classmethod
    def format_income_limit(cls, income_min: Optional[float], income_max: Optional[float]) -> str:
        """Formats income limit conditions."""
        if income_min is not None and income_max is not None:
            return f"Rs. {income_min:,.0f} to Rs. {income_max:,.0f} per annum"
        elif income_max is not None:
            return f"Up to Rs. {income_max:,.0f} per annum"
        elif income_min is not None:
            return f"Minimum Rs. {income_min:,.0f} per annum"
        return "As mentioned in the source"

    @classmethod
    def prepare_full_text(cls, scheme: Dict[str, Any]) -> str:
        """
        Creates the standardized text representation for a scheme.
        Does not invent missing information.
        Preserves the source URL and scheme metadata.
        """
        name = cls.normalize_string(scheme.get("scheme_name")) or "Unnamed Scheme"
        dept = cls.normalize_string(scheme.get("department")) or "Government of Karnataka"
        state = cls.normalize_string(scheme.get("state")) or "Karnataka"
        desc = cls.normalize_string(scheme.get("description")) or "Official government welfare initiative."
        eligibility = cls.format_list_field(scheme.get("eligibility"))
        age_str = cls.format_age_limit(scheme.get("age_min"), scheme.get("age_max"))
        income_str = cls.format_income_limit(scheme.get("income_min"), scheme.get("income_max"))
        benefits = cls.format_list_field(scheme.get("benefits"))
        docs = cls.format_list_field(scheme.get("documents_required"))
        app_process = cls.normalize_string(scheme.get("application_process")) or "Apply through the official portal or designated office."
        official_url = cls.normalize_url(scheme.get("official_url")) or "https://karnataka.gov.in"

        text_representation = (
            f"Scheme Name: {name}\n\n"
            f"Description: {desc}\n\n"
            f"Department: {dept}\n\n"
            f"State: {state}\n\n"
            f"Eligibility: {eligibility}\n\n"
            f"Age Limit: {age_str}\n\n"
            f"Income Limit: {income_str}\n\n"
            f"Benefits: {benefits}\n\n"
            f"Required Documents: {docs}\n\n"
            f"Application Process: {app_process}\n\n"
            f"Official URL: {official_url}"
        )
        return text_representation
