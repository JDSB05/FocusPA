import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Tuple

# podes sobrepor o caminho via env var ANOMALY_POLICY_PATH
_POLICY_PATH = Path(os.getenv("ANOMALY_POLICY_PATH", "app/policy.json")).resolve()
_cache = {"mtime": None, "data": {"admins": [], "dirs": [], "custom_prompt": ""}}

def load_policy(force: bool = False) -> Dict[str, Any]:
    """Carrega a policy de um ficheiro JSON (com cache por mtime)."""
    try:
        mtime = _POLICY_PATH.stat().st_mtime
    except FileNotFoundError:
        return _cache["data"]  # default vazio

    if force or _cache["mtime"] != mtime:
        with _POLICY_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # defaults mínimos
        data.setdefault("admins", [])
        data.setdefault("dirs", [])
        data.setdefault("custom_prompt", "")
        _cache["mtime"] = mtime
        _cache["data"] = data
    return _cache["data"]

def build_policy_context_for_prompt() -> str:
    """Devolve um bloco de texto para meter no prompt do LLM (apenas contexto)."""
    p = load_policy()
    admins = ", ".join(p.get("admins") or []) or "—"
    # damos também a versão JSON para o LLM conseguir fazer match mais fiável
    dirs_json = json.dumps(p.get("dirs") or [], ensure_ascii=False)
    extra = p.get("custom_prompt") or ""
    return f"""
Contexto de permissões (apenas referência; não vinculativo):
- Admins (acesso generalista): {admins}
- Diretórios sensíveis (JSON): {dirs_json}
- Notas extra: {extra}
""".strip()

def _validate_policy_dict(data: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "Policy deve ser um objeto JSON."
    # admins
    admins = data.get("admins", [])
    if not isinstance(admins, list) or not all(isinstance(a, str) for a in admins):
        return False, '"admins" deve ser uma lista de strings.'
    # dirs
    dirs = data.get("dirs", [])
    if not isinstance(dirs, list):
        return False, '"dirs" deve ser uma lista.'
    for i, d in enumerate(dirs):
        if not isinstance(d, dict):
            return False, f'"dirs[{i}]" deve ser um objeto.'
        if "path" not in d or not isinstance(d["path"], str) or not d["path"].strip():
            return False, f'"dirs[{i}].path" em falta ou inválido.'
        aus = d.get("allowed_users", [])
        if not isinstance(aus, list) or not all(isinstance(u, str) for u in aus):
            return False, f'"dirs[{i}].allowed_users" deve ser lista de strings.'
    # custom_prompt
    if "custom_prompt" in data and not isinstance(data["custom_prompt"], str):
        return False, '"custom_prompt" deve ser string.'
    return True, ""

def save_policy(data: Dict[str, Any]) -> Dict[str, Any]:
    """Valida e guarda a policy de forma atómica; atualiza cache."""
    ok, msg = _validate_policy_dict(data)
    if not ok:
        raise ValueError(msg)

    # write atomicamente
    _POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=_POLICY_PATH.name, dir=str(_POLICY_PATH.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, _POLICY_PATH)  # atómico no mesmo FS
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    # refresh cache
    _cache["mtime"] = _POLICY_PATH.stat().st_mtime
    _cache["data"] = data
    return data