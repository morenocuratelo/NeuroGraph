"""
Multimodal Ingestion Pipeline.

Orchestra il processo di lettura documenti:
1. Estrazione testo e immagini da PDF (PyMuPDF).
2. Analisi visiva dei grafici con Llama 3.2 Vision.
3. Estrazione Triple (Knowledge Graph) con Llama 3.1.
4. Salvataggio in Neo4j.
"""

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import fitz  # type: ignore[import-untyped]  # PyMuPDF

# LangChain & Ollama
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

# Moduli interni
from src.core.config import OLLAMA_BASE_URL, OLLAMA_MODELS
from src.core.prompt_manager import PromptManager
from src.graph.db_connector import graph_db
from src.ingestion.bibliographer import (
    bibliographer,
    calculate_trust_score,
    find_doi,
)
from src.ingestion.converters import pptx_to_pdf_with_powerpoint

# Configurazione Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

prompts = PromptManager()
MAX_CONTENT_CHARS = 15000  # Llama 3.x supports large context; keep ample headroom


class IngestionPipeline:
    def __init__(self):
        # Inizializza i modelli Ollama
        self.vision_model = ChatOllama(
            model=OLLAMA_MODELS["vision"], base_url=OLLAMA_BASE_URL, temperature=0.1
        )
        self.extraction_model = ChatOllama(
            model=OLLAMA_MODELS[
                "classification"
            ],  # Usiamo il modello veloce/preciso per JSON
            base_url=OLLAMA_BASE_URL,
            temperature=0.0,  # Deterministico per JSON
            format="json",  # Forza output JSON
        )

    def process_document(self, file_path: str, trust_score: float = 0.85):
        """
        Processa un intero documento (PPTX convertito in PDF) pagina per pagina.
        """
        path = Path(file_path)
        if path.suffix.lower() == ".pptx":
            logger.info("Convertendo PPTX in PDF tramite PowerPoint (COM)...")
            path = pptx_to_pdf_with_powerpoint(path)

        if not path.exists():
            raise FileNotFoundError(f"File non trovato: {file_path}")

        logger.info(f"📄 Inizio processamento: {path.name} (Trust: {trust_score})")

        # PyMuPDF lacks type hints; treat as dynamic object
        doc = fitz.open(str(path))  # type: ignore[attr-defined]

        # Trust scoring dinamico (sovrascrive l'eventuale trust passato)
        text_sample = self._get_text_sample(doc)
        doi = find_doi(text_sample)
        trust_score, trust_meta = calculate_trust_score(
            text_sample,
            doi=doi,
            classifier=self.extraction_model,
        )
        # Ulteriore valutazione basata su OpenAlex / doc_type rilevato
        doc_type_detected = trust_meta.get("doc_type") or "Paper"
        biblio_score = bibliographer.get_trust_score(path.stem, doc_type_detected)
        trust_score = max(trust_score, biblio_score)
        logger.info(
            "🔎 Trust calcolato: %.2f (fonte: %s, dettagli: %s)",
            trust_score,
            trust_meta.get("source"),
            {k: v for k, v in trust_meta.items() if k != "source"},
        )

        # Creiamo il nodo Documento nel grafo
        self._create_document_node(path.name, trust_score)

        for page_num in range(len(doc)):
            page = cast(Any, doc[page_num])
            logger.info(f"  -- Elaborazione pagina {page_num + 1}/{len(doc)}...")

            # 1. Estrai Testo
            text_content = page.get_text()

            # 2. Estrai e Analizza Immagini
            image_descriptions = self._analyze_page_images(page)

            # 3. Sintesi del contenuto (Testo + Visione)
            full_page_content = (
                f"TESTO:\n{text_content}\n\nDESCRIZIONE FIGURE:\n{image_descriptions}"
            )

            # 4. Estrazione Conoscenza (Triple)
            knowledge = self._extract_knowledge(full_page_content)

            # 5. Salvataggio nel Grafo
            if knowledge:
                self._save_to_graph(knowledge, source_file=path.name)

        logger.info(f"✅ Processamento completato: {path.name}")

    def _get_text_sample(self, doc, max_pages: int = 3) -> str:
        """Estrae il testo dalle prime pagine per stima fiducia."""
        texts = []
        for idx in range(min(len(doc), max_pages)):
            page = doc[idx]
            try:
                texts.append(page.get_text())
            except Exception as exc:
                logger.debug(
                    "Impossibile estrarre testo da pagina %s: %s", idx + 1, exc
                )
        return "\n\n".join(texts)

    def _analyze_page_images(self, page) -> str:
        """Estrae immagini dalla pagina e chiede a Llama Vision di descriverle."""
        descriptions = []
        image_list = page.get_images(full=True)

        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]

            # Converti in base64 per Ollama
            img_b64 = base64.b64encode(image_bytes).decode("utf-8")

            # Chiedi a Llama Vision
            msg = HumanMessage(
                content=[
                    {"type": "text", "text": prompts.get("visual_analyst")},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                ]
            )
            try:
                response = self.vision_model.invoke([msg])
                descriptions.append(f"[Figura {img_index+1}]: {response.content}")
            except Exception as e:
                logger.warning(f"Errore visione immagine {img_index}: {e}")

        return "\n".join(descriptions)

    def _extract_knowledge(self, content: str) -> List[Dict]:
        """Usa LLM per estrarre triple JSON dal contenuto misto."""
        if len(content.strip()) < 50:
            return []

        prompt = prompts.format(
            "graph_extractor", text=content[:MAX_CONTENT_CHARS]
        )  # Tronca per sicurezza contestuale

        try:
            response = self.extraction_model.invoke(prompt)
            raw_content: Any = getattr(response, "content", response)
            content_str = (
                raw_content if isinstance(raw_content, str) else json.dumps(raw_content)
            )
            data = json.loads(content_str)
            triples: List[Dict[str, Any]] = []
            if isinstance(data, dict) and isinstance(data.get("triples"), list):
                triples = [t for t in data.get("triples", []) if isinstance(t, dict)]
            elif isinstance(data, list):
                triples = [t for t in data if isinstance(t, dict)]

            normalized: List[Dict[str, Any]] = []
            for t in triples:
                subj = t.get("subject") or t.get("s") or t.get("subj")
                pred = t.get("predicate") or t.get("p") or t.get("pred")
                obj = t.get("object") or t.get("o") or t.get("obj")
                if subj and pred and obj:
                    normalized.append(
                        {"subject": str(subj), "predicate": str(pred), "object": str(obj)}
                    )
            return normalized
        except json.JSONDecodeError:
            logger.error("Errore decoding JSON da LLM")
            return []
        except Exception as e:
            logger.error(f"Errore estrazione: {e}")
            return []

    def _create_document_node(self, filename: str, trust: float):
        query = """
        MERGE (d:Document {name: $name})
        SET d.trust_score = $trust, d.ingested_at = datetime()
        """
        graph_db.query(query, {"name": filename, "trust": trust})

    def _save_to_graph(self, triples: List[Dict], source_file: str):
        """Salva le triple in Neo4j collegandole al documento."""
        for triple in triples:
            if not all(k in triple for k in ("subject", "predicate", "object")):
                logger.warning("Tripla incompleta, salto: %s", triple)
                continue
            # Cypher query per inserire o aggiornare nodi e relazioni
            query = """
            MATCH (doc:Document {name: $source})
            
            MERGE (s:Concept {name: $subj})
            MERGE (o:Concept {name: $obj})
            
            MERGE (s)-[r:RELATION {type: $pred}]->(o)
            
            // Aggiornamento Bayesiano semplificato (Media pesata)
            ON CREATE SET r.weight = doc.trust_score, r.sources = [doc.name]
            ON MATCH SET r.weight = (r.weight + doc.trust_score) / 2, 
                         r.sources = r.sources + [doc.name]
            """
            params = {
                "source": source_file,
                "subj": triple["subject"],
                "pred": triple["predicate"].upper().replace(" ", "_"),
                "obj": triple["object"],
            }
            try:
                graph_db.query(query, params)
            except Exception as e:
                logger.error(f"Errore salvataggio tripla {triple}: {e}")


# Istanza globale
ingestor = IngestionPipeline()
