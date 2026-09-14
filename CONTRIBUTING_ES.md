# Guía de Contribución — Autonomous Multi-Agent Software Factory

[English](CONTRIBUTING.md) | Español

Gracias por tu interés en contribuir a **Autonomous Multi-Agent Software Factory**. Este proyecto explora la ingeniería de software autónoma gobernada por máquinas de estados finitos (FSM), compuertas deterministas y aislamiento estricto mediante Git worktrees.

---

## 1. Principios Fundamentales del Proyecto

1. **Determinismo sobre Heurística:** Las decisiones de calidad, seguridad e integración no dependen del juicio de un LLM si pueden validarse deterministamente mediante código (pruebas de cobertura, diff gates, linters SAST, fast-forward merges).
2. **Principio de Menor Autoridad (Least Privilege):** Ningún agente (especialmente el Worker) tiene acceso a modificar archivos fuera de los explícitamente autorizados en la especificación técnica de la tarea (`specs/TASK-XXX.md`).
3. **Inviolabilidad de las Compuertas:** Ninguna compuerta del pipeline puede ser deshabilitada o debilitada para forzar la integración de código.

---

## 2. Configuración del Entorno de Desarrollo

### Requisitos Previos
* **Python:** `>= 3.10`
* **Git:** `>= 2.30`
* **Semgrep:** `>= 1.0.0` (para análisis SAST)

### Instalación en Entorno Virtual

En Windows (PowerShell):
```powershell
# Clonar el repositorio y posicionarse en la raíz
cd autonomous-multi-agent-software-factory

# Crear y activar entorno virtual
python -m venv .venv
.venv\Scripts\Activate.ps1

# Instalar dependencias del proyecto en modo editable
pip install -e .
```

En Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Configuración de Credenciales
Copia el archivo de plantilla `.env.example` a `.env`:
```powershell
cp .env.example .env
```
Configura tus claves para los proveedores de modelos que desees utilizar:
* `GEMINI_API_KEY`: Requerida para Architect, Triage, Security Filter y Logic Security.
* `DEEPSEEK_API_KEY`: Requerida para el Worker (generador de código y tests).
* `GLM_API_KEY`: Opcional para Logic Security con Zhipu GLM.
* `DASHSCOPE_API_KEY`: Opcional para fallback de Logic Security con Qwen (`qwen3.8-flash`).

> [!CAUTION]
> **Nunca comittees ni envíes archivos `.env` o credenciales reales.** El repositorio ignora activamente `.env` y archivos de credenciales. Cualquier contribución que incluya secretos en texto plano será rechazada de inmediato.

---

## 3. Estrategia de Ramas y Flujo de Trabajo

* **Rama de Integración Base:** `dev`. Toda integración de código se realiza exclusivamente mediante avance rápido Fast-Forward (`--ff-only`).
* **Ramas de Tarea:** `task/TASK-XXX`.
* **Aislamiento por Worktrees:** El orquestador opera dentro de Git worktrees aislados en `.worktrees/wt_TASK-XXX`, garantizando que la copia de trabajo principal permanezca intacta durante la generación de código, ejecución de pruebas y análisis estático.
* **Recuperación Determinista:** Si una tarea autorizada se detiene en `AUTO_MERGE` (árbol sucio) o `LOGIC_AUDIT` (límites transitorios HTTP 429/503), utiliza los comandos autorizados `--resume-merge` o `--resume-audit` respectivamente. Ninguna de estas vías elude las compuertas de verificación ni realiza rebases automáticos si se detecta divergencia de ramas.

---

## 4. Estructura de Tareas y Especificaciones

Toda nueva tarea debe formalizarse en `specs/TASK-XXX.md` utilizando [`specs/TEMPLATE.md`](specs/TEMPLATE.md) como plantilla canónica:

* **Objetivo claro y conciso de la tarea.**
* **Tabla de Invariantes Lógicos y de Seguridad (`SEC-XX` / `LOG-XX`):** Reglas inviolables que deben verificarse tanto mediante pruebas unitarias como por la auditoría semántica de seguridad lógica.
* **Archivos Permitidos (Allowed Files):** Lista blanca explícita de rutas que el Worker está autorizado a crear o modificar.
* **Archivos Prohibidos (Forbidden Files):** Rutas protegidas de la infraestructura del repositorio (archivos de raíz, configuración, núcleo del orquestador, compuertas de verificación).
* **Umbral de Cobertura:** Porcentaje mínimo de cobertura de líneas exigido (por defecto $\ge 85\%$).

---

## 5. Validación y Suite de Pruebas

Antes de proponer cualquier cambio al orquestador o a los componentes del sistema:

```powershell
# 1. Verificar formato y espacios
git diff --check

# 2. Ejecutar la suite completa de pruebas unitarias e integración
python -m pytest -v tests/
```

Las 202 pruebas existentes deben pasar al 100%. No está permitido comentar, eludir ni eliminar pruebas existentes para facilitar aprobaciones.

---

## 6. Proceso de Pull Request

1. Asegúrate de que `dev` esté actualizado y que tu rama esté rebasada limpiamente sobre `dev`.
2. Verifica que `git status` reporte el árbol completamente limpio.
3. Envía tu PR con una descripción clara de:
   * Qué problema resuelve o qué compuerta/adaptador mejora.
   * Pruebas añadidas para verificar la funcionalidad.
   * Confirmación de que todas las compuertas y presupuestos de la FSM continúan respetándose.
