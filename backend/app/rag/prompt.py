from typing import List, Dict, Any, Optional

SYSTEM_PROMPT = """You are SchemeSathi — an AI-powered Assistant for Government Schemes in Karnataka, India.
Your mission is to provide accurate, reliable, citizen-friendly information regarding government welfare schemes, scholarships, and citizen services based SOLELY on retrieved official government sources.

STRICT OPERATIONAL RULES:
1. Grounding: Answer using ONLY the provided Scheme Context below. Do NOT use outside knowledge or assumptions.
2. No Invention: NEVER invent or hallucinate scheme eligibility criteria, benefits, income thresholds, age limits, or required documents.
3. No Fabricated URLs: NEVER fabricate or alter government URLs. Only cite the official URLs provided in the context.
4. Missing Information: Clearly distinguish between confirmed facts and missing/unspecified information. If specific details (e.g. deadline, income cap) are not in the context, explicitly state: "This information could not be found in the available official sources."
5. Legal Disclaimer: Do NOT make final legal or administrative eligibility decisions. Always remind the citizen that final eligibility must be confirmed by the relevant government authority or department.
6. Transparency: Always reference the official Scheme Name, Department, and Source URL for every cited scheme.
"""


def build_context_string(retrieved_chunks: List[Dict[str, Any]]) -> str:
    """
    Constructs a formatted, structured context string from retrieved Qdrant chunks.
    """
    if not retrieved_chunks:
        return "No relevant government scheme records were found for this query."

    context_blocks = []
    seen_schemes = set()

    for idx, hit in enumerate(retrieved_chunks, 1):
        payload = hit.get("payload", {})
        score = hit.get("score", 0.0)

        s_id = payload.get("scheme_id", "N/A")
        s_name = payload.get("scheme_name", "Official Scheme")
        dept = payload.get("department", "Government of Karnataka")
        state = payload.get("state_or_central", "Karnataka")
        section = payload.get("section_name", "General")
        url = payload.get("source_url", "https://karnataka.gov.in")
        chunk_text = payload.get("chunk_text", "").strip()

        block = (
            f"--- [SOURCE {idx}] ---\n"
            f"Scheme Name: {s_name} (ID: {s_id})\n"
            f"Department: {dept} ({state})\n"
            f"Section: {section}\n"
            f"Official URL: {url}\n"
            f"Relevance Score: {score:.3f}\n"
            f"Content:\n{chunk_text}\n"
        )
        context_blocks.append(block)
        seen_schemes.add(s_name)

    return "\n".join(context_blocks)


def build_user_prompt(query: str, user_profile: Optional[Dict[str, Any]] = None) -> str:
    """
    Builds the user prompt incorporating optional citizen profile criteria
    (age, income, category, occupation).
    """
    profile_info = ""
    if user_profile and any(user_profile.values()):
        parts = []
        if user_profile.get("age") is not None:
            parts.append(f"Age: {user_profile['age']}")
        if user_profile.get("income") is not None:
            parts.append(f"Annual Income: Rs. {user_profile['income']}")
        if user_profile.get("category"):
            parts.append(f"Social Category: {user_profile['category']}")
        if user_profile.get("occupation"):
            parts.append(f"Occupation: {user_profile['occupation']}")
        if user_profile.get("state"):
            parts.append(f"State: {user_profile['state']}")
        if parts:
            profile_info = f"\nCitizen Profile Context:\n" + "\n".join(f"- {p}" for p in parts) + "\n"

    return f"{profile_info}\nCitizen Question:\n{query.strip()}"
