import re
from typing import Dict, Any, List, Optional, Tuple
from scheme_cleaner.cleaner import DataCleaner


class SchemeExtractor:
    """
    Extracts structured fields from cleaned raw scheme data.
    Implements rule-based extraction for age limits, income limits,
    Indian currency normalization, occupations, categories, and documents.
    """

    @staticmethod
    def parse_indian_currency(val_str: str) -> Optional[float]:
        """
        Normalizes Indian currency text strings to numerical numbers:
        - ₹2 lakh / 2 lakh -> 200000.0
        - ₹2.5 lakh -> 250000.0
        - ₹1 crore -> 10000000.0
        - Rs. 50,000 -> 50000.0
        """
        if not val_str:
            return None

        clean_str = re.sub(r'[₹\$\,\s]', '', str(val_str)).lower()
        clean_str = re.sub(r'^(rs\.?|inr)\s*', '', clean_str, flags=re.I)

        m = re.search(r'([\d\.]+)\s*(lakh|lakhs|lac|lacs|crore|cr)?', clean_str)
        if not m:
            return None

        try:
            val = float(m.group(1))
            unit = m.group(2)
            if unit in ['lakh', 'lakhs', 'lac', 'lacs']:
                val *= 100000.0
            elif unit in ['crore', 'crores', 'cr']:
                val *= 10000000.0

            # Ignore years e.g. 2024, 2025, 2026 if unit was not specified
            if not unit and 1900 <= val <= 2099:
                return None
            return val
        except ValueError:
            return None

    @staticmethod
    def extract_age_limits(text: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Extracts age_min and age_max from text blobs.
        Examples:
        - "between 18 and 30 years of age" -> (18, 30)
        - "minimum 18 years" / "at least 18 years" -> (18, None)
        - "below 60 years" / "up to 60 years" -> (None, 60)
        - "age 21 to 45" -> (21, 45)
        """
        if not text:
            return None, None

        text_lower = text.lower()
        age_min, age_max = None, None

        # Pattern 1: between X and Y years / age X to Y
        range_match = re.search(
            r'(?:between|age|aged)\s*(\d{1,2})\s*(?:and|to|-)\s*(\d{1,2})\s*(?:years|yrs)?',
            text_lower
        )
        if range_match:
            min_v, max_v = int(range_match.group(1)), int(range_match.group(2))
            if 0 <= min_v <= 120 and 0 <= max_v <= 120 and min_v <= max_v:
                return min_v, max_v

        # Pattern 2: Minimum age X / at least X years / X years and above
        min_match = re.search(
            r'(?:minimum|min|at least|above|attained)\s*(\d{1,2})\s*(?:years|yrs)?',
            text_lower
        )
        if min_match:
            val = int(min_match.group(1))
            if 0 <= val <= 100:
                age_min = val

        # Pattern 3: Maximum age Y / below Y years / up to Y years / not more than Y years
        max_match = re.search(
            r'(?:maximum|max|below|under|up to|not exceed|not more than)\s*(\d{1,2})\s*(?:years|yrs)?',
            text_lower
        )
        if max_match:
            val = int(max_match.group(1))
            if 0 <= val <= 100:
                age_max = val

        return age_min, age_max

    @staticmethod
    def extract_income_limits(text: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Extracts income_min and income_max from text blobs.
        Examples:
        - "Annual family income should not exceed Rs. 2.5 lakh" -> (None, 250000.0)
        - "Family income below Rs 1.5 lakh" -> (None, 150000.0)
        - "Income between Rs 1 lakh and Rs 3 lakh" -> (100000.0, 300000.0)
        """
        if not text:
            return None, None

        text_lower = text.lower()

        # Range: between X and Y
        between_match = re.search(
            r'income\s*between\s*(?:rs\.?|inr|₹)?\s*([\d\.]+\s*(?:lakh|lakhs|lac|lacs|crore)?)\s*and\s*(?:rs\.?|inr|₹)?\s*([\d\.]+\s*(?:lakh|lakhs|lac|lacs|crore)?)',
            text_lower
        )
        if between_match:
            min_v = SchemeExtractor.parse_indian_currency(between_match.group(1))
            max_v = SchemeExtractor.parse_indian_currency(between_match.group(2))
            if min_v and max_v:
                return min_v, max_v

        # Upper bound: income not exceed / below / less than / up to X
        max_match = re.search(
            r'(?:income|family income|annual income)[^,\.\n]*?(?:not exceed|less than|below|up to|under|maximum of|within)\s*(?:rs\.?|inr|₹)?\s*([\d\.]+\s*(?:lakh|lakhs|lac|lacs|crore|\d+))',
            text_lower
        )
        if max_match:
            val = SchemeExtractor.parse_indian_currency(max_match.group(1))
            if val and val > 1000:  # Ignore trivial numbers
                return None, val

        return None, None

    @staticmethod
    def extract_occupations(text: str) -> List[str]:
        """Extracts target occupation categories from scheme text."""
        if not text:
            return []

        text_lower = text.lower()
        occupations = set()

        keywords_map = {
            "Student": ["student", "scholar", "school", "college", "university"],
            "Farmer / Agriculture": ["farmer", "agriculturist", "cultivator", "ryot", "krishi"],
            "Artisan / Weaver": ["artisan", "weaver", "craftsman", "handloom", "khadi"],
            "Unemployed Youth": ["unemployed", "job seeker", "youth"],
            "Worker / Labourer": ["labour", "labor", "worker", "construction worker", "artisan"],
            "Entrepreneur / MSME": ["entrepreneur", "business", "start-up", "startup", "vendor", "street vendor"],
            "Woman / Widow": ["women", "woman", "female", "widow", "girl child"],
            "Senior Citizen": ["senior citizen", "elderly", "pensioner"],
        }

        for category_name, patterns in keywords_map.items():
            if any(p in text_lower for p in patterns):
                occupations.add(category_name)

        return sorted(list(occupations))

    @staticmethod
    def extract_categories(text: str) -> List[str]:
        """Extracts social/economic categories from scheme text."""
        if not text:
            return []

        text_lower = text.lower()
        categories = set()

        category_keywords = {
            "SC": ["sc ", "scheduled caste"],
            "ST": ["st ", "scheduled tribe"],
            "OBC": ["obc", "other backward"],
            "Minority": ["minority", "muslim", "christian", "jain", "sikh", "buddhist"],
            "BPL": ["bpl", "below poverty line", "ration card holder"],
            "General": ["general category", "all categories"],
            "PwD / Disabled": ["pwd", "disabled", "handicapped", "differently abled"],
        }

        for cat_name, patterns in category_keywords.items():
            if any(p in text_lower for p in patterns):
                categories.add(cat_name)

        return sorted(list(categories))

    @staticmethod
    def extract_scheme(raw_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes a raw scraped item dictionary and maps it into the standard target structure.
        """
        # Extract or clean raw HTML content if present
        raw_content = raw_item.get("raw_html") or raw_item.get("content_text") or raw_item.get("description") or ""
        cleaned_main_text = DataCleaner.clean_html(raw_content) if "<" in raw_content else DataCleaner.clean_text(raw_content)

        # 1. Scheme Name
        scheme_name = raw_item.get("scheme_name") or raw_item.get("title") or ""
        scheme_name = DataCleaner.clean_text(scheme_name).replace("\n", " ").strip()

        # 2. State
        state = raw_item.get("state") or "Karnataka"
        state = DataCleaner.clean_text(state)

        # 3. Department
        department = raw_item.get("department") or raw_item.get("dept") or "Government of Karnataka"
        department = DataCleaner.clean_text(department)

        # 4. Description
        description = raw_item.get("description") or cleaned_main_text
        description = DataCleaner.clean_text(description)

        # 5. Benefits
        raw_benefits = raw_item.get("benefits") or []
        benefits = DataCleaner.clean_list(raw_benefits)

        # 6. Eligibility
        raw_eligibility = raw_item.get("eligibility") or []
        eligibility = DataCleaner.clean_list(raw_eligibility)

        # Combine text for range extraction
        combined_text = f"{description}\n" + "\n".join(eligibility) + "\n".join(benefits)

        # 7. Age Min & Max
        age_min = raw_item.get("age_min")
        age_max = raw_item.get("age_max")
        if age_min is None or age_max is None:
            extracted_min_age, extracted_max_age = SchemeExtractor.extract_age_limits(combined_text)
            if age_min is None:
                age_min = extracted_min_age
            if age_max is None:
                age_max = extracted_max_age

        # 8. Income Min & Max
        income_min = raw_item.get("income_min")
        income_max = raw_item.get("income_max")
        if income_min is None or income_max is None:
            extracted_min_inc, extracted_max_inc = SchemeExtractor.extract_income_limits(combined_text)
            if income_min is None:
                income_min = extracted_min_inc
            if income_max is None:
                income_max = extracted_max_inc

        # 9. Occupation
        occupation = DataCleaner.clean_list(raw_item.get("occupation") or [])
        if not occupation:
            occupation = SchemeExtractor.extract_occupations(combined_text)

        # 10. Category
        category = DataCleaner.clean_list(raw_item.get("category") or [])
        if not category:
            category = SchemeExtractor.extract_categories(combined_text)

        # 11. Documents Required
        raw_docs = raw_item.get("documents_required") or raw_item.get("documents") or []
        documents_required = DataCleaner.clean_list(raw_docs)

        # 12. Application Process
        app_proc = raw_item.get("application_process") or raw_item.get("how_to_apply") or ""
        application_process = DataCleaner.clean_text(app_proc)

        # 13. Official URL
        official_url = raw_item.get("official_url") or raw_item.get("url") or ""

        # 14. Dates
        source_date = raw_item.get("source_date") or raw_item.get("scraped_at") or None
        last_updated = raw_item.get("last_updated") or None

        return {
            "scheme_name": scheme_name,
            "state": state,
            "department": department,
            "description": description,
            "benefits": benefits,
            "eligibility": eligibility,
            "age_min": age_min,
            "age_max": age_max,
            "income_min": income_min,
            "income_max": income_max,
            "occupation": occupation,
            "category": category,
            "documents_required": documents_required,
            "application_process": application_process,
            "official_url": official_url,
            "source_date": source_date,
            "last_updated": last_updated
        }
