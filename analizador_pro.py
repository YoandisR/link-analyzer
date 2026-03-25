#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║   🧠 ANALIZADOR PRO v2.0 — Módulo de Inteligencia Post-Escaneo  ║
║   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║   Complemento para LINK ANALYZER PRO v5.2                        ║
║   CREADO POR : Yoandis Rodríguez                                 ║
║   GITHUB     : https://github.com/YoandisR                       ║
╚══════════════════════════════════════════════════════════════════╝

STREET COMPLETO — Las 3 Capas de Inteligencia:
  [1] Detección de Patrones Sensibles  (parámetros, rutas de interés)
  [2] Verificación de Seguridad        (extensiones críticas, archivos expuestos)
  [3] Mapeo Visual de Dominios         (top dominios externos, red de comunicación)
  [4] Reporte Completo                 (ejecuta las 3 y genera informe unificado)

Uso:
  python3 analizador_pro.py             → Menú interactivo
  python3 analizador_pro.py --all       → Ejecuta las 3 capas directo
  python3 analizador_pro.py --file PATH → Usa archivo de URLs específico
"""

import os
import sys
import time
import json
from collections import Counter, defaultdict
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# ── Colores ────────────────────────────────────────────────────────────────────
class C:
    CYAN    = '\033[96m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[33m'
    MAGENTA = '\033[35m'
    RED     = '\033[91m'
    WHITE   = '\033[97m'
    GRAY    = '\033[90m'
    BLUE    = '\033[94m'
    ORANGE  = '\033[38;5;208m'
    BOLD    = '\033[1m'
    END     = '\033[0m'

def banner():
    print(f"""
{C.MAGENTA}╔══════════════════════════════════════════════════════════════════╗
║  {C.CYAN}{C.BOLD}🧠 ANALIZADOR PRO v2.0{C.END}{C.MAGENTA} — Módulo de Inteligencia               ║
║  {C.GRAY}Street Completo · 3 Capas · by Yoandis Rodríguez{C.MAGENTA}               ║
╠══════════════════════════════════════════════════════════════════╣
║  {C.GREEN}[1]{C.MAGENTA} Detección de Patrones Sensibles                            ║
║  {C.YELLOW}[2]{C.MAGENTA} Verificación de Seguridad (archivos expuestos)             ║
║  {C.BLUE}[3]{C.MAGENTA} Mapeo Visual de Dominios (red de comunicación)             ║
║  {C.CYAN}[4]{C.MAGENTA} Reporte Completo (ejecuta las 3 capas)                     ║
║  {C.GRAY}[0]{C.MAGENTA} Salir                                                      ║
╚══════════════════════════════════════════════════════════════════╝{C.END}
""")

# ══════════════════════════════════════════════════════════════════════════════
# LOCALIZACIÓN DE ARCHIVOS
# ══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR = os.path.join(SCRIPT_DIR, 'workspace', 'exports')
SCANS_DIR   = os.path.join(SCRIPT_DIR, 'workspace', 'scans')

DEFAULT_INPUTS = [
    os.path.join(EXPORTS_DIR, 'urls_200_limpias.txt'),
    os.path.join(EXPORTS_DIR, 'urls_200_internas.txt'),
]

def encontrar_archivo_urls(arg=None):
    """Localiza el archivo de URLs a analizar."""
    if arg and os.path.isfile(arg):
        return arg

    # Prioridad: limpias > internas > cualquier .txt en exports
    for f in DEFAULT_INPUTS:
        if os.path.isfile(f):
            return f

    # Busca cualquier .txt en exports
    if os.path.isdir(EXPORTS_DIR):
        txts = [os.path.join(EXPORTS_DIR, f)
                for f in os.listdir(EXPORTS_DIR) if f.endswith('.txt')]
        if txts:
            return sorted(txts)[-1]

    return None

def cargar_urls(filepath):
    """Carga lista de URLs desde .txt o .json."""
    urls = []
    if filepath.endswith('.json'):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Acepta formato sesión o export
        links = data.get('links', []) or \
                data.get('internos', []) + data.get('externos', [])
        for e in links:
            u = e.get('url', '').strip()
            s = e.get('status')
            if u and str(s) == '200':
                urls.append(u)
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            urls = [l.strip() for l in f if l.strip()]
    return urls

def separador(titulo, color=C.CYAN):
    ancho = 66
    linea = '─' * (ancho - len(titulo) - 3)
    print(f"\n{color}┌─ {C.BOLD}{titulo}{C.END}{color} {linea}┐{C.END}\n")

def guardar_reporte(nombre, contenido):
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    ruta = os.path.join(EXPORTS_DIR, nombre)
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(contenido)
    return ruta

# ==============================================================================
# FUNCIÓN DE BARRA DINÁMICA (SEMÁFORO)
# ==============================================================================
def obtener_barra_dinamica(valor, max_valor, ancho=35):
    """
    Devuelve una barra de caracteres con color según el porcentaje que representa valor/max_valor.
    Verde < 25%, Amarillo 25-60%, Rojo > 60%.
    """
    if max_valor == 0:
        return f"{C.GRAY}{'░' * ancho}{C.END}"
    fill = int(valor / max_valor * ancho)
    barra = '█' * fill + '░' * (ancho - fill)
    pct = (valor / max_valor) * 100
    if pct > 60:
        color = C.RED
    elif pct > 25:
        color = C.YELLOW
    else:
        color = C.GREEN
    return f"{color}{barra}{C.END}"

# ══════════════════════════════════════════════════════════════════════════════
# CAPA 1: DETECCIÓN DE PATRONES SENSIBLES
# ══════════════════════════════════════════════════════════════════════════════

# Patrones organizados por categoría de riesgo
PATRONES = {
    'CRÍTICO': {
        'keywords': ['admin', 'administrator', 'panel', 'dashboard', 'cpanel',
                     'wp-admin', 'phpmyadmin', 'webadmin', 'manager', 'console'],
        'color': C.RED,
        'desc': 'Paneles de administración'
    },
    'AUTH': {
        'keywords': ['login', 'signin', 'signup', 'auth', 'oauth', 'token',
                     'password', 'passwd', 'credential', 'session', 'jwt'],
        'color': C.ORANGE,
        'desc': 'Autenticación y credenciales'
    },
    'API': {
        'keywords': ['api/', '/api', 'api.', 'graphql', 'rest/', 'v1/', 'v2/',
                     'endpoint', 'webhook', 'callback', 'rpc'],
        'color': C.YELLOW,
        'desc': 'Endpoints de API'
    },
    'PARAMS': {
        'keywords': ['?id=', '?uid=', '?user=', '?file=', '?path=', '?url=',
                     '?redirect=', '?return=', '?next=', '?src=', '?include=',
                     '?page=', '?q=', '?search=', '?query=', '?cmd='],
        'color': C.YELLOW,
        'desc': 'Parámetros potencialmente inyectables'
    },
    'CONFIG': {
        'keywords': ['config', 'setup', 'install', 'debug', 'test', 'dev',
                     'staging', 'backup', 'old', 'tmp', 'temp'],
        'color': C.CYAN,
        'desc': 'Rutas de configuración/desarrollo'
    },
    'UPLOAD': {
        'keywords': ['upload', 'uploads/', 'files/', 'media/', 'attach',
                     'import', 'export', 'download', 'static/'],
        'color': C.BLUE,
        'desc': 'Carga y descarga de archivos'
    },
}

def capa1_patrones(urls, silencioso=False):
    separador('CAPA 1 · DETECCIÓN DE PATRONES SENSIBLES', C.GREEN)
    t0 = time.time()

    resultados = defaultdict(list)
    parametros_encontrados = Counter()

    for url in urls:
        url_lower = url.lower()
        for cat, data in PATRONES.items():
            for kw in data['keywords']:
                if kw in url_lower:
                    resultados[cat].append(url)
                    break

        # Extraer parámetros de query string
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            for p in params:
                parametros_encontrados[p] += 1
        except Exception:
            pass

    total_alertas = sum(len(v) for v in resultados.values())

    if not silencioso:
        for cat, data in PATRONES.items():
            urls_cat = resultados.get(cat, [])
            if not urls_cat:
                continue
            print(f"  {data['color']}{C.BOLD}[{cat}]{C.END} {C.GRAY}{data['desc']}{C.END} "
                  f"→ {data['color']}{C.BOLD}{len(urls_cat)}{C.END} URLs")
            for u in urls_cat[:5]:
                # Color de URL según categoría
                if cat in ('CRÍTICO', 'AUTH'):
                    color_url = C.ORANGE
                elif cat in ('PARAMS', 'API'):
                    color_url = C.YELLOW
                else:
                    color_url = C.WHITE
                print(f"    {C.GRAY}├─{C.END} {color_url}{u}{C.END}")
            if len(urls_cat) > 5:
                print(f"    {C.GRAY}└─ ... y {len(urls_cat)-5} más{C.END}")
            print()

        if parametros_encontrados:
            print(f"  {C.YELLOW}{C.BOLD}TOP PARÁMETROS QUERY STRING:{C.END}")
            max_param = parametros_encontrados.most_common(1)[0][1] if parametros_encontrados else 1
            for p, n in parametros_encontrados.most_common(15):
                barra = obtener_barra_dinamica(n, max_param, ancho=30)
                print(f"    {C.GRAY}?{p}={C.END} {barra} {C.YELLOW}({n}){C.END}")
            print()

        elapsed = time.time() - t0
        print(f"  {C.GREEN}✓{C.END} {total_alertas} alertas detectadas en {elapsed:.2f}s")

    return resultados, parametros_encontrados

# ══════════════════════════════════════════════════════════════════════════════
# CAPA 2: VERIFICACIÓN DE SEGURIDAD
# ══════════════════════════════════════════════════════════════════════════════

EXTENSIONES_RIESGO = {
    'CRÍTICO': {
        'ext': ['.env', '.bak', '.sql', '.db', '.sqlite', '.dump'],
        'color': C.RED,
        'desc': 'Archivos de base de datos / configuración sensible'
    },
    'ALTO': {
        'ext': ['.log', '.cfg', '.conf', '.ini', '.htaccess', '.htpasswd'],
        'color': C.ORANGE,
        'desc': 'Archivos de configuración del servidor'
    },
    'MEDIO': {
        'ext': ['.xml', '.yaml', '.yml', '.toml', '.properties'],
        'color': C.YELLOW,
        'desc': 'Archivos de configuración de aplicación'
    },
    'INFO': {
        'ext': ['.json', '.csv', '.xlsx', '.xls', '.pdf', '.doc', '.docx'],
        'color': C.CYAN,
        'desc': 'Archivos de datos / documentos'
    },
    'CÓDIGO': {
        'ext': ['.php', '.asp', '.aspx', '.jsp', '.py', '.rb', '.sh', '.bash'],
        'color': C.BLUE,
        'desc': 'Archivos de código expuestos'
    },
}

RUTAS_EXPUESTAS = [
    '/.git/', '/.svn/', '/.env', '/.htaccess', '/wp-config.php',
    '/config.php', '/database.php', '/settings.py', '/web.config',
    '/Dockerfile', '/docker-compose.yml', '/package.json', '/composer.json',
    '/phpinfo.php', '/info.php', '/test.php', '/readme.md', '/CHANGELOG',
]

def capa2_seguridad(urls, silencioso=False):
    separador('CAPA 2 · VERIFICACIÓN DE SEGURIDAD', C.YELLOW)
    t0 = time.time()

    expuestos = defaultdict(list)
    rutas_criticas = []

    for url in urls:
        url_lower = url.lower()
        # Verificar extensiones
        for nivel, data in EXTENSIONES_RIESGO.items():
            for ext in data['ext']:
                if url_lower.split('?')[0].endswith(ext):
                    expuestos[nivel].append(url)
                    break
        # Verificar rutas conocidas como sensibles
        for ruta in RUTAS_EXPUESTAS:
            if ruta in url_lower:
                rutas_criticas.append(url)
                break

    total = sum(len(v) for v in expuestos.values()) + len(rutas_criticas)

    if not silencioso:
        if not total:
            print(f"  {C.GREEN}✓{C.END} {C.GRAY}Sin extensiones ni rutas críticas detectadas.{C.END}\n")
        else:
            for nivel, data in EXTENSIONES_RIESGO.items():
                lista = expuestos.get(nivel, [])
                if not lista:
                    continue
                print(f"  {data['color']}{C.BOLD}[{nivel}]{C.END} {C.GRAY}{data['desc']}{C.END} "
                      f"→ {data['color']}{C.BOLD}{len(lista)}{C.END} archivos")
                for u in lista[:5]:
                    print(f"    {C.GRAY}├─{C.END} {data['color']}{u}{C.END}")
                if len(lista) > 5:
                    print(f"    {C.GRAY}└─ ... y {len(lista)-5} más{C.END}")
                print()

            if rutas_criticas:
                print(f"  {C.RED}{C.BOLD}[RUTAS EXPUESTAS CONOCIDAS]{C.END}")
                for u in rutas_criticas:
                    print(f"    {C.RED}⚠{C.END} {C.BOLD}{u}{C.END}")
                print()

        elapsed = time.time() - t0
        estado = C.RED if total > 0 else C.GREEN
        print(f"  {estado}{'⚠' if total else '✓'}{C.END} {total} archivos/rutas sensibles en {elapsed:.2f}s")

    return expuestos, rutas_criticas

# ══════════════════════════════════════════════════════════════════════════════
# CAPA 3: MAPEO VISUAL DE DOMINIOS
# ══════════════════════════════════════════════════════════════════════════════

def capa3_mapeo(urls, silencioso=False):
    separador('CAPA 3 · MAPEO VISUAL DE DOMINIOS', C.BLUE)
    t0 = time.time()

    dominios    = Counter()
    subdominios = Counter()
    esquemas    = Counter()
    tlds        = Counter()
    profundidad = Counter()  # niveles de path
    rutas_raiz  = Counter()  # primer segmento del path

    for url in urls:
        try:
            p = urlparse(url)
            if not p.netloc:
                continue

            dominios[p.netloc] += 1
            esquemas[p.scheme] += 1

            # TLD
            partes = p.netloc.split('.')
            if len(partes) >= 2:
                tlds['.'.join(partes[-2:])] += 1

            # Subdominios
            if len(partes) > 2:
                subdominios[p.netloc] += 1

            # Profundidad del path
            depth = len([s for s in p.path.split('/') if s])
            profundidad[depth] += 1

            # Primera carpeta raíz
            partes_path = [s for s in p.path.split('/') if s]
            if partes_path:
                rutas_raiz[partes_path[0]] += 1

        except Exception:
            continue

    total_urls     = len(urls)
    total_dominios = len(dominios)

    if not silencioso:
        # Top dominios con barra dinámica
        print(f"  {C.BLUE}{C.BOLD}TOP DOMINIOS:{C.END} {C.GRAY}({total_dominios} únicos){C.END}\n")
        max_count = dominios.most_common(1)[0][1] if dominios else 1
        for dom, cnt in dominios.most_common(15):
            pct = cnt / total_urls * 100
            barra = obtener_barra_dinamica(cnt, max_count, ancho=35)
            print(f"    {C.WHITE}{dom:<35}{C.END} {barra} {C.YELLOW}{cnt:>5}{C.END} {C.GRAY}({pct:.1f}%){C.END}")
        print()

        # Profundidad con barra dinámica
        print(f"  {C.BLUE}{C.BOLD}PROFUNDIDAD DE RUTAS:{C.END}\n")
        if profundidad:
            max_depth_val = max(profundidad.values())
            for depth in sorted(profundidad.keys())[:8]:
                cnt = profundidad[depth]
                pct = cnt / total_urls * 100
                barra = obtener_barra_dinamica(cnt, max_depth_val, ancho=30)
                print(f"    {C.GRAY}Nivel {depth}:{C.END} {barra} {C.GRAY}{cnt} ({pct:.1f}%){C.END}")
        else:
            print(f"    {C.GRAY}No hay rutas con profundidad > 0.{C.END}")
        print()

        # Top rutas raíz
        if rutas_raiz:
            print(f"  {C.BLUE}{C.BOLD}DIRECTORIOS RAÍZ MÁS FRECUENTES:{C.END}\n")
            for ruta, cnt in rutas_raiz.most_common(10):
                print(f"    {C.GRAY}/{ruta:<25}{C.END} → {C.YELLOW}{cnt}{C.END}")
            print()

        # Subdominios detectados
        if subdominios:
            print(f"  {C.BLUE}{C.BOLD}SUBDOMINIOS DETECTADOS:{C.END} {C.GRAY}({len(subdominios)}){C.END}\n")
            for sub, cnt in subdominios.most_common(10):
                print(f"    {C.GRAY}├─{C.END} {sub} {C.YELLOW}({cnt}){C.END}")
            print()

        elapsed = time.time() - t0
        print(f"  {C.GREEN}✓{C.END} {total_dominios} dominios únicos mapeados en {elapsed:.2f}s")

    return dominios, subdominios, profundidad, rutas_raiz

# ══════════════════════════════════════════════════════════════════════════════
# CAPA 4: REPORTE COMPLETO UNIFICADO (CON ETIQUETAS DE SEVERIDAD)
# ══════════════════════════════════════════════════════════════════════════════

def generar_reporte_txt(urls, r1, r2, r3, filepath_fuente):
    """Genera reporte .txt completo y legible con etiquetas de severidad."""
    patrones, params   = r1
    expuestos, rutas_c = r2
    dominios, subs, prof, rutas_raiz = r3

    total_alertas = sum(len(v) for v in patrones.values())
    total_expuesto = sum(len(v) for v in expuestos.values()) + len(rutas_c)
    total_dominios = len(dominios)

    lineas = []
    def L(s=''): lineas.append(s)

    L("=" * 70)
    L("  REPORTE DE INTELIGENCIA — ANALIZADOR PRO v2.0")
    L("  by Yoandis Rodríguez  |  github.com/YoandisR")
    L("=" * 70)
    L(f"  Fecha     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L(f"  Fuente    : {os.path.basename(filepath_fuente)}")
    L(f"  Total URLs: {len(urls):,}")
    L()

    L("─" * 70)
    L("  RESUMEN EJECUTIVO")
    L("─" * 70)
    L(f"  Alertas de patrones  : {total_alertas:,}")
    L(f"  Archivos expuestos   : {total_expuesto:,}")
    L(f"  Dominios únicos      : {total_dominios:,}")
    L(f"  Subdominios          : {len(subs):,}")
    L()

    # Capa 1 con etiquetas
    L("─" * 70)
    L("  CAPA 1 · PATRONES SENSIBLES")
    L("─" * 70)
    for cat, data in PATRONES.items():
        lista = patrones.get(cat, [])
        if lista:
            if cat == 'CRÍTICO':
                prefijo = "[!!!] CRÍTICO"
            elif cat == 'AUTH':
                prefijo = "[!!] ALTO"
            else:
                prefijo = "[!]"
            L(f"\n  {prefijo} — {data['desc']} ({len(lista)} URLs)")
            for u in lista:
                L(f"    {u}")
    if params:
        L("\n  TOP PARÁMETROS QUERY STRING:")
        for p, n in params.most_common(20):
            L(f"    ?{p}= ({n} ocurrencias)")
    L()

    # Capa 2 con etiquetas
    L("─" * 70)
    L("  CAPA 2 · ARCHIVOS / RUTAS SENSIBLES")
    L("─" * 70)
    if not total_expuesto:
        L("  Sin archivos o rutas sensibles detectados.")
    else:
        for nivel, data in EXTENSIONES_RIESGO.items():
            lista = expuestos.get(nivel, [])
            if lista:
                if nivel == 'CRÍTICO':
                    prefijo = "[!!!]"
                elif nivel == 'ALTO':
                    prefijo = "[!!]"
                elif nivel == 'MEDIO':
                    prefijo = "[!]"
                else:
                    prefijo = "[i]"
                L(f"\n  {prefijo} {nivel} — {data['desc']}")
                for u in lista:
                    L(f"    {u}")
        if rutas_c:
            L("\n  [!!!] RUTAS EXPUESTAS CONOCIDAS")
            for u in rutas_c:
                L(f"    ⚠ {u}")
    L()

    # Capa 3 (sin etiquetas, solo datos)
    L("─" * 70)
    L("  CAPA 3 · MAPEO DE DOMINIOS")
    L("─" * 70)
    L("\n  TOP DOMINIOS:")
    for dom, cnt in dominios.most_common(20):
        pct = cnt / len(urls) * 100
        L(f"    {dom:<40} {cnt:>5} ({pct:.1f}%)")
    L("\n  DIRECTORIOS RAÍZ:")
    for ruta, cnt in rutas_raiz.most_common(15):
        L(f"    /{ruta:<30} {cnt}")
    L()

    L("=" * 70)
    L("  FIN DEL REPORTE")
    L("=" * 70)

    contenido = '\n'.join(lineas)
    ts    = datetime.now().strftime('%Y%m%d_%H%M%S')
    ruta  = guardar_reporte(f'inteligencia_{ts}.txt', contenido)
    return ruta

def capa4_completo(urls, filepath):
    separador('REPORTE COMPLETO — LAS 3 CAPAS', C.MAGENTA)
    print(f"  {C.GRAY}Analizando {len(urls):,} URLs...{C.END}\n")

    r1 = capa1_patrones(urls, silencioso=False)
    r2 = capa2_seguridad(urls, silencioso=False)
    r3 = capa3_mapeo(urls, silencioso=False)

    print(f"\n{C.MAGENTA}{'═'*66}{C.END}")
    print(f"  {C.CYAN}{C.BOLD}Generando reporte unificado...{C.END}")

    ruta = generar_reporte_txt(urls, r1, r2, r3, filepath)

    print(f"  {C.GREEN}✓{C.END} Reporte guardado en:\n    {C.WHITE}{ruta}{C.END}")
    print(f"\n{C.MAGENTA}{'═'*66}{C.END}")
    print(f"  {C.CYAN}{C.BOLD}Misión de inteligencia completada.{C.END}")
    print(f"  {C.GRAY}El tanque tiene su mapa de guerra.{C.END}")
    print(f"{C.MAGENTA}{'═'*66}{C.END}\n")

# ══════════════════════════════════════════════════════════════════════════════
# MENÚ PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def menu(urls, filepath):
    while True:
        banner()
        print(f"  {C.GRAY}Archivo : {os.path.basename(filepath)}{C.END}")
        print(f"  {C.GRAY}URLs    : {len(urls):,}{C.END}\n")

        opcion = input(f"  {C.WHITE}Elige una opción [0-4]: {C.END}").strip()

        if opcion == '0':
            print(f"\n  {C.CYAN}Tanque en el garaje. Hasta la próxima misión.{C.END}\n")
            break
        elif opcion == '1':
            capa1_patrones(urls)
            input(f"\n  {C.GRAY}[Enter para continuar]{C.END}")
        elif opcion == '2':
            capa2_seguridad(urls)
            input(f"\n  {C.GRAY}[Enter para continuar]{C.END}")
        elif opcion == '3':
            capa3_mapeo(urls)
            input(f"\n  {C.GRAY}[Enter para continuar]{C.END}")
        elif opcion == '4':
            capa4_completo(urls, filepath)
            input(f"\n  {C.GRAY}[Enter para continuar]{C.END}")
        else:
            print(f"\n  {C.RED}[!] Opción inválida.{C.END}")
            time.sleep(0.8)

# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    args   = sys.argv[1:]
    modo_all = '--all' in args

    # Detectar archivo de entrada
    filepath_arg = None
    for i, a in enumerate(args):
        if a == '--file' and i + 1 < len(args):
            filepath_arg = args[i + 1]
            break
        if a.endswith('.txt') or a.endswith('.json'):
            filepath_arg = a
            break

    filepath = encontrar_archivo_urls(filepath_arg)

    if not filepath:
        print(f"{C.RED}[!] No se encontró archivo de URLs.{C.END}")
        print(f"{C.GRAY}    Ejecuta primero: python3 filtrar_200.py{C.END}")
        print(f"{C.GRAY}    O usa: python3 analizador_pro.py --file mi_archivo.txt{C.END}")
        sys.exit(1)

    print(f"\n{C.GRAY}  Cargando URLs desde: {filepath}{C.END}")
    urls = cargar_urls(filepath)

    if not urls:
        print(f"{C.RED}[!] El archivo está vacío o no contiene URLs válidas.{C.END}")
        sys.exit(1)

    print(f"{C.GREEN}  ✓{C.END} {len(urls):,} URLs cargadas\n")
    time.sleep(0.5)

    if modo_all:
        capa4_completo(urls, filepath)
    else:
        menu(urls, filepath)

if __name__ == '__main__':
    main()
