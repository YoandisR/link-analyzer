#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   🧹 FILTRAR 200 — Limpiador de Resultados                   ║
║   Compatible con Link Analyzer PRO v5.2                      ║
║   Autor: Yoandis Rodríguez                                   ║
╚══════════════════════════════════════════════════════════════╝

Lee los resultados del escaneo desde:
  • linkanalyzer_session.json  (sesión guardada)
  • workspace/scans/*.json     (exportaciones guardadas)

Genera:
  • urls_200_limpias.txt       → Solo URLs con status 200, sin duplicados
  • urls_200_internas.txt      → URLs 200 internas únicamente
  • urls_200_externas.txt      → URLs 200 externas únicamente
  • resumen_final.txt          → Estadísticas del escaneo

Uso:
  python3 filtrar_200.py                    → Usa linkanalyzer_session.json
  python3 filtrar_200.py mi_escaneo.json    → Usa archivo específico
"""

import json
import os
import sys
import time
from datetime import datetime

# ── Colores ────────────────────────────────────────────────────────────────────
class C:
    CYAN    = '\033[96m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[33m'
    MAGENTA = '\033[35m'
    RED     = '\033[91m'
    WHITE   = '\033[37m'
    GRAY    = '\033[90m'
    BLUE    = '\033[94m'
    BOLD    = '\033[1m'
    END     = '\033[0m'

def banner():
    print(f"""
{C.MAGENTA}╔══════════════════════════════════════════════════════════════╗
║   {C.CYAN}🧹 FILTRAR 200{C.MAGENTA} — Limpiador de Resultados                   ║
║   {C.GRAY}Link Analyzer PRO v5.2 · by Yoandis Rodríguez{C.MAGENTA}              ║
╚══════════════════════════════════════════════════════════════╝{C.END}
""")

def encontrar_fuente(arg=None):
    """Localiza el archivo JSON de resultados."""
    candidatos = []

    # Argumento explícito
    if arg and os.path.isfile(arg):
        return arg

    # Sesión activa (mismo directorio que este script)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    session    = os.path.join(script_dir, 'linkanalyzer_session.json')
    if os.path.isfile(session):
        candidatos.append(session)

    # workspace/scans/*.json
    scans_dir = os.path.join(script_dir, 'workspace', 'scans')
    if os.path.isdir(scans_dir):
        for f in sorted(os.listdir(scans_dir), reverse=True):
            if f.endswith('.json'):
                candidatos.append(os.path.join(scans_dir, f))

    if not candidatos:
        return None

    # Si hay varios, mostrar menú
    if len(candidatos) == 1:
        return candidatos[0]

    print(f"{C.CYAN}Archivos encontrados:{C.END}")
    for i, c in enumerate(candidatos):
        size_mb = os.path.getsize(c) / (1024 * 1024)
        mtime   = datetime.fromtimestamp(os.path.getmtime(c)).strftime('%Y-%m-%d %H:%M')
        print(f"  {C.YELLOW}[{i}]{C.END} {os.path.basename(c)} {C.GRAY}({size_mb:.1f} MB · {mtime}){C.END}")

    try:
        idx = int(input(f"\n{C.WHITE}Elige número [0]: {C.END}").strip() or "0")
        return candidatos[idx]
    except (ValueError, IndexError):
        return candidatos[0]

def cargar_links(filepath):
    """Carga y normaliza la lista de links desde el JSON."""
    print(f"{C.GRAY}  Cargando: {filepath}{C.END}")
    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"{C.GRAY}  Tamaño  : {size_mb:.1f} MB{C.END}\n")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Formato sesión: data['links']
    # Formato export: data['internos'] + data['externos']
    links = []

    if 'links' in data:
        links = data['links']
    elif 'internos' in data or 'externos' in data:
        links = data.get('internos', []) + data.get('externos', [])
    else:
        print(f"{C.RED}[!] Formato JSON no reconocido.{C.END}")
        sys.exit(1)

    return links, data

def filtrar(links):
    """
    Filtra URLs con status 200, elimina duplicados.
    Retorna dict con listas separadas.
    """
    vistas     = set()
    ok_200     = []
    internas   = []
    externas   = []
    total_err  = 0
    total_otro = 0
    sin_status = 0

    for entry in links:
        url    = entry.get('url', '').strip()
        status = entry.get('status')
        interno = entry.get('interno', False)

        if not url:
            continue

        # Normalizar status
        try:
            status = int(status) if status is not None else None
        except (ValueError, TypeError):
            status = None

        if status is None or status == 0:
            sin_status += 1
            continue
        elif status >= 400:
            total_err += 1
            continue
        elif status != 200:
            total_otro += 1  # 3xx, 201, etc.
            continue

        # Es 200 — deduplicar
        url_norm = url.rstrip('/')
        if url_norm in vistas:
            continue
        vistas.add(url_norm)

        ok_200.append(url)
        if interno:
            internas.append(url)
        else:
            externas.append(url)

    return {
        'todas'     : ok_200,
        'internas'  : internas,
        'externas'  : externas,
        'total_err' : total_err,
        'total_otro': total_otro,
        'sin_status': sin_status,
    }

def guardar(nombre, lista, modo='urls'):
    """Guarda lista en archivo de texto."""
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workspace', 'exports')
    os.makedirs(out_dir, exist_ok=True)
    ruta = os.path.join(out_dir, nombre)

    with open(ruta, 'w', encoding='utf-8') as f:
        for item in lista:
            f.write(item + '\n')

    return ruta

def guardar_resumen(data, links_orig, resultado, filepath_fuente):
    """Genera resumen estadístico."""
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workspace', 'exports')
    os.makedirs(out_dir, exist_ok=True)
    ruta = os.path.join(out_dir, 'resumen_final.txt')

    total_orig   = len(links_orig)
    total_200    = len(resultado['todas'])
    pct_exito    = (total_200 / total_orig * 100) if total_orig > 0 else 0
    pct_error    = (resultado['total_err'] / total_orig * 100) if total_orig > 0 else 0
    pct_otro     = (resultado['total_otro'] / total_orig * 100) if total_orig > 0 else 0

    meta = data.get('meta', {})
    target = data.get('target', meta.get('dominio', 'N/A'))

    lineas = [
        "=" * 60,
        "  REPORTE FINAL — LINK ANALYZER PRO v5.2",
        "  by Yoandis Rodríguez",
        "=" * 60,
        f"  Fecha         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Fuente        : {os.path.basename(filepath_fuente)}",
        f"  Target        : {target}",
        "",
        "  TOTALES",
        f"  ├─ Links escaneados  : {total_orig:,}",
        f"  ├─ Status 200 únicos : {total_200:,}  ({pct_exito:.1f}%)",
        f"  │    ├─ Internos     : {len(resultado['internas']):,}",
        f"  │    └─ Externos     : {len(resultado['externas']):,}",
        f"  ├─ Errores (4xx/5xx) : {resultado['total_err']:,}  ({pct_error:.1f}%)",
        f"  ├─ Redirecciones/2xx : {resultado['total_otro']:,}  ({pct_otro:.1f}%)",
        f"  └─ Sin status/timeout: {resultado['sin_status']:,}",
        "",
        "  ARCHIVOS GENERADOS (workspace/exports/)",
        "  ├─ urls_200_limpias.txt",
        "  ├─ urls_200_internas.txt",
        "  └─ urls_200_externas.txt",
        "",
        "=" * 60,
    ]

    with open(ruta, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lineas) + '\n')

    return ruta, lineas

def barra(actual, total, ancho=40):
    pct  = actual / total if total > 0 else 0
    fill = int(ancho * pct)
    bar  = '█' * fill + '░' * (ancho - fill)
    return f"{C.CYAN}[{bar}]{C.END} {pct*100:.1f}%"

# ══════════════════════════════════════════════════════════════════════════════
def main():
    banner()

    # ── 1. Localizar fuente ──
    arg      = sys.argv[1] if len(sys.argv) > 1 else None
    filepath = encontrar_fuente(arg)

    if not filepath:
        print(f"{C.RED}[!] No se encontró ningún archivo de resultados.{C.END}")
        print(f"{C.GRAY}    Coloca este script en el mismo directorio que link_analyzer.py{C.END}")
        sys.exit(1)

    # ── 2. Cargar ──
    print(f"{C.CYAN}[1/4]{C.END} Cargando datos...")
    links_orig, data = cargar_links(filepath)
    print(f"      {C.GREEN}✓{C.END} {len(links_orig):,} entradas cargadas\n")

    # ── 3. Filtrar ──
    print(f"{C.CYAN}[2/4]{C.END} Filtrando status 200 y eliminando duplicados...")
    t0       = time.time()
    resultado = filtrar(links_orig)
    elapsed  = time.time() - t0
    print(f"      {C.GREEN}✓{C.END} {len(resultado['todas']):,} URLs únicas con status 200  ({elapsed:.2f}s)\n")

    # ── 4. Guardar ──
    print(f"{C.CYAN}[3/4]{C.END} Guardando archivos...")

    r1 = guardar('urls_200_limpias.txt',   resultado['todas'])
    r2 = guardar('urls_200_internas.txt',  resultado['internas'])
    r3 = guardar('urls_200_externas.txt',  resultado['externas'])

    print(f"      {C.GREEN}✓{C.END} urls_200_limpias.txt   → {len(resultado['todas']):,} URLs")
    print(f"      {C.GREEN}✓{C.END} urls_200_internas.txt  → {len(resultado['internas']):,} URLs")
    print(f"      {C.GREEN}✓{C.END} urls_200_externas.txt  → {len(resultado['externas']):,} URLs\n")

    # ── 5. Resumen ──
    print(f"{C.CYAN}[4/4]{C.END} Generando resumen...\n")
    ruta_res, lineas = guardar_resumen(data, links_orig, resultado, filepath)

    for l in lineas:
        print(f"  {C.GRAY}{l}{C.END}")

    print(f"\n  {C.GREEN}✓ Resumen guardado en workspace/exports/resumen_final.txt{C.END}")
    print(f"\n{C.MAGENTA}{'═'*60}{C.END}")
    print(f"  {C.CYAN}Misión completada.{C.END} {C.GRAY}El tanque tiene su inventario limpio.{C.END}")
    print(f"{C.MAGENTA}{'═'*60}{C.END}\n")

if __name__ == '__main__':
    main()
