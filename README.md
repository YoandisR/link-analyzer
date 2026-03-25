# 🔗 Link Analyzer PRO v5.2

> **Motor profesional de crawling, mapeo jerárquico y auditoría de enlaces web.**  
> Desarrollado por **Yoandis Rodríguez** · [GitHub](https://github.com/YoandisR) · curvadigital0@gmail.com

---

## ¿Qué es Link Analyzer PRO?

Link Analyzer PRO es un motor de crawling multihilo escrito en Python, diseñado para mapear de forma exhaustiva la estructura de enlaces de cualquier sitio web. Extrae, clasifica y verifica URLs internas y externas, genera representaciones jerárquicas del sitio y exporta los resultados en múltiples formatos para auditoría y análisis posterior.

Opera en dos modos: una **interfaz web interactiva** con visualización de grafo en tiempo real (D3.js), y un **modo CLI** con panel de métricas en terminal. Ambos modos comparten el mismo motor de crawling y soporte de memoria persistente.

Diseñado y probado en entornos móviles (**Termux / Android**) con rendimiento superior a **23 URLs/segundo** desde un Pixel 9 Pro XL.

---

## Arquitectura del Sistema

El proyecto se divide en cinco módulos funcionales independientes pero interconectados:

| Componente | Archivo | Función |
|---|---|---|
| **Exploración Táctica** | `link_analyzer_v5.2.py` | Crawling, grafos, memoria persistente |
| **Analizador Pro** | `analizador_pro.py` | Motor de análisis avanzado (patrones, seguridad, mapeo) |
| **Filtro de Resultados** | `filtrar_200.py` | Filtra URLs status 200, elimina duplicados, exporta por categoría |
| **Ejecución de Ataque** | `auto_attack.py` | Inyección SQLi, XSS, Path Traversal, SSTI, XXE, Open Redirect |
| **Logística y Comando** | `report_manager.py` | Archivo .tar.gz, PDF ejecutivo, resumen táctico |

### Módulos internos del motor principal

| Módulo | Responsabilidad |
|---|---|
| `QuantumBus` | Canal de eventos en tiempo real entre hilos de crawling |
| `PersistentMemory` | Checkpoints atómicos en JSON — reanuda donde se detuvo |
| `LinkEngine` | Motor de crawling, normalización, deduplicación y verificación |
| `generar_mapa_jerarquico` | Clasificador de estructura de directorios para el grafo D3.js |
| `WebHandler` | Servidor HTTP interno con API REST completa |
| `exportar_json / exportar_pdf` | Exportadores de resultados al workspace |

---

## Capacidades Comprobadas

**Sesiones de crawling:**

| Métrica | Resultado real |
|---|---|
| Enlaces procesados en sesión única (CLI) | **1.160.258** |
| Páginas rastreadas — sesión web (YouTube) | **146 páginas** |
| Enlaces encontrados — sesión web (YouTube) | **5.845 enlaces** |
| URLs con status 200 verificadas | **819 únicas** |
| Internos / Externos (YouTube) | **451 / 368** |
| Errores 4xx/5xx detectados | **411 (33.3%)** |
| Velocidad de crawling (Termux) | **23+ URLs/segundo** |

**Sesiones de ataque (AUTO ATTACK v2.0 ELITE):**

| Sesión | Pruebas | Tiempo | Velocidad | Vulnerables |
|---|---|---|---|---|
| Sesión completa A | 4.118 | 347.79s | 11.84 p/s | **259** |
| Sesión completa B | 4.118 | 343.16s | 12.00 p/s | **252** |
| Sesión rápida A | 1.278 | 110.38s | 11.58 p/s | 40 |
| Sesión rápida B | 783 | 101.26s | 7.73 p/s | 7 |

**Análisis de vulnerabilidades (REPORT MANAGER):**

| Categoría | Proporción |
|---|---|
| Path Traversal | **85.7%** (6 hits) |
| SQL Injection | **14.3%** (1 hit) |
| Parámetro más vulnerable | `?subid` → 5 veces |
| Segundo más vulnerable | `?hl` → 2 veces |
| Top payload | `..\..\windows\system32\drivers\etc\hosts` |

---

## Interfaz Web — Vista en Tiempo Real

La interfaz web corre en `127.0.0.1:5002` (puerto auto-asignado) y ofrece dos vistas:

**Vista Tabla** — lista paginada de URLs con:
- Badge de tipo (`INT` / `EXT`) y código de status (`200`, `404`, `5xx`)
- Nivel de profundidad por URL (`lvl 0`, `lvl 1`, etc.)
- Filtros rápidos: TODOS · INTERNOS · EXTERNOS · ACTIVOS · ERRORES
- Buscador por URL en tiempo real
- Exportación directa: `↓ CSV` · `↓ TXT` · `↓ JSON` · `↓ PDF`

**Vista Eje Central** — grafo jerárquico D3.js con:
- Nodos por directorio y archivo
- Zoom, arrastre y agrupación automática de nodos hoja
- Panel de métricas: páginas · enlaces · verificados

**Panel de Consola** integrado muestra el flujo en vivo:
```
14:29:19  [200] https://accounts.google.com/TOS...
14:29:20  Verificacion completada.
14:29:20  Analisis finalizado.
14:29:20  Sesion final guardada en disco.
```

---

## Instalación

```bash
# Clonar el repositorio
git clone https://github.com/YoandisR/link-analyzer.git
cd link-analyzer

# Instalar dependencias
pip install requests beautifulsoup4 urllib3 matplotlib --break-system-packages
```

---

## Modos de Operación

### A. Exploración — Link Analyzer PRO v5.2

```bash
# Interfaz web con grafo jerárquico en tiempo real
python3 link_analyzer_v5.2.py

# Modo CLI con panel de métricas en terminal
python3 link_analyzer_v5.2.py cli
```

**Parámetros** (vía interfaz web o CLI):

| Parámetro | Descripción | Default |
|---|---|---|
| `url` | Objetivo del crawling | — |
| `verificar` | Verifica código HTTP de cada enlace | `false` |
| `recursivo` | Sigue enlaces internos recursivamente | `false` |
| `profundidad` | Profundidad máxima de rastreo | `1` |
| `resume` | Reanuda desde último checkpoint | `false` |

**Características:**
- Crawling multihilo con `ThreadPoolExecutor` y deduplicación O(1)
- Grafo de fuerza dirigida (D3.js v7) con zoom, arrastre y agrupación de nodos hoja
- Checkpoint automático cada 500 URLs o 60 segundos — botón REANUDAR siempre visible
- Limpieza automática de parámetros de tracking (`utm_`, `fbclid`, `gclid`, etc.)
- Exportación JSON, PDF y TXT a `workspace/exports/`
- Soporte de redirecciones, páginas grandes truncadas y sesiones persistentes

---

### B. Filtrado — FILTRAR 200

```bash
# Filtra URLs con status 200 desde la sesión guardada
python3 filtrar_200.py

# Opcional: usar un archivo JSON específico
python3 filtrar_200.py workspace/scans/mi_escaneo.json
```

Genera en `workspace/exports/`:

| Archivo | Contenido |
|---|---|
| `urls_200_limpias.txt` | Todas las URLs con status 200 |
| `urls_200_internas.txt` | Solo URLs internas |
| `urls_200_externas.txt` | Solo URLs externas |
| `resumen_final.txt` | Estadísticas de la sesión |

> ⚠️ `auto_attack.py` necesita este paso previo para obtener las listas limpias.

---

### C. Ataque — AUTO ATTACK v2.0 ELITE

Motor de inyección profesional con soporte para **6 categorías de vulnerabilidades**, detección de WAF, time-based SQLi, codificación de payloads, inyección en cabeceras y reportes HTML interactivos.

```bash
# Modo básico: detecta automáticamente todos los parámetros
python3 auto_attack.py

# Usar un archivo de URLs específico
python3 auto_attack.py --file workspace/exports/urls_200_limpias.txt

# Atacar solo parámetros específicos
python3 auto_attack.py --params id,q,search

# Usar múltiples métodos HTTP
python3 auto_attack.py --methods GET,POST

# Codificar payloads (url, double, base64, html)
python3 auto_attack.py --encode url,double

# Inyectar también en cabeceras HTTP
python3 auto_attack.py --headers

# Detectar WAF antes de atacar
python3 auto_attack.py --waf-detect

# Modo sigiloso (delays aleatorios 0.3–1.2s)
python3 auto_attack.py --stealth

# Modo agresivo (sin delays, máxima velocidad)
python3 auto_attack.py --aggressive

# Control de hilos y timeout
python3 auto_attack.py --workers 16 --timeout 12

# Prueba rápida (solo 3 payloads por categoría)
python3 auto_attack.py --quick

# Seleccionar categorías específicas
python3 auto_attack.py --categories sqli,xss

# Reportar solo HIGH o CRITICAL
python3 auto_attack.py --severity high

# Sin reporte HTML (solo TXT y JSON)
python3 auto_attack.py --no-html

# Desactivar deduplicación de URLs
python3 auto_attack.py --no-dedup

# Combinación típica para escaneo completo pero rápido
python3 auto_attack.py --file workspace/exports/urls_200_limpias.txt --quick --workers 4
```

**Flags disponibles:**

| Flag | Descripción |
|---|---|
| `--file` | Archivo con URLs objetivo (default: `workspace/exports/urls_200_limpias.txt`) |
| `--params` | Parámetros fijos separados por coma (ej: `id,q,search`) |
| `--methods` | Métodos HTTP (GET, POST) — default: `GET` |
| `--encode` | Codificaciones a aplicar a los payloads (`url`, `double`, `base64`, `html`) |
| `--headers` | Inyectar payloads también en cabeceras HTTP (`X-Forwarded-For`, `Referer`, etc.) |
| `--waf-detect` | Detectar WAF antes de iniciar las pruebas |
| `--stealth` | Modo sigiloso con delays aleatorios (0.3–1.2s) entre requests |
| `--aggressive` | Modo agresivo sin delays — máxima velocidad |
| `--workers` | Número de hilos paralelos (default: `4`) |
| `--timeout` | Timeout por request en segundos (default: `10`) |
| `--quick` | Solo 3 payloads por categoría (prueba rápida) |
| `--categories` | Categorías a probar: `sqli`, `xss`, `lfi`, `ssti`, `redirect`, `xxe` — default: todas |
| `--severity` | Nivel mínimo de severidad a reportar (`critical`, `high`, `medium`, `info`, `all`) — default: `all` |
| `--no-html` | No generar reporte HTML (solo TXT y JSON) |
| `--no-dedup` | No deduplicar URLs (puede aumentar el número de pruebas) |

**Salida generada:**

| Archivo | Descripción |
|---|---|
| `attack_v2_YYYYMMDD_HHMMSS.txt` | Informe detallado en texto plano |
| `attack_v2_YYYYMMDD_HHMMSS.json` | Datos completos en JSON |
| `attack_v2_YYYYMMDD_HHMMSS.html` | Reporte interactivo con filtros (si no se usó `--no-html`) |

---

### D. Informe — REPORT MANAGER v1.0

```bash
# Archivar resultados antiguos (mantiene solo los últimos 5 en exports/)
python3 report_manager.py --archive

# Generar PDF con gráfica de barras de vulnerabilidades
python3 report_manager.py --pdf

# Mostrar resumen táctico en terminal
python3 report_manager.py --summary

# Ejecutar las tres acciones en secuencia
python3 report_manager.py --all

# Usar un archivo JSON específico para PDF o resumen
python3 report_manager.py --pdf --file workspace/exports/attack_v2_20260325_123456.json
```

**Funcionalidades:**
- Auto-archivo: comprime los resultados más antiguos en `.tar.gz` dentro de `workspace/archives/`
- PDF profesional con gráfica de distribución de vulnerabilidades (requiere `matplotlib`)
- Resumen por categoría, parámetros más afectados y top payloads

---

## API REST Interna (modo web)

El servidor HTTP interno expone los siguientes endpoints:

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/health` | Estado del servidor y versión |
| `GET` | `/api/stream` | Poll de logs, URLs y contadores en tiempo real |
| `GET` | `/api/session` | Resumen de la sesión guardada en disco |
| `GET` | `/api/session/clear` | Eliminar sesión guardada |
| `GET` | `/api/grafo` | Datos del grafo jerárquico en JSON |
| `POST` | `/api/scan` | Iniciar nuevo escaneo |
| `POST` | `/api/resume` | Reanudar sesión guardada |
| `POST` | `/api/exportar-grafo` | Exportar grafo completo a JSON |

---

## Estructura del Repositorio

```
link-analyzer/
├── link_analyzer_v5.2.py      # Motor principal de crawling
├── analizador_pro.py          # Motor de análisis avanzado (patrones, seguridad, mapeo)
├── filtrar_200.py             # Filtrador de URLs status 200
├── auto_attack.py             # Módulo de ataque (SQLi, XSS, LFI, SSTI, XXE, Open Redirect)
├── report_manager.py          # Módulo de informes y archivo
├── linkanalyzer_session.json  # Sesión persistente (auto-generado)
├── LICENSE
├── README.md
├── eje_central_web.jpg        # Evidencia — interfaz web
├── evidencia_potencia_cli.jpg # Evidencia — modo CLI
└── workspace/
    ├── scans/                 # Resultados de sesiones (mapas jerárquicos)
    ├── exports/               # JSON, PDF, TXT, listas 200, reportes de ataque
    │   ├── urls_200_limpias.txt
    │   ├── urls_200_internas.txt
    │   ├── urls_200_externas.txt
    │   ├── attack_v2_*.json
    │   ├── attack_v2_*.txt
    │   ├── attack_v2_*.html
    │   └── resumen_final.txt
    └── archives/              # .tar.gz de exports anteriores
```

---

## Filosofía de Uso

Esta herramienta fue creada para auditorías autorizadas, investigación de seguridad ofensiva y estudio técnico de infraestructuras web.

> Úsala exclusivamente en entornos donde tengas permiso explícito.  
> El autor no se responsabiliza por usos fuera de ese marco.

---

## Licencia

MIT License — libre para uso personal y comercial con atribución.

---

## Autor

**Yoandis Rodríguez**  
Ingeniería de Ciberseguridad Táctica  
GitHub: [github.com/YoandisR](https://github.com/YoandisR)  
Contacto: curvadigital0@gmail.com
