# TASK-001: Implementación de Módulo de Autenticación Básica de Tokens

## 1. Alcance y Fronteras
- Archivos permitidos:
  - `src/auth/token_validator.py`
  - `tests/test_token_validator.py`
- Archivos estrictamente prohibidos:
  - `src/core/security_keys.py`
  - `pyproject.toml`
  - `.env`

## 2. Criterios de Aceptación (AC)
- [AC-01] La función `validate_token` debe rechazar tokens vacíos o nulos retornando False.
- [AC-02] La función `validate_token` debe validar tokens con firma HMAC-SHA256 válida retornando True.

## 3. Invariantes de Seguridad (SEC)
- [SEC-01] No utilizar algoritmos criptográficos débiles o inseguros como MD5 o SHA1.
- [SEC-02] No registrar tokens o secretos en logs ni exponerlos en excepciones.

## 4. Matriz de Pruebas Requeridas (TEST)
- [TEST-01] Probar que tokens vacíos o malformados son rechazados de forma segura (Cubre: [AC-01], [SEC-02])
- [TEST-02] Probar que tokens firmados correctamente con HMAC-SHA256 son aceptados (Cubre: [AC-02], [SEC-01])
