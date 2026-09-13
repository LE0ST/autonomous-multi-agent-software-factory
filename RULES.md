# WORKER GOVERNANCE RULES & DIRECTIVES

Como agente Worker de la Autonomous Multi-Agent Software Factory, estás sujeto a las siguientes reglas inquebrantables de ejecución y límites de autoridad:

## 1. Principio de Menor Privilegio (Least Authority)
- Solo tienes autorización para crear o modificar los archivos explícitamente listados en la sección `Archivos permitidos` de la especificación técnica activa (`specs/TASK-XXX.md`).
- Tienes **estrictamente prohibido** acceder, crear o modificar cualquier archivo listado en `Archivos estrictamente prohibidos`.
- Cualquier modificación fuera de los límites autorizados será rechazada de inmediato por `diff_gate.py` antes de la fase de pruebas.

## 2. Inviolabilidad de Archivos Raíz y Configuración
- Está terminantemente prohibido modificar archivos de configuración base del repositorio, incluyendo pero no limitándose a:
  - `pyproject.toml`
  - `package.json`
  - `.env`
  - `.gitignore`
  - `RULES.md`
  - Archivos dentro de `orchestrator/` o `scripts/`

## 3. Calidad de Código y Pruebas
- Toda nueva funcionalidad o corrección debe incluir pruebas unitarias asociadas.
- La cobertura global de código no debe ser inferior al umbral configurado (85%).
- Los tests existentes no deben ser eliminados, comentados ni debilitados para forzar el paso del pipeline.

## 4. Seguridad e Invariantes
- Queda estrictamente prohibido introducir llamadas inseguras a APIs del sistema (`eval`, `exec`, inyección de comandos shell sin sanitizar, credenciales en texto plano).
- Cualquier hallazgo reportado por `sast_runner.py` con severidad crítica detendrá el pipeline y requerirá subsanación obligatoria.
