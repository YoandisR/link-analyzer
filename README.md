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

El proyecto se divide en tres capas funcionales independientes pero interconectadas:

| Componente | Archivo | Función |
|---|---|---|
| **Exploración Táctica** | `link_analyzer_v5_2.py` | Crawling, grafos, memoria persistente |
| **Analizador Pro** | `analizador_pro.py` | Motor de análisis avanzado |
| **Filtro de Resultados** | `filtrar_200.py` | Filtra URLs status 200, elimina duplicados, exporta por categoría |
| **Ejecución de Ataque** | `auto_attack.py` | Inyección SQLi, XSS, Path Traversal en tiempo real |
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

**Sesiones de ataque (AUTO ATTACK):**

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
| Top payload | `..\..\windows\system32\drivers\etc\ho...` |

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

Funcionalidades clave:

- Crawling multihilo con `ThreadPoolExecutor` y deduplicación `O(1)` por diccionario
- Grafo de fuerza dirigida (D3.js v7) con zoom, arrastre y agrupación de nodos hoja
- Checkpoint automático cada 500 URLs o 60 segundos — botón **REANUDAR** siempre visible
- Limpieza automática de parámetros de tracking (`utm_`, `fbclid`, `gclid`, etc.)
- Exportación en JSON, PDF y TXT al directorio `workspace/exports/`
- Soporte de redirecciones, páginas grandes truncadas y sesiones persistentes entre reinicios

### B. Filtrado — FILTRAR 200

```bash
# Paso obligatorio antes de auto_attack — genera las listas de URLs objetivo
python3 filtrar_200.py
```

Lee `linkanalyzer_session.json` y produce tres archivos en `workspace/exports/`:

- `urls_200_limpias.txt` → todas las URLs con status 200 (819 en sesión YouTube)
- `urls_200_internas.txt` → solo internas (451)
- `urls_200_externas.txt` → solo externas (368)

> **Nota:** `auto_attack.py --file mis_urls.txt` requiere ejecutar `filtrar_200.py` primero para generar el archivo de URLs.

### C. Ataque — AUTO ATTACK v1.1

```bash
python3 auto_attack.py                        # Escaneo completo
python3 auto_attack.py --quick                # Solo 3 payloads por categoría
python3 auto_attack.py --file mis_urls.txt    # Usar lista personalizada
```

Funcionalidades clave:

- Payloads tácticos para **SQL Injection**, **XSS reflejado** y **Path Traversal (LFI)**
- Detección de firmas de confirmación: `root:`, `sql syntax`, `<script>alert`, etc.
- Biometría en tiempo real por consola con código de color (verde / rojo / amarillo)
- Compatible con la salida JSON de Link Analyzer PRO como entrada directa

### D. Informe — REPORT MANAGER v1.0

```bash
python3 report_manager.py --archive    # Comprimir resultados antiguos en .tar.gz
python3 report_manager.py --pdf        # Generar PDF con gráfica de barras (Matplotlib)
python3 report_manager.py --summary    # Resumen táctico por categoría en terminal
python3 report_manager.py --all        # Ejecutar las tres acciones en secuencia
```

Funcionalidades clave:

- Auto-archivo: mantiene solo los últimos 5 exports activos
- PDF profesional con gráfica de distribución de vulnerabilidades
- Resumen por categoría (SQLi, XSS, Path Traversal), parámetros más afectados y top payloads

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
├── analizador_pro.py          # Motor de análisis avanzado
├── filtrar_200.py             # Filtrador de URLs status 200
├── auto_attack.py             # Módulo de ataque (SQLi, XSS, LFI)
├── report_manager.py          # Módulo de informes y archivo
├── linkanalyzer_session.json  # Sesión persistente (auto-generado)
├── LICENSE
├── README.md
├── eje_central_web.jpg        # Evidencia — interfaz web
├── evidencia_potencia_cli.jpg # Evidencia — modo CLI
└── workspace/
    ├── scans/                 # Resultados de sesiones
    ├── exports/               # JSON, PDF, TXT, listas 200
    │   ├── urls_200_limpias.txt
    │   ├── urls_200_internas.txt
    │   ├── urls_200_externas.txt
    │   ├── attack_results_*.json
    │   ├── attack_results_*.txt
    │   └── resumen_final.txt
    └── archives/              # .tar.gz de exports anteriores
```

---

## Filosofía de Uso

Esta herramienta fue creada para auditorías autorizadas, investigación de seguridad ofensiva y estudio técnico de infraestructuras web.

> **Úsala exclusivamente en entornos donde tengas permiso explícito.**  
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
