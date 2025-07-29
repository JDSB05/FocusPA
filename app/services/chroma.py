import os
import requests


class ChromaService:
    """Minimal client for the Chroma DB REST API."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.environ.get('CHROMA_URL', 'http://localhost:8000')

    def health(self) -> bool:
        try:
            resp = requests.get(f'{self.base_url}/api/health')
            return resp.ok
        except Exception:
            return False


def get_client() -> ChromaService:
    return ChromaService()


chroma = get_client()
