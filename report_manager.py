#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║   📊 REPORT MANAGER v1.0 — Gestión de Informes Tácticos         ║
║   Complemento para Link Analyzer PRO v5.2                        ║
║   CREADO POR : Yoandis Rodríguez                                 ║
║   GITHUB     : https://github.com/YoandisR                       ║
╚══════════════════════════════════════════════════════════════════╝

Gestión de resultados de AUTO ATTACK y filtrados:
  • Auto‑archive    : comprime y archiva resultados antiguos
  • PDF profesional : genera gráficas de vulnerabilidades
  • Resumen táctico : muestra en terminal los hallazgos clave

Uso:
  python3 report_manager.py --archive          # archiva resultados antiguos
  python3 report_manager.py --pdf              # genera PDF con gráficas
  python3 report_manager.py --summary          # muestra resumen en terminal
  python3 report_manager.py --all              # ejecuta las tres acciones
  python3 report_manager.py --file <archivo>   # especifica un JSON de resultados
"""

import os
import sys
import json
import tarfile
import shutil
import glob
from datetime import datetime
from collections import Counter, defaultdict

# Colores (misma paleta que Link Analyzer PRO)
class C:
    CYAN    = '\033[96m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    MAGENTA = '\033[35m'
    RED     = '\033[91m'
    WHITE   = '\033[97m'
    GRAY    = '\033[90m'
    BLUE    = '\033[94m'
    ORANGE  = '\033[38;5;208m'
    BOLD    = '\033[1m'
    END     = '\033[0m'

# Directorios
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR = os.path.join(SCRIPT_DIR, 'workspace', 'exports')
ARCHIVES_DIR = os.path.join(SCRIPT_DIR, 'workspace', 'archives')

# Número de archivos a mantener en exports (los más recientes)
KEEP_LATEST = 5

# ------------------------------------------------------------------------------
# Auto‑archive
# ------------------------------------------------------------------------------
def auto_archive():
    """Comprime y archiva los archivos más antiguos de exports/."""
    print(f"\n{C.CYAN}{C.BOLD}[*] Iniciando auto‑archive...{C.END}\n")

    if not os.path.isdir(EXPORTS_DIR):
        print(f"  {C.RED}[!] No existe el directorio exports/{C.END}")
        return

    # Obtener todos los archivos .json y .txt
    files = glob.glob(os.path.join(EXPORTS_DIR, '*.json')) + \
            glob.glob(os.path.join(EXPORTS_DIR, '*.txt'))
    if not files:
        print(f"  {C.YELLOW}[!] No hay archivos en exports/{C.END}")
        return

    # Ordenar por fecha de modificación (más antiguos primero)
    files.sort(key=lambda f: os.path.getmtime(f))

    # Seleccionar los que exceden KEEP_LATEST
    to_archive = files[:-KEEP_LATEST] if len(files) > KEEP_LATEST else []
    if not to_archive:
        print(f"  {C.GREEN}✓{C.END} Solo hay {len(files)} archivos, se mantienen todos.")
        return

    # Crear directorio de archivos si no existe
    os.makedirs(ARCHIVES_DIR, exist_ok=True)

    # Nombre del archivo comprimido con timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_name = f"archive_{timestamp}.tar.gz"
    archive_path = os.path.join(ARCHIVES_DIR, archive_name)

    print(f"  {C.CYAN}Creando archivo: {archive_name}{C.END}")
    with tarfile.open(archive_path, "w:gz") as tar:
        for f in to_archive:
            tar.add(f, arcname=os.path.basename(f))
            os.remove(f)  # eliminar después de empaquetar
            print(f"    {C.GRAY}→ {os.path.basename(f)}{C.END}")

    print(f"\n  {C.GREEN}✓{C.END} Archivo creado: {archive_path}")
    print(f"  {C.GREEN}✓{C.END} Se mantienen los últimos {KEEP_LATEST} archivos en exports/")

# ------------------------------------------------------------------------------
# Generación de PDF profesional
# ------------------------------------------------------------------------------
def generar_pdf(json_file=None):
    """Genera un PDF con gráficas de vulnerabilidades a partir del JSON de resultados."""
    if json_file is None:
        # Buscar el JSON más reciente en exports/
        json_files = glob.glob(os.path.join(EXPORTS_DIR, 'attack_results_*.json'))
        if not json_files:
            print(f"  {C.RED}[!] No se encontraron archivos JSON de resultados.{C.END}")
            return
        json_file = max(json_files, key=os.path.getmtime)

    print(f"\n{C.CYAN}{C.BOLD}[*] Generando PDF a partir de: {os.path.basename(json_file)}{C.END}\n")

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  {C.RED}[!] Error al leer JSON: {e}{C.END}")
        return

    # Contar vulnerabilidades por categoría
    vuln_cat = Counter()
    for entry in data:
        if entry.get('vulnerable'):
            vuln_cat[entry.get('category', 'unknown')] += 1

    if not vuln_cat:
        print(f"  {C.YELLOW}[!] No hay vulnerabilidades en este JSON.{C.END}")
        return

    # Generar gráfica con matplotlib
    try:
        import matplotlib
        matplotlib.use('Agg')  # Sin interfaz gráfica
        import matplotlib.pyplot as plt
    except ImportError:
        print(f"  {C.RED}[!] Matplotlib no instalado. Ejecuta: pip install matplotlib --break-system-packages{C.END}")
        return

    # Preparar datos
    categories = list(vuln_cat.keys())
    counts = list(vuln_cat.values())
    # Mapeo de colores por categoría
    colores = {
        'path_traversal': '#ff5555',  # rojo
        'sql_injection': '#ffaa44',   # naranja/amarillo
        'xss': '#44ff44'              # verde
    }
    bar_colors = [colores.get(c, '#888888') for c in categories]

    plt.figure(figsize=(10, 6))
    bars = plt.bar(categories, counts, color=bar_colors, edgecolor='white', linewidth=1.5)
    plt.title(f'Vulnerabilidades detectadas - {os.path.basename(json_file)}', fontsize=14, pad=20)
    plt.ylabel('Cantidad', fontsize=12)
    plt.xlabel('Categoría', fontsize=12)
    plt.grid(axis='y', linestyle='--', alpha=0.3)

    # Etiquetas de valor encima de las barras
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height,
                 f'{int(height)}', ha='center', va='bottom', fontsize=10)

    # Guardar como PDF
    pdf_filename = json_file.replace('.json', '_report.pdf')
    plt.savefig(pdf_filename, format='pdf', bbox_inches='tight')
    plt.close()

    print(f"  {C.GREEN}✓{C.END} PDF generado: {pdf_filename}")
    return pdf_filename

# ------------------------------------------------------------------------------
# Resumen ejecutivo en terminal
# ------------------------------------------------------------------------------
def resumen_ejecutivo(json_file=None):
    """Muestra en terminal un resumen táctico de los hallazgos."""
    if json_file is None:
        json_files = glob.glob(os.path.join(EXPORTS_DIR, 'attack_results_*.json'))
        if not json_files:
            print(f"  {C.RED}[!] No se encontraron archivos JSON de resultados.{C.END}")
            return
        json_file = max(json_files, key=os.path.getmtime)

    print(f"\n{C.CYAN}{C.BOLD}[*] Resumen ejecutivo: {os.path.basename(json_file)}{C.END}\n")

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  {C.RED}[!] Error al leer JSON: {e}{C.END}")
        return

    total_pruebas = len(data)
    vulnerables = [e for e in data if e.get('vulnerable')]
    total_vuln = len(vulnerables)

    # Contar por categoría
    cat_count = Counter()
    param_count = Counter()
    payload_count = Counter()
    indicator_count = Counter()

    for e in vulnerables:
        cat = e.get('category', 'unknown')
        cat_count[cat] += 1
        param_count[e.get('param')] += 1
        payload_count[e.get('payload')] += 1
        for ind in e.get('indicators', []):
            indicator_count[ind] += 1

    # Mostrar encabezado
    print(f"  {C.MAGENTA}{C.BOLD}════════════════════════════════════════════════════════════{C.END}")
    print(f"  {C.CYAN}Pruebas totales   : {total_pruebas}{C.END}")
    print(f"  {C.CYAN}Vulnerabilidades  : {total_vuln}{C.END}")
    print(f"  {C.MAGENTA}{C.BOLD}────────────────────────────────────────────────────────────{C.END}")

    # Categorías
    if cat_count:
        print(f"\n  {C.YELLOW}{C.BOLD}► Distribución por categoría:{C.END}")
        max_count = max(cat_count.values())
        for cat, cnt in cat_count.most_common():
            pct = cnt / total_vuln * 100
            bar_len = int(cnt / max_count * 30) if max_count else 0
            bar = '█' * bar_len + '░' * (30 - bar_len)
            if cat == 'path_traversal':
                color = C.RED
            elif cat == 'sql_injection':
                color = C.ORANGE
            else:
                color = C.GREEN
            print(f"    {color}{cat:<15}{C.END} {bar} {C.YELLOW}{cnt:>4}{C.END} {C.GRAY}({pct:.1f}%){C.END}")

    # Parámetros más afectados
    if param_count:
        print(f"\n  {C.YELLOW}{C.BOLD}► Parámetros más vulnerables:{C.END}")
        for param, cnt in param_count.most_common(5):
            print(f"    {C.CYAN}?{param}{C.END} {C.GRAY}→ {cnt} veces{C.END}")

    # Top 5 payloads
    if payload_count:
        print(f"\n  {C.YELLOW}{C.BOLD}► Top payloads efectivos:{C.END}")
        for payload, cnt in payload_count.most_common(5):
            # Truncar payload si es muy largo
            short = payload[:40] + '...' if len(payload) > 40 else payload
            print(f"    {C.MAGENTA}{short}{C.END} {C.GRAY}({cnt}){C.END}")

    # Indicadores más frecuentes
    if indicator_count:
        print(f"\n  {C.YELLOW}{C.BOLD}► Indicadores de éxito más comunes:{C.END}")
        for ind, cnt in indicator_count.most_common(5):
            print(f"    {C.GREEN}{ind}{C.END} {C.GRAY}({cnt}){C.END}")

    print(f"\n  {C.MAGENTA}{C.BOLD}════════════════════════════════════════════════════════════{C.END}")
    print(f"  {C.GRAY}Informe detallado guardado en: {json_file}{C.END}")

# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
def main():
    args = sys.argv[1:]

    # Flags
    do_archive = '--archive' in args or '--all' in args
    do_pdf = '--pdf' in args or '--all' in args
    do_summary = '--summary' in args or '--all' in args

    # Archivo específico (para pdf y summary)
    specific_file = None
    for i, arg in enumerate(args):
        if arg == '--file' and i+1 < len(args):
            specific_file = args[i+1]
            break

    # Si no se especifica ninguna acción, mostrar ayuda
    if not (do_archive or do_pdf or do_summary):
        print(__doc__)
        return

    # Auto‑archive primero
    if do_archive:
        auto_archive()

    # PDF
    if do_pdf:
        generar_pdf(specific_file)

    # Resumen
    if do_summary:
        resumen_ejecutivo(specific_file)

if __name__ == '__main__':
    main()
