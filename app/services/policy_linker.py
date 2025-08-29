from __future__ import annotations

from ..extensions import db
from ..model import Anomaly, AnomalyPolicyLink
from ..services.chroma_client import chroma
from ..services.embeddings import embed


def link_anomaly_to_policy_chunks(anomaly: Anomaly, top_k: int = 1) -> int:
    """Link an anomaly to the most relevant policy chunk(s) in Chroma.

    Queries the "policies" collection using the anomaly description embedding and stores
    up to `top_k` links in `anomaly_policy_links`. Returns the number of links created.
    Safe to call multiple times; duplicate chunk links for the same anomaly are ignored.
    """
    try:
        text = (anomaly.description or "").strip()
        if not text:
            return 0

        vec = embed([text])[0]
        col = chroma.get_or_create_collection("policies")
        res = col.query(query_embeddings=[vec], n_results=top_k)

        ids = (res.get("ids") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        created = 0
        for i, meta in enumerate(metas):
            chunk_id = ids[i] if i < len(ids) else None
            distance = float(dists[i]) if i < len(dists) and dists[i] is not None else None
            policy_name = (meta or {}).get("name") or (meta or {}).get("policy_name")
            chunk_index = (meta or {}).get("chunk_index")
            if not policy_name:
                continue

            # skip duplicates
            exists = AnomalyPolicyLink.query.filter_by(
                anomaly_id=anomaly.id,
                chunk_id=chunk_id
            ).first()
            if exists:
                continue

            link = AnomalyPolicyLink(
                anomaly_id=anomaly.id,
                policy_name=policy_name,
                chunk_id=chunk_id,
                chunk_index=chunk_index,
                distance=distance,
            )
            db.session.add(link)
            created += 1

        if created:
            db.session.commit()
        return created
    except Exception as e:
        print(f"[WARN] Failed to link anomaly {anomaly.id} to policy chunks: {e}")
        db.session.rollback()
        return 0

