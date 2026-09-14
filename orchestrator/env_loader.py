"""
orchestrator/env_loader.py - Automatic credential loader for apis.txt and .env.
Detects and maps keys from both apis.txt format (gemini=, deepseek=, glm=) and standard .env.
"""

import os
from pathlib import Path

def load_api_keys(repo_root: Path = None):
    """Load credentials from apis.txt or .env if they exist in the root directory."""
    root = repo_root or Path.cwd()

    # 1. Read apis.txt if present
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
                elif k in ["qwen", "dashscope", "dashscope_api_key"] and not os.getenv("DASHSCOPE_API_KEY"):
                    os.environ["DASHSCOPE_API_KEY"] = v
        except Exception:
            pass

    # 2. Read .env if present
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
