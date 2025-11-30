"""
Dynamic trust scoring utilities for document ingestion.

Trust is computed from:
- External validation (Semantic Scholar DOI lookup, citation counts)
- Structural analysis (LLM classification of the document type)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import requests  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    requests = None  # type: ignore[assignment]


DOC_TYPE_PROMPT = """Analizza il seguente testo (prime pagine del documento) e rispondi in JSON.
Classifica il documento in una delle categorie: LAB_NOTE, TEXTBOOK, LECTURE_SLIDES, IMAGE_CAPTION, EXPERIMENTAL_STUDY, REVIEW_ARTICLE, POPULAR_SCIENCE, OTHER.
Restituisci solo JSON: {{"doc_type": "...", "confidence": 0.0-1.0, "rationale": "breve motivo"}}.
Testo:
{sample}
"""

DOC_TYPE_TRUST = {
    "LAB_NOTE": 1.0,
    "TEXTBOOK": 0.90,
    "LECTURE_SLIDES": 0.70,
    "IMAGE_CAPTION": 0.60,
    "EXPERIMENTAL_STUDY": 0.90,
    "REVIEW_ARTICLE": 0.85,
    "POPULAR_SCIENCE": 0.60,
}


def find_doi(text: str) -> Optional[str]:
    """Estrai un DOI dal testo, se presente."""
    match = re.search(r"10\.\d{4,9}/[^\s\"'>)]+", text, re.IGNORECASE)
    if not match:
        return None
    doi = match.group(0).rstrip(".,;)")
    return doi


def fetch_citation_count(doi: str, timeout: float = 8.0) -> Optional[int]:
    """Recupera il numero di citazioni via Semantic Scholar (se disponibile)."""
    if requests is None:
        logger.debug("requests non disponibile; salto lookup citazioni")
        return None

    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    headers = {"x-api-key": api_key} if api_key else {}
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
    params = {"fields": "citationCount"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        count = data.get("citationCount")
        return int(count) if count is not None else None
    except Exception as exc:  # pragma: no cover - network dependent
        logger.debug("Lookup citazioni fallito per DOI %s: %s", doi, exc)
        return None


def _classify_document_type(
    text: str, classifier: Any, max_chars: int = 12000
) -> Tuple[str, float, str]:
    """Usa un LLM per classificare il documento e restituire doc_type, confidence, rationale."""
    if classifier is None:
        return "OTHER", 0.0, "classifier missing"

    prompt = DOC_TYPE_PROMPT.format(sample=text[:max_chars])
    try:
        response = classifier.invoke(prompt)
        raw_content: Any = getattr(response, "content", response)
        content_str = (
            raw_content if isinstance(raw_content, str) else json.dumps(raw_content)
        )
        data = json.loads(content_str)
        doc_type = str(data.get("doc_type") or data.get("type") or "OTHER").upper()
        confidence = float(data.get("confidence", 0.0))
        rationale = str(data.get("rationale", ""))
        return doc_type, confidence, rationale
    except Exception as exc:
        logger.debug("Classificazione documento fallita: %s", exc)
        return "OTHER", 0.0, "classification failed"


def _trust_from_doc_type(doc_type: str) -> float:
    return DOC_TYPE_TRUST.get(doc_type.upper(), 0.5)


def calculate_trust_score(
    text: str,
    doi: Optional[str] = None,
    classifier: Any = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Calcola il Trust Score (0.0 - 1.0) usando DOI/citazioni o analisi strutturale.

    Returns:
        trust_score, details
    """
    base_score = 0.5

    if doi:
        citations = fetch_citation_count(doi)
        if citations is not None:
            if citations > 50:
                return 0.95, {"source": "citations", "doi": doi, "citations": citations}
            if citations > 0:
                return 0.85, {"source": "citations", "doi": doi, "citations": citations}
            return 0.80, {"source": "citations", "doi": doi, "citations": citations}
        # if lookup failed, fall back to structure

    doc_type, confidence, rationale = _classify_document_type(text, classifier)
    trust = _trust_from_doc_type(doc_type) if doc_type else base_score

    return trust, {
        "source": "structure",
        "doc_type": doc_type,
        "confidence": confidence,
        "rationale": rationale,
    }


__all__ = [
    "calculate_trust_score",
    "find_doi",
    "fetch_citation_count",
]


# -----------------------------------------------------------------------------
# Bibliographer class (OpenAlex/Wikidata heuristics)
# -----------------------------------------------------------------------------

class Bibliographer:
    """
    Biblioteca e motore di fiducia locale-first:
    - Se online, prova OpenAlex per citazioni/retrazioni
    - Se offline, degrada senza bloccare
    """

    def __init__(self) -> None:
        self.openalex_url = "https://api.openalex.org/works"
        self.wikidata_url = "https://query.wikidata.org/sparql"
        self.headers = {"User-Agent": "NeuroGraph/1.0 (mailto:researcher@local.test)"}

    def get_trust_score(self, title: str, doc_type_detected: str) -> float:
        """
        Calcola il punteggio di affidabilità (0.0 - 1.0) combinando
        euristiche locali e dati bibliometrici remoti.
        """
        base_score = 0.5

        # 1. Gerarchia Locale (Priority Override)
        if doc_type_detected.lower() in {"note", "lab_note", "labnote"}:
            return 1.0  # La verità sperimentale dell'utente vince sempre

        # 2. Validazione Bibliometrica (OpenAlex)
        alex_data = self._query_openalex(title)
        if alex_data:
            citations = alex_data.get("cited_by_count", 0)
            is_retracted = alex_data.get("is_retracted", False)

            if is_retracted:
                return 0.1  # Paper ritirato!

            if citations > 100:
                return 0.95
            if citations > 10:
                return 0.85
            return 0.75  # Pubblicato ma poco citato

        # 3. Fallback Euristico
        if doc_type_detected.upper() in {"TEXTBOOK"}:
            return 0.90
        if doc_type_detected.upper() in {"PAPER", "EXPERIMENTAL_STUDY", "REVIEW_ARTICLE"}:
            return 0.70

        return base_score

    def validate_triple_with_wikidata(self, subject: str, object: str) -> bool:
        """
        Verifica se una relazione tra due concetti esiste già in Wikidata.
        Placeholder: restituisce sempre False per evitare rallentamenti.
        """
        if not subject or not object:
            return False

        # Nota: l'implementazione reale richiederebbe reconciliation + pathfinding SPARQL
        return False

    def _query_openalex(self, title: str) -> Optional[Dict]:
        """Cerca il documento su OpenAlex per titolo."""
        if requests is None:  # type: ignore[truthy-function]
            return None
        try:
            params = {"search": title, "per_page": 1}
            response = requests.get(self.openalex_url, params=params, headers=self.headers, timeout=3)
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    return results[0]
        except Exception as exc:
            logger.warning("OpenAlex offline o errore: %s", exc)
        return None


# Istanza globale
bibliographer = Bibliographer()

__all__.extend(["Bibliographer", "bibliographer"])