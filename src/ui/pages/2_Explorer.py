"""
Streamlit page: Explorer

Semantic search + graph visualization using streamlit-agraph.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

from src.graph.db_connector import graph_db


def semantic_search(query: str) -> List[Dict[str, Any]]:
    cypher = """
    MATCH (c:Concept)
    WHERE toLower(c.name) CONTAINS toLower($q)
    OPTIONAL MATCH (c)-[r:RELATION]->(t:Concept)
    RETURN c.name AS source,
           labels(c) AS source_labels,
           t.name AS target,
           labels(t) AS target_labels,
           r.type AS rel_type,
           r.weight AS weight
    LIMIT 200
    """
    return graph_db.query(cypher, {"q": query})


def color_for_labels(labels: List[str]) -> str:
    labels_upper = {label.upper() for label in labels}
    if "ANATOMIA" in labels_upper or "ANATOMY" in labels_upper:
        return "#ff7f0e"
    if "MOLECOLA" in labels_upper or "MOLECULE" in labels_upper:
        return "#1f77b4"
    if "PATOLOGIA" in labels_upper or "PATHOLOGY" in labels_upper:
        return "#d62728"
    return "#7f7f7f"


def build_graph(rows: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    nodes: Dict[str, Node] = {}
    edges: List[Edge] = []

    for row in rows:
        src = row.get("source")
        tgt = row.get("target")
        rel = row.get("rel_type")
        if src and src not in nodes:
            nodes[src] = Node(
                id=src, label=src, color=color_for_labels(row.get("source_labels", []))
            )
        if tgt and tgt not in nodes:
            nodes[tgt] = Node(
                id=tgt, label=tgt, color=color_for_labels(row.get("target_labels", []))
            )
        if src and tgt and rel:
            edges.append(Edge(source=src, target=tgt, label=rel))

    return {"nodes": list(nodes.values()), "edges": edges}


def main() -> None:
    st.set_page_config(page_title="Explorer", layout="wide")
    st.title("🌐 Explorer")
    st.caption("Cerca concetti e visualizza il grafo.")

    query = st.text_input("Ricerca semantica", "")

    if st.button("Cerca") and query.strip():
        with st.spinner("Ricerca in corso..."):
            rows = semantic_search(query.strip())
        if not rows:
            st.info("Nessun risultato trovato.")
            return

        graph = build_graph(rows)
        config = Config(
            width=1200,
            height=700,
            directed=True,
            physics=True,
            hierarchical=False,
        )
        agraph(
            nodes=graph["nodes"],
            edges=graph["edges"],
            config=config,
        )
    else:
        st.info("Inserisci un termine di ricerca e premi 'Cerca'.")


if __name__ == "__main__":
    main()
