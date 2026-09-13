import pytest
from pathlib import Path
from adapters.deepseek_adapter import clean_code_block, extract_and_write_files

def test_clean_code_block_with_python_fences():
    raw = "```python\ndef foo():\n    return 42\n```"
    cleaned = clean_code_block(raw)
    assert cleaned == "def foo():\n    return 42\n"
    assert "```" not in cleaned

def test_clean_code_block_with_empty_language_fences():
    raw = "```\nprint('hello world')\n```"
    cleaned = clean_code_block(raw)
    assert cleaned == "print('hello world')\n"
    assert "```" not in cleaned

def test_clean_code_block_without_fences():
    raw = "x = 10\ny = 20\n"
    cleaned = clean_code_block(raw)
    assert cleaned == "x = 10\ny = 20\n"

def test_extract_and_write_files_header_blocks(tmp_path):
    response = """
Here is the implementation:

### FILE: src/auth/validator.py
```python
def check_auth(token: str) -> bool:
    return bool(token)
```

### FILE: tests/test_validator.py
```python
from src.auth.validator import check_auth

def test_check_auth():
    assert check_auth("abc") is True
```
"""
    written = extract_and_write_files(response, tmp_path)
    assert "src/auth/validator.py" in written
    assert "tests/test_validator.py" in written
    
    val_file = tmp_path / "src" / "auth" / "validator.py"
    assert val_file.exists()
    assert "```" not in val_file.read_text(encoding="utf-8")
    assert "def check_auth" in val_file.read_text(encoding="utf-8")

def test_extract_and_write_files_json_format(tmp_path):
    response = """
```json
{
  "files": [
    {
      "path": "src/utils.py",
      "content": "```python\ndef helper():\n    pass\n```"
    }
  ]
}
```
"""
    written = extract_and_write_files(response, tmp_path)
    assert "src/utils.py" in written
    f = tmp_path / "src" / "utils.py"
    assert f.exists()
    assert "def helper():\n    pass\n" in f.read_text(encoding="utf-8")
    assert "```" not in f.read_text(encoding="utf-8")
