import os
import random
from datetime import datetime, timedelta
from typing import Optional

import requests
from elasticsearch import Elasticsearch


def get_client() -> Elasticsearch:
    """Create an Elasticsearch client using environment vars."""

    url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
    req = requests.get(f"{url}/_cluster/health")
    if req.status_code != 200:
        print(f"[ERROR] Failed to connect to Elasticsearch at {url}: {req.text}")
        raise ValueError(f"Cannot connect to Elasticsearch at {url}")
    print(f"[INFO] Elasticsearch connected at {url}")
    return Elasticsearch(url)


def create_fake_winlogs(
    num_logs: int = 5,
    *,
    seed: Optional[int] = None,
    interval_minutes: int = 10,
) -> None:
    """Generate deterministic Winlog-style events for testing.

    Parameters
    ----------
    num_logs:
        Number of synthetic entries that should be indexed.
    seed:
        Optional seed so multiple model runs can be executed under the exact
        same conditions (identical tokens/logs).
    interval_minutes:
        Temporal spacing between generated events.
    """

    if num_logs <= 0:
        raise ValueError("'num_logs' must be a positive integer")

    es_client = get_client()

    rng = random.Random(seed)
    index_name = f"winlog-{datetime.utcnow():%Y.%m.%d}"

    descriptions = [
        "Serviço iniciado com sucesso.",
        "Falha ao reiniciar o serviço.",
        "Atualização aplicada com sucesso.",
        "Erro de autenticação detectado.",
        "Política de segurança aplicada.",
    ]
    providers = ["Microsoft-Windows-Security-SPP", "Microsoft-Windows-Sysmon"]
    levels = ["information", "warning", "error"]
    now = datetime.utcnow()

    actions = []
    for i in range(num_logs):
        doc = {
            "@timestamp": (now - timedelta(minutes=i * interval_minutes)).isoformat() + "Z",
            "message": rng.choice(descriptions),
            "event.provider": rng.choice(providers),
            "winlog.event_id": str(rng.randint(100, 999)),
            "winlog.process.pid": rng.randint(1000, 50000),
            "log.level": rng.choice(levels),
        }
        actions.append({"create": {"_index": index_name}})
        actions.append(doc)

    es_client.bulk(body=actions)
    print(
        f"[INFO] Insert bulk no índice '{index_name}' completo com {num_logs} eventos.",
        flush=True,
    )


es = get_client()
