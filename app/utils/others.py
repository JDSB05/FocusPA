from flask import request

def get_client_ip():
    """Obtém o IP real do cliente, considerando proxies."""
    if request.headers.get("X-Forwarded-For"):
        # Pode conter vários IPs separados por vírgula → usar o primeiro (origem)
        return request.headers.get("X-Forwarded-For").split(",")[0].strip() # type: ignore
    return request.remote_addr
