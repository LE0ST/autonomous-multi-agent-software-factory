# TASK-002: Implementar validador seguro de contraseñas

## 1. Alcance y Fronteras
- Archivos permitidos:
  - src/auth/password_validator.py
  - 	ests/test_password_validator.py
- Archivos estrictamente prohibidos:
  - orchestrator/
  - specs/
  - src/auth/token_validator.py
  - 	ests/test_token_validator.py
  - orchestrator/config.json

## 2. Criterios de Aceptación (AC)
- [AC-01] Implementar una función alidate_password(password: str) -> bool que rechace contraseñas vacías, menores de 8 caracteres y aquellas que no contengan al menos una letra y un número.
- [AC-02] La función debe aceptar contraseñas que cumplan los requisitos mínimos y no debe almacenar, imprimir ni exponer la contraseña recibida.

## 3. Invariantes de Seguridad (SEC)
- [SEC-01] La contraseña recibida no debe escribirse en archivos, registros, salida estándar ni mensajes de error.
- [SEC-02] La implementación no debe almacenar contraseñas ni introducir credenciales, secretos, tokens o claves codificadas de forma fija en el código.

## 4. Matriz de Pruebas Requeridas (TEST)
- [TEST-01] Verificar que alidate_password rechaza valores vacíos, contraseñas menores de 8 caracteres y contraseñas que no contienen simultáneamente letras y números. (Cubre: [AC-01], [SEC-01])
- [TEST-02] Verificar que alidate_password acepta contraseñas válidas y que no produce salida por stdout/stderr ni persiste la contraseña recibida. (Cubre: [AC-02], [SEC-02])
