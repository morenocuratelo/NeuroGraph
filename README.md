🧠 NeuroGraph: Local-First Multimodal Semantic Wiki

NeuroGraph trasforma documenti (PDF, PPTX, EPUB, immagini) in un grafo di conoscenza locale, con estrazione di triple, analisi visiva e validazione umana.

## Cosa fa
- Ingestione multimodale: PDF/PPTX (auto-convertito via PowerPoint), EPUB (testo), immagini da PDF (PyMuPDF) con descrizione VLM.
- Estrazione/analisi: Llama 3.2 Vision per immagini, Llama 3.1 per classificazione/JSON, Llama 3.3 70B (quantizzato) per ragionamento e triple.
- Dynamic Trust: DOI + citazioni (Semantic Scholar / OpenAlex) + classificazione LLM (Bibliographer); fallback locale-first se offline.
- Grafo Neo4j: nodi `Concept`, relazioni `RELATION` con `status` (`PROVISIONAL` → `VALIDATED`).
- UI Streamlit: upload/ingestion, validazione triple (data editor), esplorazione grafo (streamlit-agraph).

## Requisiti
- Python 3.10+
- Neo4j in esecuzione (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` in `.env`)
- Ollama attivo (`OLLAMA_BASE_URL`, default `http://localhost:11434`)
- PowerPoint installato (per PPTX→PDF via COM) oppure LibreOffice se vuoi usare `convert_pptx_to_pdf`.
- Facoltativo: `SEMANTIC_SCHOLAR_API_KEY` per maggiori limiti; accesso rete per OpenAlex/Semantic Scholar.

## Installazione rapida
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # se presente
# Oppure installa i pacchetti chiave:
pip install streamlit streamlit-agraph requests pywin32 pymupdf ebooklib \
    langchain-ollama langchain-core neo4j python-dotenv
```
Scarica i modelli Ollama usati di default:
```
ollama pull llama3.1:8b-instruct-fp16
ollama pull llama3.2-vision:11b
ollama pull llama3.3:70b-instruct-q4_K_M
ollama pull nomic-embed-text
```

## Configurazione
Compila `.env` nella root con:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
OLLAMA_BASE_URL=http://localhost:11434
SEMANTIC_SCHOLAR_API_KEY=...   # opzionale
```

## Uso
1) Avvia Neo4j e Ollama.
2) Esegui l'app Streamlit:
```
streamlit run app.py
```
3) Pagine:
   - Ingestion (home): drag & drop PDF/PPTX, log live, ingest nel grafo.
   - Validator (`src/ui/pages/1_Validator.py`): tabella editabile di triple `PROVISIONAL`; commit → `VALIDATED`.
   - Explorer (`src/ui/pages/2_Explorer.py`): ricerca semantica + visualizzazione grafo (colori per tipo: Anatomia/Arancio, Molecola/Blu, Patologia/Rosso).

## Percorsi chiave
- `app.py` – entry Streamlit, stato connessioni, upload.
- `src/ingestion/pipeline.py` – ingestion multimodale, trust dinamico, salvataggio Neo4j.
- `src/ingestion/converters.py` – PPTX→PDF (PowerPoint COM/LibreOffice), EPUB→testo, estrazione immagini.
- `src/ingestion/bibliographer.py` – trust scoring (DOI/citazioni, doc-type LLM, fallback).
- `src/graph/db_connector.py` – singleton Neo4j.
- `src/core/config.py` – modelli Ollama, percorsi dati, .env loader.
- `src/core/prompt_manager.py` & `src/core/prompts.json` – prompt LLM centralizzati.
- `src/ui/pages/` – pagine Streamlit (Validator, Explorer).

## Note
- Se PyMuPDF dà `ModuleNotFoundError: frontend`, reinstalla: `pip uninstall -y fitz PyMuPDF && pip install --no-cache-dir PyMuPDF`.
- Per rimuovere warning Bandit su `subprocess`, sono già marcati come `# nosec` (uso controllato).
- Librerie opzionali: `python-dotenv` (caricamento .env), `requests` (API esterne), `pywin32` (PowerPoint COM).
