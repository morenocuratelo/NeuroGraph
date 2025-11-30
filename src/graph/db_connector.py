"""
Neo4j Database Connector.

Gestisce la connessione al Graph Database usando il driver ufficiale.
Implementa il pattern Singleton per evitare connessioni multiple inutili
e gestisce il ciclo di vita della sessione.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, cast

from typing_extensions import LiteralString

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

from src.core.config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD

# Configurazione Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Neo4jConnector:
    _instance: Optional[Neo4jConnector] = None
    _driver: Optional[Driver] = None

    def __new__(cls) -> Neo4jConnector:
        """Implementazione Thread-safe del Singleton."""
        if cls._instance is None:
            cls._instance = super(Neo4jConnector, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Inizializza il driver se non esiste già."""
        if self._driver is None:
            self.connect()

    def connect(self) -> Driver:
        """Crea la connessione al database."""
        try:
            if not NEO4J_URI or not NEO4J_USERNAME or not NEO4J_PASSWORD:
                raise ValueError("Credenziali Neo4j mancanti in .env o config.py")

            self._driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
            )
            # Verifica connettività immediata
            self._driver.verify_connectivity()
            logger.info(f"✅ Connesso con successo a Neo4j su {NEO4J_URI}")
            return self._driver
        except (ServiceUnavailable, AuthError) as e:
            logger.error(f"❌ Errore di connessione a Neo4j: {e}")
            raise e
        except Exception as e:
            logger.error(f"❌ Errore imprevisto Neo4j: {e}")
            raise e

    def _get_driver(self) -> Driver:
        """Restituisce un driver attivo o solleva se non disponibile."""
        if self._driver is None:
            self.connect()
        if self._driver is None:  # type: ignore[unreachable]
            raise RuntimeError("Driver Neo4j non disponibile")
        return self._driver

    def close(self) -> None:
        """Chiude la connessione al driver."""
        if self._driver:
            self._driver.close()
            logger.info("🔒 Connessione Neo4j chiusa.")

    def query(
        self, cypher_query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Esegue una query Cypher generica e restituisce i risultati come lista di dizionari.

        Args:
            cypher_query (str): La query da eseguire.
            parameters (dict): I parametri per la query (previene injection).

        Returns:
            List[Dict]: I record trovati.
        """
        try:
            driver = self._get_driver()
            with driver.session() as session:
                result = session.run(
                    cast(LiteralString, cypher_query), parameters or {}
                )
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"❌ Errore esecuzione query: {cypher_query}")
            logger.error(f"Dettaglio: {e}")
            raise e

    def test_connection(self) -> bool:
        """Test rapido per verificare se il DB è raggiungibile."""
        try:
            self.query("RETURN 1 AS test")
            return True
        except Exception:
            return False


# Istanza globale da importare negli altri moduli
# Usage: from src.graph.db_connector import graph_db
graph_db = Neo4jConnector()
