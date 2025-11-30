"""
Streamlit page: Validator

Shows provisional triples from Neo4j and lets the user validate them.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from src.graph.db_connector import graph_db

PAGE_LIMIT = 200


def fetch_provisional_triples(limit: int = PAGE_LIMIT) -> List[Dict[str, Any]]:
    query = """
    MATCH (s)-[r:RELATION]->(o)
    WHERE coalesce(r.status, 'PROVISIONAL') = 'PROVISIONAL'
    RETURN id(r) AS rel_id,
           s.name AS subject,
           r.type AS predicate,
           o.name AS object,
           coalesce(r.status, 'PROVISIONAL') AS status,
           r.weight AS weight,
           r.sources AS sources
    ORDER BY rel_id DESC
    LIMIT $limit
    """
    return graph_db.query(query, {"limit": limit})


def commit_triples(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0

    query = """
    UNWIND $rows AS row
    MATCH (s)-[r:RELATION]->(o)
    WHERE id(r) = row.rel_id
    SET s.name = row.subject,
        r.type = toUpper(row.predicate),
        o.name = row.object,
        r.status = 'VALIDATED',
        r.validated_at = datetime()
    RETURN count(*) AS updated
    """
    res = graph_db.query(query, {"rows": rows})
    return res[0]["updated"] if res else 0


def to_records(edited) -> List[Dict[str, Any]]:
    if hasattr(edited, "to_dict"):
        return edited.to_dict("records")
    if isinstance(edited, list):
        return edited
    return []


def main() -> None:
    st.set_page_config(page_title="Validator", layout="wide")
    st.title("✅ Validator")
    st.caption("Rivedi le triple estratte e valida quelle corrette.")

    with st.spinner("Caricamento triple provvisorie..."):
        triples = fetch_provisional_triples()

    if not triples:
        st.success("Nessuna tripla in attesa di validazione.")
        return

    data = []
    for row in triples:
        data.append(
            {
                "selected": True,
                "rel_id": row.get("rel_id"),
                "subject": row.get("subject", ""),
                "predicate": row.get("predicate", ""),
                "object": row.get("object", ""),
                "status": row.get("status", "PROVISIONAL"),
                "weight": row.get("weight"),
                "sources": row.get("sources"),
            }
        )

    edited = st.data_editor(
        data,
        hide_index=True,
        use_container_width=True,
        column_config={
            "selected": st.column_config.CheckboxColumn("Seleziona", default=True),
            "rel_id": st.column_config.Column("Rel ID", disabled=True),
            "status": st.column_config.Column("Stato", disabled=True),
        },
        key="validator_editor",
    )

    if st.button("Commit selezionati"):
        records = to_records(edited)
        selected = [
            {
                "rel_id": int(r["rel_id"]),
                "subject": str(r.get("subject", "")),
                "predicate": str(r.get("predicate", "")),
                "object": str(r.get("object", "")),
            }
            for r in records
            if r.get("selected")
        ]
        if not selected:
            st.warning("Nessuna riga selezionata.")
            return

        updated = commit_triples(selected)
        st.success(f"Confermate {updated} relazioni.")
        st.experimental_rerun()


if __name__ == "__main__":
    main()
