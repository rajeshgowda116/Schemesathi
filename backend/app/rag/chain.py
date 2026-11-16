import logging
import requests
from typing import Dict, Any, List, Optional

from backend.app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT
from backend.app.rag.retriever import SchemeRetriever
from backend.app.rag.prompt import SYSTEM_PROMPT, build_context_string, build_user_prompt

logger = logging.getLogger("RAGChain")


class RAGChain:
    """
    End-to-End Grounded Question Answering Chain for SchemeSathi.
    Coordinates query retrieval, prompt construction, Ollama LLM inference,
    and structured source citation.
    """

    def __init__(
        self,
        retriever: Optional[SchemeRetriever] = None,
        ollama_url: str = OLLAMA_BASE_URL,
        model_name: str = OLLAMA_MODEL,
        timeout: int = OLLAMA_TIMEOUT
    ):
        self.retriever = retriever or SchemeRetriever()
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.timeout = timeout

    def answer_question(
        self,
        query: str,
        user_profile: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes grounded RAG workflow for citizen query.
        Returns:
        {
            "answer": str,
            "sources": List[dict],
            "retrieved_chunks": int,
            "llm_engine": str
        }
        """
        # 1. Retrieve relevant scheme chunks from Qdrant
        retrieved_hits = self.retriever.retrieve(query=query, filters=filters)

        # 2. Handle Empty Retrieval
        if not retrieved_hits:
            return {
                "answer": (
                    "No matching government scheme records could be found in the official SchemeSathi database "
                    "for your query. Please verify the scheme name or try broader terms. "
                    "\n\n*Note: Final eligibility criteria must always be confirmed through official government departments.*"
                ),
                "sources": [],
                "retrieved_chunks": 0,
                "llm_engine": "none"
            }

        # 3. Extract unique sources for citations
        sources: List[Dict[str, Any]] = []
        seen_schemes = set()

        for hit in retrieved_hits:
            payload = hit.get("payload", {})
            s_name = payload.get("scheme_name", "Scheme")
            if s_name not in seen_schemes:
                seen_schemes.add(s_name)
                sources.append({
                    "scheme_id": payload.get("scheme_id"),
                    "scheme_name": s_name,
                    "department": payload.get("department", "Government of Karnataka"),
                    "state": payload.get("state_or_central", "Karnataka"),
                    "official_url": payload.get("source_url", "https://karnataka.gov.in"),
                    "relevance_score": round(hit.get("score", 0.0), 3)
                })

        # 4. Construct Grounded Prompt & Context
        context_str = build_context_string(retrieved_hits)
        user_prompt_str = build_user_prompt(query, user_profile)

        # 5. Call Ollama API
        answer = self._call_ollama(context_str, user_prompt_str)

        # If Ollama is unavailable, fallback to structured grounded synthesis
        if not answer:
            answer = self._synthesize_fallback_answer(retrieved_hits, query)
            engine_used = "offline_grounded_fallback"
        else:
            engine_used = f"ollama:{self.model_name}"

        return {
            "answer": answer,
            "sources": sources,
            "retrieved_chunks": len(retrieved_hits),
            "llm_engine": engine_used
        }

    def _call_ollama(self, context: str, user_prompt: str) -> Optional[str]:
        """Attempts generation using Ollama."""
        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"=== OFFICIAL SCHEME CONTEXT ===\n"
            f"{context}\n\n"
            f"=== USER QUERY ===\n"
            f"{user_prompt}\n\n"
            f"Answer:"
        )

        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # Low temperature for strict factual grounding
                        "top_p": 0.9
                    }
                },
                timeout=3.0  # Fast timeout: if Ollama is unreachable, failover immediately
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response", "").strip()
        except Exception as e:
            logger.warning(f"Ollama generation unavailable ({e}). Falling back to structured synthesis.")
        return None

    def _synthesize_fallback_answer(self, hits: List[Dict[str, Any]], query: str) -> str:
        """
        Synthesizes a 100% grounded answer directly from retrieved chunks
        when the external Ollama engine is unreachable.
        """
        schemes_grouped: Dict[str, Dict[str, Any]] = {}

        for hit in hits:
            p = hit.get("payload", {})
            name = p.get("scheme_name", "Scheme")
            if name not in schemes_grouped:
                schemes_grouped[name] = {
                    "department": p.get("department", "Government of Karnataka"),
                    "url": p.get("source_url", "https://karnataka.gov.in"),
                    "sections": []
                }
            schemes_grouped[name]["sections"].append({
                "section": p.get("section_name", "Overview"),
                "text": p.get("chunk_text", "")
            })

        lines = [
            f"Based on official government scheme records retrieved for '**{query}**':\n"
        ]

        for s_name, data in schemes_grouped.items():
            lines.append(f"### 🏛️ {s_name}")
            lines.append(f"- **Department:** {data['department']}")
            lines.append(f"- **Official Portal:** {data['url']}")
            for sec in data["sections"]:
                lines.append(f"\n**{sec['section']}:**\n{sec['text']}")
            lines.append("\n" + "-" * 40 + "\n")

        lines.append(
            "\n*⚖️ Disclaimer: This information is derived directly from official portal records. "
            "Final eligibility and sanction must be confirmed by the respective government department or issuing authority.*"
        )
        return "\n".join(lines)
