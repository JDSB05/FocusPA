import os
from elasticsearch import Elasticsearch


def get_client() -> Elasticsearch:
    """Create an Elasticsearch client using environment vars."""
    url = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200')
    return Elasticsearch(url)


es = get_client()
