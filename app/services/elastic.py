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

def create_fake_winlogs():
    es = get_client()
    template_name = "winlog-template"
    datastream_name = "winlog-2025.08.07"

    # 1. Criar index template habilitado para data stream (sempre)
    es.indices.put_index_template(
        name=template_name,
        body={
            "index_patterns": ["winlog-*"],
            "data_stream": {},
            "template": {
                "settings": {"number_of_shards": 1},
                "mappings": {
                    "properties": {
                        "@timestamp": {"type": "date"},
                        "message": {"type": "text"},
                        "event.provider": {"type": "keyword"},
                        "winlog.event_id": {"type": "keyword"},
                        "winlog.process.pid": {"type": "integer"},
                        "log.level": {"type": "keyword"},
                    }
                }
            },
            "priority": 500
        }
    )
    print(f"[INFO] Template '{template_name}' criado ou atualizado.")

    # 2. Só criar data stream se não existir
    if not es.indices.exists(index=datastream_name):
        es.indices.create_data_stream(name=datastream_name)
        print(f"[INFO] Data stream '{datastream_name}' criado.")
    else:
        print(f"[INFO] Data stream '{datastream_name}' já existe — a criação foi ignorada.")

    # 3. Inserir documentos no data stream usando bulk
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

    actions = []
    for i in range(5):
        doc = {
            "@timestamp": (now - timedelta(minutes=i * 10)).isoformat() + "Z",
            "message": random.choice(descriptions),
            "event.provider": random.choice(providers),
            "winlog.event_id": str(random.randint(100, 999)),
            "winlog.process.pid": random.randint(1000, 50000),
            "log.level": random.choice(levels)
        }
        actions.append({"create": {"_index": datastream_name}})
        actions.append(doc)

    res = es.bulk(body=actions)
    print(f"[INFO] Insert bulk no data stream completo. Resumo:")
    for item in res.get("items", []):
        print(item)

es = get_client()
