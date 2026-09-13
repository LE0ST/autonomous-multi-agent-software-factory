import re
import os
import json
import requests
from pathlib import Path
from typing import Optional
from .network_retry import retry_with_backoff

def clean_code_block(content: str) -> str:
    """Limpia etiquetas de bloques Markdown (```python ... ```) y espacios residuales."""
    text = content.strip()
    pattern = r"^```[a-zA-Z0-9_\-\.]*\r?\n(.*?)```$"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip() + "\n"
    
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
        
    return "\n".join(lines).strip() + "\n"

def extract_and_write_files(raw_response: str, worktree_path: Path) -> list[str]:
    """
    Extrae de forma robusta archivos del texto devuelto por el Worker y los escribe en el worktree.
    Soporta:
      1. Formato JSON: {"files": [{"path": "...", "content": "..."}]}
      2. Formato delimitado por encabezados: ### FILE: <path> \n ```python \n ... ```
      3. Bloques etiquetados: File: `<path>` \n ``` ... ```
    """
    written_files = []
    
    # 1. Intentar parsear como JSON directo (extrayendo entre la primera { y última })
    first_brace = raw_response.find("{")
    last_brace = raw_response.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate_json = raw_response[first_brace:last_brace + 1]
        try:
            data = json.loads(candidate_json, strict=False)
            if isinstance(data, dict) and "files" in data and isinstance(data["files"], list):
                for item in data["files"]:
                    rel_path = item.get("path", "").strip().replace("\\", "/").lstrip("/")
                    content = clean_code_block(item.get("content", ""))
                    if rel_path:
                        dest = worktree_path / rel_path
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_text(content, encoding="utf-8")
                        written_files.append(rel_path)
                if written_files:
                    return written_files
        except Exception:
            pass

    # 2. Parsear bloques delimitados por FILE / Archivo
    file_block_regex = re.compile(
        r"(?:###|##|\*\*|---\s*\n)?\s*(?:FILE|ARCHIVO|File|Archivo)\s*[:\`]?\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+)[\`\s\*]*\n+```[a-zA-Z0-9_\-]*\r?\n(.*?)```",
        re.DOTALL | re.IGNORECASE
    )
    
    matches = file_block_regex.findall(raw_response)
    if matches:
        for rel_path, code_body in matches:
            norm_path = rel_path.strip().replace("\\", "/").lstrip("/")
            dest = worktree_path / norm_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(clean_code_block(code_body), encoding="utf-8")
            written_files.append(norm_path)
        return written_files

    # 3. Fallback: buscar patrones genéricos de path seguido de bloque de código
    generic_block_regex = re.compile(
        r"([a-zA-Z0-9_\-\./\\]+\.(?:py|ts|js|json|md))\s*:\s*\n+```[a-zA-Z0-9_\-]*\r?\n(.*?)```",
        re.DOTALL
    )
    matches_generic = generic_block_regex.findall(raw_response)
    if matches_generic:
        for rel_path, code_body in matches_generic:
            norm_path = rel_path.strip().replace("\\", "/").lstrip("/")
            dest = worktree_path / norm_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(clean_code_block(code_body), encoding="utf-8")
            written_files.append(norm_path)
        return written_files

    return written_files

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
        system_prompt = (
            "Actúa como Senior Software Engineer en un entorno de desarrollo autónomo. "
            "Debes implementar los archivos requeridos por la especificación respetando estrictamente RULES.md.\n"
            "Formato de respuesta OBLIGATORIO: Por cada archivo que debas crear o modificar, utiliza la sintaxis:\n"
            "### FILE: <ruta_relativa>\n"
            "```<lenguaje>\n"
            "<código fuente completo sin truncar>\n"
            "```\n"
            "Solo modifica archivos permitidos. No incluyas explicaciones conversacionales fuera de estos bloques."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Especificación:\n{spec_content}\nFeedback de fallos:\n{json.dumps(triage_feedback or {})}"}
        ]
        resp = requests.post(url, json={"model": self.model, "messages": messages}, headers=headers, timeout=60)
        resp.raise_for_status()
        raw_text = resp.json()["choices"][0]["message"]["content"]
        
        written = extract_and_write_files(raw_text, worktree_path)
        if not written:
            raise ValueError(f"El modelo no devolvió archivos con formato reconocible (### FILE: <path>). Respuesta:\n{raw_text[:300]}")
        return written
