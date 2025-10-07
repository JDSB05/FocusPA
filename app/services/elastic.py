import os
from elasticsearch import Elasticsearch
import requests

def get_client() -> Elasticsearch:
    """Create an Elasticsearch client using environment vars."""
    url = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200') # elasticsearch URL
    # health check
    req = requests.get(f"{url}/_cluster/health")
    if req.status_code != 200:
        print(f"[ERROR] Failed to connect to Elasticsearch at {url}: {req.text}")
        raise ValueError(f"Cannot connect to Elasticsearch at {url}")
    print(f"[INFO] Elasticsearch connected at {url}")
    return Elasticsearch(url)

from elasticsearch import Elasticsearch
from datetime import datetime, timedelta
import random

def create_fake_winlogs(count: int = 5):
    """Insert ``count`` synthetic Windows logs into Elasticsearch."""

    es = get_client()

    # índice diário no formato do Winlogbeat
    index_name = f"winlog-{datetime.utcnow():%Y.%m.%d}"

    descriptions = [
        "Serviço iniciado com sucesso.",
        "Falha ao reiniciar o serviço.",
        "Atualização aplicada com sucesso.",
        "Erro de autenticação detectado.",
        "Política de segurança aplicada."
    ]
    providers = ["Microsoft-Windows-Security-SPP", "Microsoft-Windows-Sysmon"]
    levels = ["information", "warning", "error"]
    now = datetime.utcnow()

    try:
        iterations = max(int(count), 0)
    except (TypeError, ValueError):
        iterations = 0

    actions = []
    for i in range(iterations):
        doc = {
            "@timestamp": (now - timedelta(minutes=i * 10)).isoformat() + "Z",
            "message": random.choice(descriptions),
            "event.provider": random.choice(providers),
            "winlog.event_id": str(random.randint(100, 999)),
            "winlog.process.pid": random.randint(1000, 50000),
            "log.level": random.choice(levels)
        }
        actions.append({"create": {"_index": index_name}})
        actions.append(doc)

    res = es.bulk(body=actions)
    print(f"[INFO] Insert bulk no índice '{index_name}' completo.")

es = get_client()
