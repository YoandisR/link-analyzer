# 🔗 Link Analyzer PRO v5.5

**Herramienta profesional de crawling, mapeo jerárquico y auditoría de enlaces web.**  
Desarrollada por **Yoandis Rodríguez** · [GitHub](https://github.com/YoandisR) · curvadigital0@gmail.com

---

## ¿Qué es Link Analyzer PRO?

Link Analyzer PRO es un motor de crawling multihilo escrito en Python, diseñado para mapear de forma exhaustiva la estructura de enlaces de cualquier sitio web. Extrae, clasifica y verifica URLs internas y externas, genera representaciones jerárquicas del sitio y exporta los resultados en múltiples formatos para auditoría y análisis posterior.

Opera en dos modos: una **interfaz web interactiva** con visualización de grafo en tiempo real, y un **modo CLI** con panel de métricas en terminal. Ambos modos comparten el mismo motor de crawling y soporte de memoria persistente.

---

## Características principales

### Motor de crawling
- Crawling recursivo con profundidad configurable por el usuario
- Pool de User-Agents con rotación automática en cada petición
- Normalización y deduplicación de URLs mediante caché interna
- Filtrado inteligente de recursos no relevantes (imágenes, fuentes, scripts, etc.)
- Verificación de estado HTTP con `ThreadPoolExecutor` (hasta 8 hilos concurrentes)
- Clasificación de enlaces en internos y externos por dominio base

### Memoria persistente y reanudación
- Checkpoint automático cada 10 URLs descubiertas (`linkanalyzer_session.json`)
- Botón **REANUDAR** / comando `--resume` para continuar sesiones interrumpidas
- Preserva opciones originales de la sesión (verificar, recursivo, profundidad)
- Resumen de sesión guardada visible al iniciar

### Visualización y exportación
- **Eje Central (Mapa Jerárquico):** grafo de fuerza dirigida integrado en la interfaz web
- Exportación a **JSON** con metadatos completos de la sesión
- Exportación a **PDF** (reporte imprimible generado desde el navegador)
- Exportación a **TXT** para procesamiento externo
- Workspace organizado: `workspace/scans/` y `workspace/exports/`

### Rendimiento
- Probado con más de **61,000 URLs** en una sola sesión sin pérdida de estabilidad
- Velocidad sostenida superior a **23 URLs/segundo** en dispositivos móviles (Termux/Android)
- Panel de métricas en tiempo real: páginas, enlaces, verificados, errores y velocidad

---

## Requisitos

- Python 3.8 o superior
- Librerías:

```bash
pip install requests beautifulsoup4 urllib3 colorama flask
```

> En Termux o sistemas con restricciones de entorno, añade `--break-system-packages`.

---

## Instalación

```bash
git clone https://github.com/YoandisR/link-analyzer-pro.git
cd link-analyzer-pro
pip install requests beautifulsoup4 urllib3 colorama flask
```

---

## Uso

### Interfaz web (modo por defecto)

```bash
python3 link_analyzer_v5.5.py
```

Abre el navegador en `http://localhost:5000`. Desde la interfaz puedes:
- Introducir la URL objetivo y configurar opciones
- Iniciar, pausar o reanudar un escaneo
- Ver el mapa jerárquico (Eje Central) en tiempo real
- Exportar resultados en JSON o PDF

### Modo CLI

```bash
python3 link_analyzer_v5.5.py cli
```

Muestra un panel de métricas en la terminal con actualizaciones en tiempo real: velocidad (U/s), páginas, enlaces y estado HTTP de cada URL procesada.

---

## Estructura del proyecto

```
link-analyzer-pro/
├── link_analyzer_v5.5.py   # Script principal
├── linkanalyzer_session.json  # Checkpoint de sesión (generado en tiempo de ejecución)
└── workspace/
    ├── scans/              # Resultados de escaneos
    └── exports/            # Archivos exportados (JSON, PDF, TXT)
```

---

## Opciones de configuración

| Parámetro    | Descripción                                              | Valor por defecto |
|--------------|----------------------------------------------------------|-------------------|
| `url`        | URL objetivo del crawling                                | —                 |
| `verificar`  | Verificar código de estado HTTP de cada enlace           | `false`           |
| `recursivo`  | Seguir enlaces internos de forma recursiva               | `false`           |
| `profundidad`| Profundidad máxima del crawling recursivo                | `1`               |
| `resume`     | Reanudar desde el último checkpoint guardado             | `false`           |

---

## Arquitectura interna

| Componente        | Responsabilidad                                                  |
|-------------------|------------------------------------------------------------------|
| `PersistentMemory`| Lectura/escritura atómica del checkpoint JSON con bloqueo        |
| `QuantumBus`      | Bus de eventos en memoria compartida entre hilos (logs, contadores, buffer de URLs) |
| `LinkEngine`      | Motor principal: crawling, normalización, filtrado, verificación |
| `WebHandler`      | Servidor HTTP integrado, API REST y HTML de la interfaz          |
| `generar_mapa_jerarquico` | Construcción del árbol de nodos para el grafo de fuerza dirigida |

---

## Capturas de métricas reales

```
Páginas mapeadas  : 4,300+
Rutas detectadas  : 61,300+
Velocidad media   : 23+ U/s  (Termux, Android)
Estado de sesión  : checkpoint automático cada 10 URLs
```

---

## Exportación de datos

**JSON** — Incluye metadatos de sesión, listas de enlaces internos y externos, estado HTTP y nivel de profundidad de cada URL.

**PDF** — Reporte imprimible generado en el navegador con tabla completa de resultados.

**TXT** — Lista plana de URLs para procesamiento externo o integración con otras herramientas.

---

## Licencia

MIT License — libre para uso personal y comercial con atribución.

---

## Autor

**Yoandis Rodríguez**  
GitHub: [github.com/YoandisR](https://github.com/YoandisR)  
Contacto: curvadigital0@gmail.com
