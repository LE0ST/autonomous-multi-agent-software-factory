"""
adapters/deepseek_adapter.py - Adaptador para DeepSeek (Worker / Code Generator)
con soporte dual: API real y Modo Simulación/Mock para pruebas sin consumo de tokens.
"""

import os
import json
import requests
from pathlib import Path
from typing import Optional
from .network_retry import retry_with_backoff

class DeepSeekAdapter:
    def __init__(self, model: str = "deepseek-chat", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.is_simulation = not bool(self.api_key)

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    def generate_code_and_tests(
        self,
        spec_content: str,
        worktree_path: Path,
        triage_feedback: Optional[dict] = None
    ) -> list[str]:
        """Rol Worker: Genera o actualiza el código y los tests dentro del worktree."""
        if self.is_simulation:
            # Generar archivos mock basados en la spec
            src_dir = worktree_path / "src" / "auth"
            src_dir.mkdir(parents=True, exist_ok=True)
            code_file = src_dir / "token_validator.py"
            code_file.write_text(
                "import hmac\nimport hashlib\n\ndef validate_token(token: str, secret: str = 'key') -> bool:\n"
                "    if not token or not isinstance(token, str):\n"
                "        return False\n"
                "    expected = hmac.new(secret.encode(), b'valid', hashlib.sha256).hexdigest()\n"
                "    return hmac.compare_digest(token, expected)\n",
                encoding="utf-8"
            )

            test_dir = worktree_path / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            test_file = test_dir / "test_token_validator.py"
            test_file.write_text(
                "import hmac\nimport hashlib\nfrom src.auth.token_validator import validate_token\n\n"
                "def test_token_empty():\n"
                "    assert validate_token('') is False\n"
                "    assert validate_token(None) is False\n\n"
                "def test_token_valid():\n"
                "    valid_token = hmac.new(b'key', b'valid', hashlib.sha256).hexdigest()\n"
                "    assert validate_token(valid_token) is True\n",
                encoding="utf-8"
            )
            return [str(code_file.relative_to(worktree_path)), str(test_file.relative_to(worktree_path))]

        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        messages = [
            {"role": "system", "content": "Actúa como Senior Software Engineer. Implementa código y tests respetando RULES.md."},
            {"role": "user", "content": f"Especificación:\n{spec_content}\nFeedback:\n{json.dumps(triage_feedback or {})}"}
        ]
        resp = requests.post(url, json={"model": self.model, "messages": messages}, headers=headers, timeout=45)
        resp.raise_for_status()
        # En producción el worker procesa y vuelca los parches al worktree
        return ["src/auth/token_validator.py", "tests/test_token_validator.py"]
