from typing import Dict, Any, List, Tuple
from backend.app.config import CHUNK_SIZE, CHUNK_OVERLAP
from backend.app.ingestion.scheme_normalizer import SchemeNormalizer


class SchemeChunk:
    """Represents an individual chunk of a scheme for vector indexing."""
    def __init__(
        self,
        scheme_id: int,
        scheme_name: str,
        department: str,
        state_or_central: str,
        source_url: str,
        section_name: str,
        chunk_index: int,
        content_hash: str,
        chunk_text: str
    ):
        self.scheme_id = scheme_id
        self.scheme_name = scheme_name
        self.department = department
        self.state_or_central = state_or_central
        self.source_url = source_url
        self.section_name = section_name
        self.chunk_index = chunk_index
        self.content_hash = content_hash
        self.chunk_text = chunk_text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scheme_id": self.scheme_id,
            "scheme_name": self.scheme_name,
            "department": self.department,
            "state_or_central": self.state_or_central,
            "source_url": self.source_url,
            "section_name": self.section_name,
            "chunk_index": self.chunk_index,
            "content_hash": self.content_hash,
            "chunk_text": self.chunk_text
        }


class SchemeChunker:
    """
    Scheme-aware section chunker that splits schemes into logical semantic sections:
    - Overview
    - Eligibility
    - Benefits
    - Required Documents
    - Application Process
    """

    def __init__(self, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text_recursively(self, text: str) -> List[str]:
        """
        Recursively splits text on paragraphs, sentences, or word boundaries
        to stay within chunk_size while maintaining chunk_overlap.
        """
        text = text.strip()
        if len(text) <= self.chunk_size:
            return [text]

        splits: List[str] = []
        separators = ["\n\n", "\n", ". ", "; ", ", ", " "]

        def _split(s: str, sep_idx: int) -> List[str]:
            if len(s) <= self.chunk_size or sep_idx >= len(separators):
                # Hard chunk if no separator worked
                res = []
                start = 0
                while start < len(s):
                    end = min(start + self.chunk_size, len(s))
                    res.append(s[start:end].strip())
                    start += self.chunk_size - self.chunk_overlap
                return [r for r in res if r]

            sep = separators[sep_idx]
            parts = s.split(sep)
            chunks: List[str] = []
            curr_chunk: List[str] = []
            curr_len = 0

            for p in parts:
                p_len = len(p) + len(sep)
                if curr_len + p_len > self.chunk_size:
                    if curr_chunk:
                        joined = sep.join(curr_chunk).strip()
                        if joined:
                            chunks.append(joined)
                        # Keep overlap from end
                        curr_chunk = [curr_chunk[-1]] if self.chunk_overlap > 0 and len(curr_chunk) > 1 else []
                        curr_len = sum(len(x) + len(sep) for x in curr_chunk)
                    if len(p) > self.chunk_size:
                        sub = _split(p, sep_idx + 1)
                        chunks.extend(sub)
                        curr_chunk = []
                        curr_len = 0
                    else:
                        curr_chunk.append(p)
                        curr_len += p_len
                else:
                    curr_chunk.append(p)
                    curr_len += p_len

            if curr_chunk:
                joined = sep.join(curr_chunk).strip()
                if joined:
                    chunks.append(joined)
            return chunks

        return _split(text, 0)

    def chunk_scheme(self, scheme: Dict[str, Any], content_hash: str) -> List[SchemeChunk]:
        """
        Generates section-aware chunks for a single scheme record.
        """
        scheme_id = int(scheme.get("scheme_id") or scheme.get("id", 0))
        name = SchemeNormalizer.normalize_string(scheme.get("scheme_name")) or "Scheme"
        dept = SchemeNormalizer.normalize_string(scheme.get("department")) or "Government of Karnataka"
        state = SchemeNormalizer.normalize_string(scheme.get("state")) or "Karnataka"
        url = SchemeNormalizer.normalize_url(scheme.get("official_url")) or "https://karnataka.gov.in"
        desc = SchemeNormalizer.normalize_string(scheme.get("description"))

        # Build Logical Sections
        sections: List[Tuple[str, str]] = []

        # 1. Section: Overview
        overview_text = (
            f"Scheme: {name}\n"
            f"Department: {dept}\n"
            f"State: {state}\n"
            f"Official Portal: {url}\n"
            f"Overview: {desc}"
        )
        sections.append(("Overview", overview_text))

        # 2. Section: Eligibility
        elig_text = SchemeNormalizer.format_list_field(scheme.get("eligibility"))
        age_str = SchemeNormalizer.format_age_limit(scheme.get("age_min"), scheme.get("age_max"))
        income_str = SchemeNormalizer.format_income_limit(scheme.get("income_min"), scheme.get("income_max"))
        occ_str = SchemeNormalizer.format_list_field(scheme.get("occupation"))
        cat_str = SchemeNormalizer.format_list_field(scheme.get("category"))

        eligibility_section = (
            f"Scheme: {name} (Eligibility Criteria)\n"
            f"Department: {dept}\n"
            f"Eligibility Requirements: {elig_text}\n"
            f"Age Limit: {age_str}\n"
            f"Income Limit: {income_str}\n"
            f"Target Occupation: {occ_str}\n"
            f"Eligible Categories: {cat_str}"
        )
        sections.append(("Eligibility", eligibility_section))

        # 3. Section: Benefits
        benefits_text = SchemeNormalizer.format_list_field(scheme.get("benefits"))
        benefits_section = (
            f"Scheme: {name} (Benefits & Assistance)\n"
            f"Department: {dept}\n"
            f"Financial & Welfare Benefits: {benefits_text}"
        )
        sections.append(("Benefits", benefits_section))

        # 4. Section: Required Documents
        docs_text = SchemeNormalizer.format_list_field(scheme.get("documents_required"))
        docs_section = (
            f"Scheme: {name} (Required Documents for Application)\n"
            f"Department: {dept}\n"
            f"Documents & Certificates Needed: {docs_text}"
        )
        sections.append(("Required Documents", docs_section))

        # 5. Section: Application Process
        app_text = SchemeNormalizer.normalize_string(scheme.get("application_process")) or "Apply online on the official portal."
        app_section = (
            f"Scheme: {name} (How to Apply / Application Process)\n"
            f"Department: {dept}\n"
            f"Application Procedure: {app_text}\n"
            f"Official Link: {url}"
        )
        sections.append(("Application Process", app_section))

        # Split and package into SchemeChunk objects
        chunks: List[SchemeChunk] = []
        chunk_idx = 0

        for sec_name, sec_text in sections:
            split_texts = self.split_text_recursively(sec_text)
            for st in split_texts:
                if not st.strip():
                    continue
                chunk = SchemeChunk(
                    scheme_id=scheme_id,
                    scheme_name=name,
                    department=dept,
                    state_or_central=state,
                    source_url=url,
                    section_name=sec_name,
                    chunk_index=chunk_idx,
                    content_hash=content_hash,
                    chunk_text=st
                )
                chunks.append(chunk)
                chunk_idx += 1

        return chunks
