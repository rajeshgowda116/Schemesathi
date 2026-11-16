import re
from typing import Dict, Any, List, Set, Tuple, Optional
from backend.app.ingestion.scheme_normalizer import SchemeNormalizer


class SchemeDeduplicator:
    """
    Detects and eliminates duplicate scheme records using strict priority order:
    1. Existing stable scheme ID (e.g. scheme_id primary key).
    2. Official scheme identifier (if available in metadata).
    3. Normalized official URL combined with source portal information.
    4. Normalized scheme name + department + state as fallback.
    """

    @classmethod
    def generate_dedup_keys(cls, scheme: Dict[str, Any]) -> Tuple[str, str, str, str]:
        """
        Generates the 4 hierarchical deduplication keys for a scheme:
        1. Existing stable scheme ID
        2. Official scheme identifier
        3. Normalized specific official URL + scheme name
        4. Normalized scheme name + department + state as fallback
        """
        # 1. Scheme ID key
        scheme_id = scheme.get("scheme_id") or scheme.get("id")
        id_key = f"ID:{scheme_id}" if scheme_id else ""

        # 2. Official identifier key
        official_id = scheme.get("official_identifier") or scheme.get("scheme_code")
        official_id_key = f"OFFICIAL_ID:{SchemeNormalizer.normalize_string(official_id).lower()}" if official_id else ""

        # 3. Normalized official URL combined with scheme name
        norm_url = SchemeNormalizer.normalize_url(scheme.get("official_url"))
        name = SchemeNormalizer.normalize_string(scheme.get("scheme_name")).lower()
        dept = SchemeNormalizer.normalize_string(scheme.get("department") or "").lower()
        state = SchemeNormalizer.normalize_string(scheme.get("state") or "Karnataka").lower()

        url_key = f"URL:{norm_url}|NAME:{name}" if norm_url and name else ""

        # 4. Normalized name + department + state fallback key
        name_dept_key = f"NAME:{name}|DEPT:{dept}|STATE:{state}" if name else ""

        return id_key, official_id_key, url_key, name_dept_key

    @classmethod
    def deduplicate_batch(cls, schemes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filters out duplicate schemes within a batch based on priority order.
        Keeps the first occurrence (or more complete record).
        """
        seen_ids: Set[str] = set()
        seen_official_ids: Set[str] = set()
        seen_urls: Set[str] = set()
        seen_name_dept: Set[str] = set()

        unique_schemes: List[Dict[str, Any]] = []

        for s in schemes:
            id_key, off_id_key, url_key, name_key = cls.generate_dedup_keys(s)

            # Check Priority 1: ID
            if id_key and id_key in seen_ids:
                continue

            # Check Priority 2: Official Identifier
            if off_id_key and off_id_key in seen_official_ids:
                continue

            # Check Priority 3: URL
            if url_key and url_key in seen_urls:
                continue

            # Check Priority 4: Name + Dept + State
            if name_key and name_key in seen_name_dept:
                continue

            # Register keys
            if id_key:
                seen_ids.add(id_key)
            if off_id_key:
                seen_official_ids.add(off_id_key)
            if url_key:
                seen_urls.add(url_key)
            if name_key:
                seen_name_dept.add(name_key)

            unique_schemes.append(s)

        return unique_schemes
