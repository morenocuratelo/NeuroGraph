"""
Streamlit entry point for NeuroGraph.

Features:
- Sidebar connection status (Neo4j, Ollama).
- Drag & drop area for documents (PDF/PPTX).
- Live log panel showing ingestion progress.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import List, Tuple

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from src.core.config import OLLAMA_BASE_URL
from src.graph.db_connector import graph_db
from src.ingestion.pipeline import ingestor


class StreamlitLogHandler(logging.Handler):
    """Capture logs and stream them into a Streamlit placeholder."""

    def __init__(self, placeholder: DeltaGenerator) -> None:
        super().__init__()
        self.placeholder = placeholder
        self.lines: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.lines.append(msg)
        self.placeholder.text("\n".join(self.lines))


def check_neo4j() -> Tuple[bool, str]:
    try:
        ok = graph_db.test_connection()
        return ok, "Connesso" if ok else "Non raggiungibile"
    except Exception as exc:
        return False, str(exc)


def check_ollama() -> Tuple[bool, str]:
    try:
        import requests  # type: ignore[import-not-found]

        resp = requests.get(OLLAMA_BASE_URL, timeout=3)
        return resp.ok, f"HTTP {resp.status_code}"
    except Exception as exc:
        return False, str(exc)


def save_uploaded_file(uploaded_file) -> Path:
    uploads_dir = Path("data/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=suffix, dir=uploads_dir
    ) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return Path(tmp.name)


def main() -> None:
    st.set_page_config(page_title="NeuroGraph Ingestion", layout="wide")
    st.title("📥 NeuroGraph - Ingestion")

    # Sidebar status
    st.sidebar.header("Stato connessioni")
    neo_status, neo_msg = check_neo4j()
    ollama_status, ollama_msg = check_ollama()
    st.sidebar.write(f"Neo4j: {'🟢' if neo_status else '🔴'} {neo_msg}")
    st.sidebar.write(f"Ollama: {'🟢' if ollama_status else '🔴'} {ollama_msg}")
    if st.sidebar.button("Ricarica stato"):
        st.rerun()

    st.markdown(
        "Carica un documento PDF o PPTX. L'ingestion avvierà analisi, estrazione triple e salvataggio in Neo4j."
    )

    uploaded = st.file_uploader("Trascina qui un PDF o PPTX", type=["pdf", "pptx"])
    start = st.button("Avvia ingestion")

    log_placeholder = st.empty()

    if start:
        if not uploaded:
            st.warning("Carica un file prima di procedere.")
            return

        ext = Path(uploaded.name).suffix.lower()
        if ext not in {".pdf", ".pptx"}:
            st.error("Formato non supportato. Usa PDF o PPTX.")
            return

        saved_path = save_uploaded_file(uploaded)
        st.info(f"File caricato: {saved_path.name}")

        handler = StreamlitLogHandler(log_placeholder)
        handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        target_loggers = [
            logging.getLogger("src.ingestion.pipeline"),
            logging.getLogger("src.graph.db_connector"),
        ]
        for lg in target_loggers:
            lg.setLevel(logging.INFO)
            lg.addHandler(handler)

        try:
            ingestor.process_document(str(saved_path))
            st.success("Ingestion completata.")
        except Exception as exc:  # pragma: no cover - runtime path
            st.error(f"Errore durante l'ingestion: {exc}")
        finally:
            for lg in target_loggers:
                lg.removeHandler(handler)


if __name__ == "__main__":
    main()
