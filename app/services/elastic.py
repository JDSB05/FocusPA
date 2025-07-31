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


es = get_client()
