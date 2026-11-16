import json
import hashlib
from typing import Dict, Any
from backend.app.ingestion.scheme_normalizer import SchemeNormalizer


class SchemeHasher:
    """
    Computes deterministic SHA-256 content hashes for scheme records
    across all RAG-relevant fields.
    """

    RAG_RELEVANT_KEYS = [
        "scheme_name",
        "department",
        "state",
        "description",
        "benefits",
        "eligibility",
        "age_min",
        "age_max",
        "income_min",
        "income_max",
        "occupation",
        "category",
        "documents_required",
        "application_process",
        "official_url"
    ]

    @classmethod
    def compute_hash(cls, scheme_dict: Dict[str, Any]) -> str:
        """
        Generates a deterministic SHA-256 hash using normalized fields.
        Ensures consistent hashing across different Python versions or dict key orders.
        """
        normalized_payload: Dict[str, Any] = {}

        for k in cls.RAG_RELEVANT_KEYS:
            val = scheme_dict.get(k)
            if isinstance(val, str):
                normalized_payload[k] = SchemeNormalizer.normalize_string(val).lower()
            elif isinstance(val, (int, float)):
                normalized_payload[k] = val
            elif isinstance(val, list):
                # Sort items if string list for stability
                items = [str(x).strip().lower() for x in val if str(x).strip()]
                normalized_payload[k] = sorted(items)
            elif isinstance(val, dict):
                normalized_payload[k] = {str(dk).lower(): str(dv).strip().lower() for dk, dv in sorted(val.items())}
            elif val is None:
                normalized_payload[k] = None
            else:
                normalized_payload[k] = str(val).strip().lower()

        # Serialize to sorted JSON string
        serialized = json.dumps(normalized_payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
