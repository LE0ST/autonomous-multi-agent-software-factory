"""
orchestrator/env_loader.py - Cargador automático de credenciales para apis.txt y .env.
Detecta y mapea claves tanto en formato apis.txt (gemini=, deepseek=, glm=) como .env estándar.
"""

import os
from pathlib import Path

def load_api_keys(repo_root: Path = None):
    """Carga credenciales desde apis.txt o .env si existen en el directorio raíz."""
    root = repo_root or Path.cwd()

    # 1. Leer apis.txt si existe
    apis_file = root / "apis.txt"
    if apis_file.exists():
        try:
            for line in apis_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().lower()
                v = v.strip().strip("'\"")
                
                if k in ["gemini", "gemini_api_key"] and not os.getenv("GEMINI_API_KEY"):
                    os.environ["GEMINI_API_KEY"] = v
                elif k in ["deepseek", "deepseek_api_key"] and not os.getenv("DEEPSEEK_API_KEY"):
                    os.environ["DEEPSEEK_API_KEY"] = v
                elif k in ["glm", "glm_api_key"] and not os.getenv("GLM_API_KEY"):
                    os.environ["GLM_API_KEY"] = v
        except Exception:
            pass

    # 2. Leer .env si existe
    env_file = root / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and not os.getenv(k):
                    os.environ[k] = v
        except Exception:
            pass
