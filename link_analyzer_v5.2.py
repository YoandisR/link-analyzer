#!/usr/bin/env python3
"""
╔════════════════════════════════════════════════════════════════╗
║   🔗 LINK ANALYZER PRO v5.2 — MEMORIA PERSISTENTE             ║
║   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║  Motor jerárquico · Visualizador de fuerza dirigida · Termux  ║
║  Memoria Persistente · Botón Reanudar · Android Optimized     ║
║                                                               ║
║  CREADO POR : Yoandis Rodríguez                               ║
║  GITHUB     : https://github.com/YoandisR                     ║
║  CORREO     : curvadigital0@gmail.com                         ║
╚════════════════════════════════════════════════════════════════╝
Uso:
  python3 link_analyzer.py        → Interfaz web con Eje Central
  python3 link_analyzer.py cli    → Modo CLI clásico

NUEVO v5.2:
  - Memoria persistente en JSON (~/linkanalyzer_session.json)
  - Botón REANUDAR siempre visible en la interfaz
  - Reanuda exactamente desde la URL donde se detuvo
  - Guarda checkpoint cada 10 URLs descubiertas
  - Muestra resumen de sesión guardada al cargar
"""
import json
import sys
import os
import shutil
import threading
import subprocess
import time
import urllib3
import concurrent.futures
import hashlib
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, urljoin, parse_qs

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("[!] Ejecuta: pip install requests beautifulsoup4 --break-system-packages")
    sys.exit(1)

# ==============================================================================
# COLORES CLI
# ==============================================================================
class C:
    CYAN    = '\033[96m'   # cyan brillante  — SPEED, VER, codigos 3xx
    GREEN   = '\033[92m'   # verde brillante — codigos 2xx, PAG
    YELLOW  = '\033[33m'   # amarillo        — TIME, codigos 4xx
    MAGENTA = '\033[35m'   # magenta         — marcos de pizarra
    RED     = '\033[91m'   # rojo brillante  — codigos 5xx, ERR
    WHITE   = '\033[37m'   # blanco          — etiquetas de pizarra
    GRAY    = '\033[90m'   # gris oscuro     — texto de URLs (neutro)
    BLUE    = '\033[94m'   # azul brillante  — contador LNK (unico)
    BOLD    = '\033[1m'
    END     = '\033[0m'

# ==============================================================================
# MEMORIA PERSISTENTE
# ==============================================================================
# Workspace centralizado junto al script — portabilidad total
_BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR    = os.path.join(_BASE_DIR, 'workspace')
SCANS_DIR        = os.path.join(WORKSPACE_DIR, 'scans')
EXPORTS_DIR      = os.path.join(WORKSPACE_DIR, 'exports')
SESSION_FILE     = os.path.join(_BASE_DIR, 'linkanalyzer_session.json')
CHECKPOINT_EVERY = 10

# Crear estructura de carpetas al arrancar (silencioso)
for _d in (WORKSPACE_DIR, SCANS_DIR, EXPORTS_DIR):
    os.makedirs(_d, exist_ok=True)

class PersistentMemory:
    def __init__(self, filepath=SESSION_FILE):
        self.filepath = filepath
        self._lock    = threading.Lock()

    def save(self, state: dict):
        with self._lock:
            try:
                state['_saved_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
                state['_version']  = '5.2'
                tmp = self.filepath + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.filepath)
            except Exception:
                pass

    def load(self):
        try:
            if not os.path.exists(self.filepath):
                return None
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            required = ['target', 'vistos', 'cola', 'links', 'options']
            if not all(k in data for k in required):
                return None
            # Sanear status=0 → None (artefacto de versiones anteriores)
            for link in data.get('links', []):
                if link.get('status') == 0:
                    link['status'] = None
                    link['ok']     = None
            return data
        except Exception:
            return None

    def clear(self):
        with self._lock:
            try:
                if os.path.exists(self.filepath):
                    os.remove(self.filepath)
            except Exception:
                pass

    def exists(self):
        return self.load() is not None

    def summary(self):
        data = self.load()
        if not data:
            return None
        return {
            'target':       data.get('target', ''),
            'links_found':  len(data.get('links', [])),
            'urls_visited': len(data.get('vistos', [])),
            'urls_pending': len(data.get('cola', [])),
            'saved_at':     data.get('_saved_at', ''),
            'options':      data.get('options', {}),
            'completed':    data.get('completed', False),
        }


memory = PersistentMemory()


# ==============================================================================
# QUANTUM BUS
# ==============================================================================
class QuantumBus:
    def __init__(self):
        self._lock    = threading.Lock()
        self.logs     = []
        self.url_buf  = []
        self.counters = {'pages': 0, 'links': 0, 'verified': 0, 'errors': 0}
        self.running  = False
        self.result   = None

    def log(self, msg, cat="info"):
        ts = time.strftime("%H:%M:%S")
        with self._lock:
            self.logs.append({"t": ts, "m": msg, "c": cat})
            if len(self.logs) > 120:
                self.logs.pop(0)

    def push_url(self, url, status=None):
        ts = time.strftime("%H:%M:%S")
        with self._lock:
            self.url_buf.append({"t": ts, "u": url, "s": status})
            self.counters['links'] += 1

    def inc(self, key):
        with self._lock:
            self.counters[key] = self.counters.get(key, 0) + 1

    def set_result(self, res):
        with self._lock:
            self.result  = res
            self.running = False

    def poll(self):
        with self._lock:
            urls         = list(self.url_buf)
            self.url_buf = []
            return {
                'running':  self.running,
                'result':   self.result,
                'logs':     list(self.logs),
                'urls':     urls,
                'counters': dict(self.counters),
            }

    def reset(self):
        with self._lock:
            self.logs     = []
            self.url_buf  = []
            self.counters = {'pages': 0, 'links': 0, 'verified': 0, 'errors': 0}
            self.running  = True
            self.result   = None


bus = QuantumBus()


# ==============================================================================
# CLASIFICADOR DE ADN — Generador de Mapa Jerárquico
# ==============================================================================
def generar_mapa_jerarquico(lista_urls, dominio_base):
    nodos  = {}
    enlaces = []
    stats  = {'max_depth': 0, 'total_dirs': 0, 'total_files': 0}
    dominio_netloc = urlparse(dominio_base).netloc if '://' in dominio_base else dominio_base
    root_id = f"{dominio_base}/"
    nodos[root_id] = {
        "id": root_id, "name": "🏠 RAÍZ", "group": 0, "type": "root",
        "size": 25, "url_count": 0, "depth": 0
    }
    for entry in lista_urls:
        url = entry['url'] if isinstance(entry, dict) else entry
        try:
            parsed = urlparse(url)
            if parsed.netloc != dominio_netloc:
                continue
            path   = parsed.path.rstrip('/') or '/'
            partes = [p for p in path.split('/') if p]
            ruta_acumulada = ""
            for nivel, parte in enumerate(partes, start=1):
                parent_path    = ruta_acumulada
                ruta_acumulada = f"{parent_path}/{parte}" if parent_path else f"/{parte}"
                node_id   = f"{dominio_base}{ruta_acumulada}"
                is_file   = '.' in parte and not parte.endswith('/')
                node_type = "file" if is_file else "directory"
                if node_id not in nodos:
                    nodos[node_id] = {
                        "id": node_id, "name": parte,
                        "group": min(nivel, 6), "type": node_type,
                        "size": 8 if is_file else (15 - min(nivel, 7)),
                        "url_count": 0, "depth": nivel
                    }
                    stats['total_dirs']  += 0 if is_file else 1
                    stats['total_files'] += 1 if is_file else 0
                    stats['max_depth']    = max(stats['max_depth'], nivel)
                if nivel == len(partes):
                    nodos[node_id]['url_count'] += 1
                parent_id = f"{dominio_base}{parent_path}" if parent_path else root_id
                if parent_id in nodos and parent_id != node_id:
                    if not any(e['source'] == parent_id and e['target'] == node_id for e in enlaces):
                        enlaces.append({"source": parent_id, "target": node_id, "value": 1, "type": "contains"})
        except Exception:
            continue
    if len(nodos) > 10000:
        enlaces = _agrupar_nodos_hoja(enlaces, nodos, dominio_base)
    return {
        "nodes": list(nodos.values()),
        "links": enlaces,
        "metadata": {
            "dominio": dominio_base, "total_nodos": len(nodos),
            "total_enlaces": len(enlaces), "profundidad_max": stats['max_depth'],
            "generado": time.strftime("%Y-%m-%d %H:%M:%S"), "version": "5.2"
        }
    }


def _agrupar_nodos_hoja(enlaces, nodos, dominio_base):
    hijos_por_padre = defaultdict(list)
    for enlace in enlaces:
        if nodos.get(enlace['target'], {}).get('type') == 'file':
            hijos_por_padre[enlace['source']].append(enlace['target'])
    procesados = set()
    resultado  = []
    for enlace in enlaces:
        target_node = nodos.get(enlace['target'], {})
        padre       = enlace['source']
        if target_node.get('type') == 'file' and padre not in procesados:
            if len(hijos_por_padre[padre]) > 20:
                cid = f"{padre}#CLUSTER"
                if cid not in nodos:
                    nodos[cid] = {
                        "id": cid,
                        "name": f"📦 {len(hijos_por_padre[padre])} archivos",
                        "group": 7, "type": "cluster", "size": 12,
                        "url_count": len(hijos_por_padre[padre]),
                        "depth": nodos.get(padre, {}).get('depth', 0) + 1
                    }
                mod = enlace.copy()
                mod['target'] = cid
                mod['value']  = len(hijos_por_padre[padre])
                mod['type']   = 'cluster'
                resultado.append(mod)
                procesados.add(padre)
                continue
        if padre not in procesados or target_node.get('type') != 'file':
            resultado.append(enlace)
    return resultado


# ==============================================================================
# MOTOR DE ANÁLISIS
# ==============================================================================
class LinkEngine:
    # Pool de User-Agents reales — rotación automática para máxima compatibilidad global
    _UA_POOL = [
        # Chrome Windows
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        # Chrome Android
        'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        # Firefox Linux
        'Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0',
        # Safari macOS
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        # Edge Windows
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        # Googlebot (acceso a contenido público sin bloqueo)
        'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    ]
    _ua_index = 0
    _ua_lock  = threading.Lock()

    def __init__(self):
        """Sesión HTTP persistente — reutiliza conexiones TCP por dominio."""
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0
        )
        self._session.mount('http://',  adapter)
        self._session.mount('https://', adapter)

    @classmethod
    def _next_ua(cls):
        """Rota User-Agent en cada petición."""
        with cls._ua_lock:
            ua = cls._UA_POOL[cls._ua_index % len(cls._UA_POOL)]
            cls._ua_index += 1
            return ua

    @staticmethod
    @__import__('functools').lru_cache(maxsize=50000)
    def _normalize_url_cached(url):
        """Versión cacheada de normalización — evita re-parsear la misma URL."""
        try:
            from urllib.parse import urlparse as _up
            p = _up(url)
            if p.scheme not in ('http', 'https'):
                return None
            host = p.hostname or ''
            if ':' in host and not host.startswith('['):
                host = f'[{host}]'
            else:
                try:
                    host = host.encode('idna').decode('ascii')
                except (UnicodeError, UnicodeDecodeError):
                    pass
            netloc = host
            if p.port and p.port not in (80, 443):
                netloc = f'{host}:{p.port}'
            normalized = p._replace(netloc=netloc, fragment='').geturl()
            return normalized.rstrip('/')
        except Exception:
            return url.split('#')[0].rstrip('/')

    @staticmethod
    def _normalize_url(url):
        return LinkEngine._normalize_url_cached(url)

    @staticmethod
    @__import__('functools').lru_cache(maxsize=20000)
    def _skip_url_cached(url):
        try:
            from urllib.parse import urlparse as _up
            import os as _os
            path = _up(url).path.lower().split('?')[0]
            _, ext = _os.path.splitext(path)
            return ext in LinkEngine.SKIP_EXT
        except Exception:
            return False

    # Extensiones binarias — skip sin petición de red
    SKIP_EXT = {
        '.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx',
        '.zip','.gz','.tar','.rar','.7z','.bz2','.xz',
        '.xml','.p7s','.p7m','.der','.crt','.pem','.cer','.pfx',
        '.txt','.csv','.tsv','.json','.jsonld','.rdf','.owl','.atom','.rss',
        '.mp3','.mp4','.wav','.ogg','.webm','.avi','.mov','.flac','.aac',
        '.jpg','.jpeg','.png','.gif','.svg','.webp','.ico','.bmp','.tiff','.avif',
        '.woff','.woff2','.ttf','.eot','.otf',
        '.exe','.dmg','.apk','.deb','.rpm','.msi','.pkg',
        '.iso','.img','.bin','.vmdk',
        '.py','.js','.css','.sh','.bash','.bat','.rb','.go','.c','.cpp','.h',
        '.java','.class','.jar','.swift','.kt','.rs','.ts',
        '.patch','.diff','.log','.bak','.tmp','.swp',
    }
    MAX_CONTENT_BYTES = 5 * 1024 * 1024   # 5 MB máximo por página

    def _skip_url(self, url):
        """True si la URL apunta a un archivo binario/no-navegable."""
        return LinkEngine._skip_url_cached(url)

    def _fetch(self, url):
        # Normalizar URL (IDN, IPv6, puertos) — con caché LRU
        url = self._normalize_url(url) or url

        # Skip rápido por extensión — sin hacer ninguna petición de red
        if self._skip_url(url):
            bus.log(f"Skip: {url[:60]}", "warn")
            return None, [], url, 0

        # Construir headers con User-Agent rotativo
        headers = {
            'User-Agent':      self._next_ua(),
            'Accept':          'text/html,application/xhtml+xml,*/*;q=0.8',
            'Accept-Language': 'es,en;q=0.9,*;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection':      'keep-alive',
        }
        bus.log(f"Abriendo: {url[:70]}", "process")
        try:
            # Usar sesión persistente para reutilizar conexiones TCP
            r = self._session.get(
                url, headers=headers,
                timeout=8, verify=False,
                stream=True, allow_redirects=True
            )
            r.raise_for_status()

            ct = r.headers.get('Content-Type', '').lower()
            if 'html' not in ct and 'xml' not in ct:
                r.close()
                bus.log(f"No-HTML ({ct[:30]}): {url[:45]}", "warn")
                return None, [], r.url, r.status_code

            content = b''
            for chunk in r.iter_content(chunk_size=32768):
                content += chunk
                if len(content) > self.MAX_CONTENT_BYTES:
                    r.close()
                    bus.log(f"Pagina grande, truncada: {url[:45]}", "warn")
                    break

            encoding = r.encoding or r.apparent_encoding or 'utf-8'
            try:
                text = content.decode(encoding, errors='replace')
            except Exception:
                text = content.decode('utf-8', errors='replace')

            soup = BeautifulSoup(text, 'html.parser')
            base = r.url
            seen = set()
            found = []

            for a in soup.find_all('a', href=True):
                try:
                    raw  = urljoin(base, a['href']).split('#')[0].strip()
                    full = self._normalize_url(raw)
                    if not full:
                        continue
                    if self._skip_url(full):
                        continue
                    p = urlparse(full)
                    if p.scheme not in ('http', 'https') or not p.netloc:
                        continue
                    # Limpiar parámetros de tracking
                    if p.query:
                        from urllib.parse import parse_qs, urlencode as _ue
                        params = parse_qs(p.query, keep_blank_values=True)
                        clean  = {k: v for k, v in params.items()
                                  if not k.lower().startswith(
                                      ('utm_', 'ref_', 'fbclid', 'gclid', 'mc_', '_ga', 'yclid'))}
                        full   = p._replace(query=_ue(clean, doseq=True)).geturl()
                        full   = full.rstrip('?').rstrip('/')
                    if full and full not in seen:
                        seen.add(full)
                        found.append(full)
                        bus.push_url(full, r.status_code)
                except Exception:
                    continue

            bus.log(f"  {len(found)} enlaces en {urlparse(url).netloc}", "ok")
            return None, found, base, r.status_code

        except requests.exceptions.Timeout:
            bus.log(f"Timeout: {url[:60]}", "warn")
            return None, [], url, 0
        except requests.exceptions.TooManyRedirects:
            bus.log(f"Demasiadas redirecciones: {url[:55]}", "warn")
            return None, [], url, 0
        except requests.exceptions.ConnectionError:
            bus.log(f"Sin conexion: {url[:60]}", "warn")
            return None, [], url, 0
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else 0
            bus.log(f"HTTP {code}: {url[:55]}", "warn")
            return None, [], url, code
        except Exception as e:
            bus.log(f"Error inesperado: {str(e)[:50]}", "warn")
            return None, [], url, 0

    def _verify(self, url):
        bus.log(f"Chk: {urlparse(url).netloc}{urlparse(url).path[:35]}", "check")
        try:
            r  = self._session.head(url, timeout=5, verify=False, allow_redirects=True)
            ok = r.status_code < 400
            bus.log(f"  [{r.status_code}] {url[:55]}",
                    "ok" if ok else "warn" if r.status_code < 500 else "error")
            bus.inc('verified' if ok else 'errors')
            return {'url': url, 'status': r.status_code, 'ok': ok}
        except Exception:
            bus.log(f"  [TIMEOUT] {url[:55]}", "error")
            bus.inc('errors')
            return {'url': url, 'status': 0, 'ok': False}

    def run(self, target, verificar, recursivo, profundidad, resume=False):
        from collections import deque
        from functools import lru_cache

        vistos   = set()
        todos_d  = {}          # dict url→entry: O(1) lookup en lugar de O(n) any()
        cola     = deque()     # deque: popleft() O(1) en lugar de pop(0) O(n)
        cola.append((target, 0))
        redir    = None
        options_snapshot = {
            'verificar': verificar, 'recursivo': recursivo, 'profundidad': profundidad
        }
        # Checkpoint inteligente: cada 500 nuevos O cuando han pasado 60s
        urls_desde_ck  = 0
        tiempo_ck      = time.time()
        CKPT_LINKS     = 500
        CKPT_SECS      = 60

        try:
            bus.log("Motor v5.2 iniciado", "start")
            if not target.startswith(('http://', 'https://')):
                target = 'https://' + target
            dominio = urlparse(target).netloc

            if resume:
                saved = memory.load()
                if saved:
                    bus.log("Reanudando sesion guardada...", "start")
                    bus.log(f"  Visitadas: {len(saved['vistos'])}  Pendientes: {len(saved['cola'])}  Links: {len(saved['links'])}", "info")
                    vistos  = set(saved['vistos'])
                    # Reconstruir dict desde lista guardada
                    todos_d = {e['url']: e for e in saved['links']}
                    cola    = deque(tuple(x) for x in saved['cola'])
                    target  = saved['target']
                    dominio = urlparse(target).netloc
                    verificar  = saved['options'].get('verificar', verificar)
                    recursivo  = saved['options'].get('recursivo', recursivo)
                    profundidad= saved['options'].get('profundidad', profundidad)
                    options_snapshot = {'verificar': verificar, 'recursivo': recursivo, 'profundidad': profundidad}
                    with bus._lock:
                        bus.counters['pages'] = len(vistos)
                        bus.counters['links'] = len(todos_d)
                    bus.log("Sesion restaurada. Continuando...", "ok")
                else:
                    bus.log("Sin sesion valida. Iniciando desde cero.", "warn")
                    resume = False

            if not resume:
                bus.log(f"Objetivo: {target}", "info")
                if recursivo:
                    bus.log(f"Crawling — profundidad {profundidad}", "info")

            while cola:
                try:
                    url_act, nivel = cola.popleft()   # O(1) con deque
                    if url_act in vistos:
                        continue
                    vistos.add(url_act)
                    bus.inc('pages')

                    err, enlaces, url_real, page_status = self._fetch(url_act)
                    if nivel == 0 and url_real != url_act and not resume:
                        redir = url_real
                        bus.log(f"Redirigido: {url_real}", "warn")

                    if err:
                        if nivel == 0 and not resume:
                            bus.log("Fallo en objetivo.", "error")
                            memory.clear()
                            bus.set_result({'error': err})
                            return
                        continue

                    nuevos = 0
                    st = page_status if (page_status and page_status >= 100) else None
                    for enlace in enlaces:
                        if enlace in todos_d:          # O(1) dict lookup
                            continue
                        interno = dominio in urlparse(enlace).netloc
                        todos_d[enlace] = {
                            'url': enlace, 'interno': interno,
                            'status': st,
                            'ok': st < 400 if st else None,
                            'nivel': nivel
                        }
                        nuevos += 1
                        if recursivo and interno and nivel < profundidad and enlace not in vistos:
                            cola.append((enlace, nivel + 1))

                    urls_desde_ck += nuevos
                    ahora = time.time()
                    if urls_desde_ck >= CKPT_LINKS or (ahora - tiempo_ck) >= CKPT_SECS:
                        urls_desde_ck = 0
                        tiempo_ck     = ahora
                        todos_list = list(todos_d.values())
                        memory.save({
                            'target': target, 'vistos': list(vistos),
                            'cola':   [list(x) for x in cola],
                            'links':  todos_list,
                            'options': options_snapshot, 'completed': False
                        })
                        bus.log(f"Checkpoint guardado ({len(todos_d)} links, {len(cola)} pendientes)", "info")

                except Exception as _loop_err:
                    bus.log(f"URL omitida: {str(_loop_err)[:50]}", "warn")
                    continue

            todos = list(todos_d.values())
            bus.log(f"Extraccion completa: {len(todos)} enlaces.", "ok")

            if verificar and todos:
                bus.log(f"Verificando {len(todos)} enlaces...", "info")
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                    res_list = list(ex.map(self._verify, [e['url'] for e in todos]))
                mapa = {r['url']: r for r in res_list}
                for e in todos:
                    r = mapa.get(e['url'], {})
                    e['status'] = r.get('status')
                    e['ok']     = r.get('ok')
                bus.log("Verificacion completada.", "ok")

            bus.log("Analisis finalizado.", "finish")
            memory.save({
                'target': target, 'vistos': list(vistos), 'cola': [],
                'links':  todos, 'options': options_snapshot, 'completed': True
            })
            bus.log("Sesion final guardada en disco.", "ok")
            bus.set_result({
                'total':    len(todos),
                'internos': [e for e in todos if     e['interno']],
                'externos': [e for e in todos if not e['interno']],
                'url_final': redir
            })

        except Exception as e:
            bus.log(f"ERROR CRITICO: {e}", "error")
            try:
                memory.save({
                    'target': target, 'vistos': list(vistos),
                    'cola':   [list(x) for x in cola],
                    'links':  todos, 'options': options_snapshot, 'completed': False
                })
                bus.log("Estado de emergencia guardado.", "warn")
            except Exception:
                pass
            bus.set_result({'error': str(e)})


engine = LinkEngine()


# ==============================================================================
# SERVIDOR HTTP
# ==============================================================================
class WebHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin',  '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path == '/':
                body = HTML_CONTENT.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.end_headers()
                self.wfile.write(body)

            elif self.path == '/api/stream':
                self._json(200, bus.poll())

            elif self.path == '/api/health':
                self._json(200, {'status': 'ok', 'version': '5.2'})

            elif self.path == '/api/session':
                summary = memory.summary()
                self._json(200, {'exists': summary is not None, 'summary': summary})

            elif self.path == '/api/session/clear':
                memory.clear()
                self._json(200, {'status': 'cleared'})

            elif self.path.startswith('/api/grafo'):
                result = bus.result
                if not result or not result.get('internos'):
                    self._json(404, {'error': 'Sin datos internos'})
                    return
                p0 = urlparse(result['internos'][0]['url'])
                grafo = generar_mapa_jerarquico(result['internos'],
                                                f"{p0.scheme}://{p0.netloc}")
                self._json(200, grafo)

            else:
                self.send_error(404)

        except Exception as e:
            bus.log(f"GET error: {e}", "error")
            self._json(500, {'error': str(e)})

    def do_POST(self):
        try:
            if self.path == '/api/scan':
                length = int(self.headers.get('Content-Length', 0))
                data   = json.loads(self.rfile.read(length).decode('utf-8'))
                if bus.running:
                    self._json(409, {'error': 'Scan ya en curso'})
                    return
                bus.reset()
                bus.log(f"Solicitud: {data.get('url','')[:60]}", "info")
                t = threading.Thread(
                    target=engine.run,
                    args=(data.get('url',''), bool(data.get('verificar',False)),
                          bool(data.get('recursivo',False)), int(data.get('profundidad',1)), False),
                    daemon=True
                )
                t.start()
                self._json(200, {'status': 'started'})

            elif self.path == '/api/resume':
                if bus.running:
                    self._json(409, {'error': 'Ya hay un scan en curso'})
                    return
                saved = memory.load()
                if not saved:
                    self._json(404, {'error': 'No hay sesion guardada'})
                    return
                bus.reset()
                bus.log("Reanudando sesion guardada...", "start")
                t = threading.Thread(
                    target=engine.run,
                    args=(saved['target'],
                          saved['options'].get('verificar', False),
                          saved['options'].get('recursivo', False),
                          saved['options'].get('profundidad', 1),
                          True),
                    daemon=True
                )
                t.start()
                self._json(200, {'status': 'resumed', 'summary': memory.summary()})

            elif self.path == '/api/exportar-grafo':
                result = bus.result
                if not result or not result.get('internos'):
                    self._json(404, {'error': 'Sin datos internos'})
                    return
                p0    = urlparse(result['internos'][0]['url'])
                grafo = generar_mapa_jerarquico(result['internos'],
                                                f"{p0.scheme}://{p0.netloc}")
                self._json(200, {'grafo': grafo,
                                 'filename': f"grafo_{p0.netloc}_{int(time.time())}.json"})

            else:
                self.send_error(404)

        except Exception as e:
            bus.log(f"POST error: {e}", "error")
            self._json(500, {'error': str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


# ==============================================================================
# LAUNCHER
# ==============================================================================
def launch_ui(port=5000):
    import socket
    try:
        subprocess.run(['fuser', '-k', f'{port}/tcp'],
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(0.3)
    except Exception:
        pass
    for candidate in range(port, port + 10):
        try:
            test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test.bind(('0.0.0.0', candidate))
            test.close()
            port = candidate
            break
        except OSError:
            continue

    server = HTTPServer(('0.0.0.0', port), WebHandler)
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    hilo   = threading.Thread(target=server.serve_forever, daemon=True)
    hilo.start()

    url = f'http://127.0.0.1:{port}'
    print(f'\n{C.CYAN}{"="*58}{C.END}')
    print(f'  {C.BOLD}LINK ANALYZER PRO v5.2 — MEMORIA PERSISTENTE{C.END}')
    print(f'  {C.CYAN}{"="*58}{C.END}')
    print(f'  {C.GREEN}Servidor : {url}{C.END}')
    print(f'  {C.GREEN}Workspace: {WORKSPACE_DIR}{C.END}')
    print(f'  {C.GREEN}Sesion   : {SESSION_FILE}{C.END}')
    summary = memory.summary()
    if summary:
        print(f'  {C.YELLOW}Sesion guardada encontrada:{C.END}')
        print(f'     URL    : {summary["target"][:50]}')
        print(f'     Links  : {summary["links_found"]}  |  {summary["saved_at"]}')
        estado = "Completado" if summary["completed"] else "Incompleto — pulse REANUDAR"
        print(f'     Estado : {estado}')
    print(f'  {C.YELLOW}Ctrl+C para detener{C.END}\n')
    time.sleep(0.5)
    for cmd in (
        ['am','start','-a','android.intent.action.VIEW','-d',url,
         '-n','com.android.chrome/com.google.android.apps.chrome.Main'],
        ['am','start','-a','android.intent.action.VIEW','-d',url],
        ['termux-open', url],
        ['xdg-open', url],
    ):
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            break
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f'\n{C.RED}[!]{C.END} Detenido. Sesion guardada en disco.')
        server.shutdown()


# ==============================================================================
# EXPORTADORES
# ==============================================================================
def exportar_json(res, filepath=None):
    import datetime
    if filepath is None:
        ts       = time.strftime('%Y%m%d_%H%M%S')
        filepath = os.path.join(EXPORTS_DIR, f'scan_{ts}.json')
    data = {
        'meta': {
            'herramienta': 'Link Analyzer PRO v5.2',
            'autor':       'Yoandis Rodriguez — github.com/YoandisR',
            'fecha':       datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'url_final':   res.get('url_final'),
            'total':       res['total'],
            'internos':    len(res['internos']),
            'externos':    len(res['externos']),
        },
        'internos': res['internos'],
        'externos': res['externos'],
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


def exportar_pdf(res, filepath=None):
    import datetime, webbrowser
    if filepath is None:
        ts       = time.strftime('%Y%m%d_%H%M%S')
        filepath = os.path.join(EXPORTS_DIR, f'scan_{ts}.pdf')
    fecha = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    todos = res['internos'] + res['externos']
    filas = ''
    for i, e in enumerate(todos, 1):
        tipo   = 'INT' if e['interno'] else 'EXT'
        color  = '#00ff88' if e['interno'] else '#aa88ff'
        st_txt = f"checkmark {e['status']}" if e.get('ok') else (
            f"x {e['status']}" if e.get('status') else '-')
        st_col = '#00ff88' if e.get('ok') else '#ff5555'
        filas += (f'<tr><td style="color:#7af;text-align:right">{i}</td>'
                  f'<td style="word-break:break-all">{e["url"]}</td>'
                  f'<td style="color:{color};text-align:center;font-weight:700">{tipo}</td>'
                  f'<td style="color:{st_col};text-align:center">{st_txt}</td>'
                  f'<td style="color:#7af;text-align:center">{e.get("nivel",0)}</td></tr>')
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Link Analyzer PRO v5.2 — Reporte</title>
<style>body{{background:#020810;color:#00f5ff;font-family:monospace;padding:2rem;font-size:12px}}
h1{{font-size:1.8rem;background:linear-gradient(135deg,#00f5ff,#7b2fff);-webkit-background-clip:text;color:transparent}}
.meta{{color:#7af;font-size:.8rem;margin-bottom:1.5rem;border-bottom:1px solid #0ff3;padding-bottom:.8rem}}
table{{width:100%;border-collapse:collapse}}th{{background:#0a1a2a;color:#00f5ff;padding:6px 10px;text-align:left;border-bottom:2px solid #0ff5}}
td{{padding:5px 10px;border-bottom:1px solid #0ff1;vertical-align:top}}
tr:nth-child(even){{background:rgba(0,245,255,.03)}}
.footer{{margin-top:1.5rem;color:#7af;font-size:.75rem;text-align:center}}
@media print{{body{{background:#fff;color:#000}}h1{{color:#000}}th{{background:#eee;color:#000}}td{{color:#000}}}}</style>
</head><body><h1>LINK ANALYZER PRO v5.2</h1>
<div class="meta">Generado: {fecha} | Total: {res['total']} | Internos: {len(res['internos'])} | Externos: {len(res['externos'])}</div>
<table><thead><tr><th>#</th><th>URL</th><th>Tipo</th><th>Status</th><th>Lvl</th></tr></thead>
<tbody>{filas}</tbody></table>
<div class="footer">Link Analyzer PRO v5.2 · Yoandis Rodriguez · github.com/YoandisR · MIT License</div>
</body></html>"""
    html_tmp = filepath.replace('.pdf', '_reporte.html')
    with open(html_tmp, 'w', encoding='utf-8') as f:
        f.write(html)
    try:
        if shutil.which('termux-open'):
            subprocess.Popen(['termux-open', html_tmp])
        elif shutil.which('am'):
            subprocess.Popen(['am','start','-a','android.intent.action.VIEW',
                              '-d',f'file://{os.path.abspath(html_tmp)}'],
                             stderr=subprocess.DEVNULL)
        else:
            webbrowser.open(f'file://{os.path.abspath(html_tmp)}')
    except Exception:
        pass
    return html_tmp


# ==============================================================================
# MODO CLI
# ==============================================================================
def modo_cli():
    print(f'\n{C.CYAN}╔{"═"*54}╗{C.END}')
    print(f'  {C.CYAN}║{C.END}  {C.BOLD}LINK ANALYZER PRO v5.2 — Modo CLI{C.END}           {C.CYAN}║{C.END}')
    print(f'  {C.CYAN}║{C.END}  Creado por: Yoandis Rodriguez                 {C.CYAN}║{C.END}')
    print(f'  {C.CYAN}╚{"═"*54}╝{C.END}\n')

    summary = memory.summary()
    if summary:
        print(f'  {C.YELLOW}Sesion guardada encontrada:{C.END}')
        print(f'     URL   : {summary["target"][:55]}')
        print(f'     Links : {summary["links_found"]}  |  {summary["saved_at"]}')
        print(f'     Estado: {"Completado" if summary["completed"] else "Incompleto"}\n')
        resp = input(f'  {C.YELLOW}Reanudar sesion guardada? [S/n]:{C.END} ').strip().lower()
        if resp != 'n':
            bus.reset()
            t = threading.Thread(
                target=engine.run,
                args=(summary['target'],
                      summary['options'].get('verificar', False),
                      summary['options'].get('recursivo', False),
                      summary['options'].get('profundidad', 1),
                      True),
                daemon=False
            )
            t.start()
            _cli_watch_and_export(t, summary['options'].get('verificar', False))
            return

    url = input(f'  {C.YELLOW}URL objetivo:{C.END} ').strip()
    if not url:
        print(f'  {C.RED}[!]{C.END} URL requerida.')
        return

    veri = input(f'  {C.YELLOW}Verificar status HTTP? [s/N]:{C.END} ').strip().lower() == 's'
    rec  = input(f'  {C.YELLOW}Crawling recursivo?    [s/N]:{C.END} ').strip().lower() == 's'
    dep  = 1
    if rec:
        try:
            dep = int(input(f'  {C.YELLOW}Profundidad (1-5):     {C.END} ').strip())
        except ValueError:
            dep = 1

    print(f'\n{C.GREEN}[*]{C.END} Iniciando motor...\n')
    bus.reset()
    t = threading.Thread(target=engine.run, args=(url, veri, rec, dep, False), daemon=False)
    t.start()
    _cli_watch_and_export(t, veri)


def _cli_watch_and_export(t, veri):
    # ── helpers internos ─────────────────────────────────────────────────────
    def _get_cols():
        try:
            return os.get_terminal_size().columns
        except OSError:
            return 50                          # ancho seguro Termux movil

    def _badge(s):
        """Badge de color logico segun codigo HTTP."""
        if not s:
            return f"{C.GRAY}[---]{C.END}"
        try:
            sc = int(s)
        except (ValueError, TypeError):
            return f"{C.GRAY}[---]{C.END}"
        if sc < 300:
            return f"{C.GREEN}[{sc}]{C.END}"   # 2xx verde brillante
        if sc < 400:
            return f"{C.CYAN}[{sc}]{C.END}"    # 3xx cyan
        if sc < 500:
            return f"{C.YELLOW}[{sc}]{C.END}"  # 4xx amarillo
        return f"{C.RED}[{sc}]{C.END}"          # 5xx rojo

    def _print_url(u, cols):
        """
        Inserta una URL encima de la pizarra sin pisarla.
        Esquema:
          timestamp  → magenta
          badge HTTP → color segun codigo
          URL texto  → gris oscuro (contrasta con badges sin saturar pantalla)
        Secuencia ANSI:
          \\033[s   guardar cursor (en linea 1 de pizarra)
          \\033[2A  subir 2 filas
          \\033[L   insertar linea vacia (scroll hacia arriba)
          imprimir URL
          \\033[u   restaurar cursor a pizarra
        """
        max_url = max(cols - 14, 15)
        url_txt = u["u"][:max_url]
        ts      = f"{C.MAGENTA}[{u['t']}]{C.END}"
        line    = f"{ts} {_badge(u['s'])} {C.GRAY}{url_txt}{C.END}"
        sys.stdout.write(f"\033[s\033[2A\033[L{line}\033[u")
        sys.stdout.flush()

    def _draw_board(timer, vps, c, cols):
        """
        Pizarra de 2 lineas fijas. Esquema de color:
          TIME    → amarillo          (dato temporal)
          SPEED   → cyan              (rendimiento)
          PAG     → verde brillante   (exito de paginas)
          LNK     → AZUL BRILLANTE    (unico color en toda la interfaz)
          VER     → cyan
          ERR     → rojo
          labels  → blanco
          marcos  → magenta
          estado  → amarillo parpadeante visual
        """
        sep  = f"{C.MAGENTA}│{C.END}"
        wall = f"{C.MAGENTA}║{C.END}"

        l1 = (
            f"\r\033[K"
            f"{wall} "
            f"{C.WHITE}TIME:{C.YELLOW}{timer}{C.END} "
            f"{sep} "
            f"{C.WHITE}SPEED:{C.CYAN}{vps:.1f}u/s{C.END} "
            f"{sep} "
            f"{C.WHITE}PAG:{C.GREEN}{c['pages']}{C.END} "
            f"{sep} "
            f"{C.WHITE}LNK:{C.BOLD}{C.BLUE}{c['links']}{C.END} "
            f"{wall}"
        )
        l2 = (
            f"\r\033[K"
            f"{wall} "
            f"{C.WHITE}VER:{C.CYAN}{c['verified']}{C.END} "
            f"{sep} "
            f"{C.WHITE}ERR:{C.RED}{c['errors']}{C.END} "
            f"{sep} "
            f"{C.YELLOW}SCANNING...{C.END} "
            f"{wall}"
        )
        sys.stdout.write(f"{l1}\n{l2}\033[1A\r")
        sys.stdout.flush()

    # ── inicio ────────────────────────────────────────────────────────────────
    start_time  = time.time()
    last_update = 0.0
    timer       = "00:00"

    sys.stdout.write("\n\n")       # reservar 2 lineas para pizarra
    sys.stdout.write("\033[?25l") # ocultar cursor
    sys.stdout.flush()

    try:
        while bus.running or t.is_alive():
            snap    = bus.poll()
            now     = time.time()
            elapsed = now - start_time
            cols    = _get_cols()

            for u in snap["urls"]:
                _print_url(u, cols)

            if now - last_update >= 0.2:
                c   = snap["counters"]
                vps = c["pages"] / elapsed if elapsed > 0 else 0.0
                mins, secs = divmod(int(elapsed), 60)
                timer = f"{mins:02d}:{secs:02d}"
                _draw_board(timer, vps, c, cols)
                last_update = now

            time.sleep(0.05)

    finally:
        sys.stdout.write("\033[1B\n")
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        print(f"\n{C.GREEN}[✔] Escaneo completado en {timer}{C.END}\n")

    # Vaciar URLs residuales
    snap_final = bus.poll()
    cols = _get_cols()
    for u in snap_final["urls"]:
        print(f"{C.MAGENTA}[{u['t']}]{C.END} {_badge(u['s'])} {C.GRAY}{u['u'][:max(cols-14,20)]}{C.END}")

    res = bus.result
    if not res or "error" in res:
        print(f'\n{C.RED}[!] Error: {res.get("error") if res else "desconocido"}{C.END}')
        return

    print(f'\n{C.GREEN}╔{"═"*54}╗{C.END}')
    print(f'  {C.GREEN}║{C.END}          {C.BOLD}RESULTADOS{C.END}                        {C.GREEN}║{C.END}')
    print(f'  {C.GREEN}╚{"═"*54}╝{C.END}\n')
    print(f'  {C.WHITE}Total   :{C.END} {C.BOLD}{res["total"]}{C.END} enlaces')
    print(f'  {C.CYAN}Internos:{C.END} {C.GREEN}{len(res["internos"])}{C.END}')
    print(f'  {C.CYAN}Externos:{C.END} {C.YELLOW}{len(res["externos"])}{C.END}')

    if veri:
        todos   = res["internos"] + res["externos"]
        activos = sum(1 for e in todos if e.get("ok"))
        errores = sum(1 for e in todos if not e.get("ok"))
        print(f'  {C.GREEN}Activos :{C.END} {C.GREEN}{activos}{C.END}')
        print(f'  {C.RED}Errores :{C.END} {C.RED}{errores}{C.END}')

    mostrar = input(f'\n{C.YELLOW}Mostrar lista? [s/N]:{C.END} ').strip().lower()
    if mostrar == 's':
        print(f'\n{C.GREEN}{"─"*72}{C.END}')
        for e in res['internos']:
            st = (f'{C.GREEN}[{e["status"]:>3}]{C.END}' if e.get('ok') is True else
                  f'{C.RED}[{str(e.get("status") or "ERR"):>3}]{C.END}' if e.get('ok') is False else
                  f'{C.GRAY}[ - ]{C.END}')
            print(f'{C.CYAN}[INT]{C.END} {st} {C.GRAY}{e["url"]}{C.END}')
        for e in res['externos']:
            st = (f'{C.GREEN}[{e["status"]:>3}]{C.END}' if e.get('ok') is True else
                  f'{C.RED}[{str(e.get("status") or "ERR"):>3}]{C.END}' if e.get('ok') is False else
                  f'{C.GRAY}[ - ]{C.END}')
            print(f'{C.MAGENTA}[EXT]{C.END} {st} {C.GRAY}{e["url"]}{C.END}')

    print(f'\n{C.CYAN}[1]{C.END} JSON  {C.CYAN}[2]{C.END} PDF  {C.CYAN}[3]{C.END} Ambos  {C.GRAY}[Enter] Salir{C.END}')
    opcion  = input(f'{C.YELLOW}Opcion:{C.END} ').strip()
    ts      = time.strftime('%Y%m%d_%H%M%S')
    base_fn = os.path.join(EXPORTS_DIR, f'scan_{ts}')

    if opcion in ('1', '3'):
        fn = base_fn + '.json'
        exportar_json(res, fn)
        print(f'  {C.GREEN}[ok] JSON:{C.END} ./workspace/exports/scan_{ts}.json')
    if opcion in ('2', '3'):
        fn      = base_fn + '.pdf'
        html_fn = exportar_pdf(res, fn)
        print(f'  {C.GREEN}[ok] HTML:{C.END} ./workspace/exports/scan_{ts}_reporte.html')


# ==============================================================================
# HTML EMBEBIDO
# ==============================================================================
HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no,maximum-scale=1">
<title>Link Analyzer PRO v5.2</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{--bg:#020810;--c1:#00f5ff;--c2:#7b2fff;--c3:#00ff88;--c4:#ff3c6e;--c5:#ffb300;--c6:#ff8c00;--surf:rgba(0,20,40,.75);--bdr:rgba(0,245,255,.25)}
html,body{min-height:100vh;background:var(--bg);color:var(--c1);font-family:'Share Tech Mono',monospace;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;z-index:0;background:radial-gradient(ellipse 120% 60% at 20% -10%,rgba(0,245,255,.07) 0%,transparent 60%),radial-gradient(ellipse 80% 80% at 80% 110%,rgba(123,47,255,.08) 0%,transparent 60%);animation:bgPulse 8s ease-in-out infinite alternate}
@keyframes bgPulse{to{opacity:.6}}
body::after{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;background-image:repeating-linear-gradient(0deg,rgba(0,245,255,.03) 0 1px,transparent 1px 40px),repeating-linear-gradient(90deg,rgba(0,245,255,.03) 0 1px,transparent 1px 40px)}
.wrap{position:relative;z-index:2;max-width:960px;margin:0 auto;padding:1.2rem}
.hero{text-align:center;padding:2rem .5rem 1.5rem;margin-bottom:1.5rem;border-bottom:1px solid var(--bdr)}
.hero-title{font-family:'Orbitron',monospace;font-weight:900;font-size:clamp(2.4rem,9vw,5rem);line-height:1;letter-spacing:-1px;background:linear-gradient(135deg,#00f5ff 0%,#7b2fff 50%,#00ff88 100%);-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 18px rgba(0,245,255,.5));animation:titleGlow 3s ease-in-out infinite alternate}
@keyframes titleGlow{from{filter:drop-shadow(0 0 12px rgba(0,245,255,.4))}to{filter:drop-shadow(0 0 28px rgba(123,47,255,.7))}}
.hero-sub{font-size:.75rem;letter-spacing:4px;text-transform:uppercase;color:rgba(0,245,255,.55);margin-top:.6rem}
.hero-ver{display:inline-block;font-family:'Orbitron',monospace;font-size:.65rem;font-weight:700;padding:.15rem .6rem;border:1px solid var(--c2);border-radius:3px;color:var(--c2);margin-top:.5rem;letter-spacing:2px}
.hero-credits{margin-top:.8rem;font-size:.68rem;color:rgba(0,245,255,.4);display:flex;justify-content:center;gap:1.5rem;flex-wrap:wrap}
.hero-credits a{color:var(--c1);text-decoration:none;opacity:.7}.hero-credits a:hover{opacity:1}
.hero-line{width:60%;max-width:400px;height:2px;margin:.8rem auto 0;background:linear-gradient(90deg,transparent,var(--c1),var(--c2),transparent);animation:lineScan 3s ease-in-out infinite}
@keyframes lineScan{0%,100%{opacity:.4;transform:scaleX(.7)}50%{opacity:1;transform:scaleX(1)}}
.card{background:var(--surf);backdrop-filter:blur(12px);border:2px solid var(--c1);border-radius:14px;padding:1.4rem;margin-bottom:1.2rem;box-shadow:0 0 18px rgba(0,245,255,.25),inset 0 0 18px rgba(0,245,255,.04)}
.inp-row{display:flex;gap:.7rem;margin-bottom:1rem;flex-wrap:wrap}
input[type=text]{flex:1;min-width:200px;background:rgba(0,10,20,.8);border:1px solid var(--bdr);color:var(--c1);font-family:'Share Tech Mono',monospace;font-size:.9rem;padding:.75rem 1.1rem;border-radius:8px;outline:none;transition:border-color .2s,box-shadow .2s}
input[type=text]:focus{border-color:var(--c1);box-shadow:0 0 12px rgba(0,245,255,.3)}
input[type=text]::placeholder{color:rgba(0,245,255,.25)}
input[type=number]{background:rgba(0,10,20,.8);border:1px solid var(--bdr);color:var(--c1);font-family:'Share Tech Mono',monospace;padding:.35rem .6rem;border-radius:6px;width:58px;outline:none;font-size:.82rem}
.btn-scan{background:linear-gradient(135deg,#0af 0%,#07e 100%);border:none;color:#000;font-family:'Orbitron',monospace;font-weight:700;font-size:.85rem;letter-spacing:1.5px;padding:.75rem 1.8rem;border-radius:8px;cursor:pointer;transition:all .2s;text-transform:uppercase;white-space:nowrap;box-shadow:0 4px 20px rgba(0,170,255,.4)}
.btn-scan:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(0,170,255,.6)}
.btn-scan:active{transform:scale(.97)}
.btn-scan:disabled{opacity:.4;cursor:not-allowed;transform:none;box-shadow:none}
.btn-resume{background:transparent;border:2px solid var(--c6);color:var(--c6);font-family:'Orbitron',monospace;font-weight:700;font-size:.75rem;letter-spacing:1px;padding:.75rem 1.2rem;border-radius:8px;cursor:pointer;transition:all .25s;text-transform:uppercase;white-space:nowrap;position:relative;overflow:visible;display:flex;align-items:center;gap:.45rem;box-shadow:0 0 8px rgba(255,140,0,.15)}
.btn-resume:hover{background:rgba(255,140,0,.12);box-shadow:0 0 20px rgba(255,140,0,.4);transform:translateY(-2px)}
.btn-resume:disabled{opacity:.35;cursor:not-allowed;transform:none}
.btn-resume.has-session{animation:resumePulse 2.5s ease-in-out infinite;box-shadow:0 0 14px rgba(255,140,0,.3)}
@keyframes resumePulse{0%,100%{box-shadow:0 0 8px rgba(255,140,0,.2);border-color:rgba(255,140,0,.6)}50%{box-shadow:0 0 22px rgba(255,140,0,.55);border-color:var(--c6)}}
.btn-resume.no-session{border-color:rgba(255,140,0,.25);color:rgba(255,140,0,.35)}
.session-badge{position:absolute;top:-38px;left:50%;transform:translateX(-50%);background:rgba(2,8,16,.95);border:1px solid var(--c6);border-radius:6px;padding:.3rem .7rem;font-size:.62rem;color:var(--c6);white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .2s;z-index:50}
.btn-resume:hover .session-badge{opacity:1}
.session-banner{background:linear-gradient(90deg,rgba(255,140,0,.08),rgba(255,140,0,.04));border:1px solid rgba(255,140,0,.35);border-radius:8px;padding:.6rem 1rem;font-size:.72rem;color:var(--c6);margin-top:.8rem;display:flex;align-items:center;gap:.7rem;flex-wrap:wrap;animation:bannerIn .4s ease}
@keyframes bannerIn{from{opacity:0;transform:translateY(-5px)}to{opacity:1;transform:translateY(0)}}
.session-banner.hidden{display:none!important}
.session-banner-text{flex:1;line-height:1.6}
.session-banner-text strong{color:#ffb347}
.session-banner-clear{background:transparent;border:1px solid rgba(255,60,110,.35);color:rgba(255,60,110,.6);font-family:'Share Tech Mono',monospace;font-size:.6rem;padding:.2rem .55rem;border-radius:4px;cursor:pointer;transition:all .15s;white-space:nowrap;text-transform:uppercase}
.session-banner-clear:hover{border-color:var(--c4);color:var(--c4)}
.opts{display:flex;gap:1.2rem;flex-wrap:wrap;font-size:.78rem;color:rgba(0,245,255,.6);align-items:center}
.tog{display:flex;align-items:center;gap:.45rem;cursor:pointer;user-select:none;transition:color .15s}
.tog:hover{color:var(--c1)}
.tog input[type=checkbox]{appearance:none;width:15px;height:15px;border:1px solid rgba(0,245,255,.4);border-radius:3px;background:transparent;cursor:pointer;position:relative;transition:all .15s}
.tog input[type=checkbox]:checked{background:var(--c1);border-color:var(--c1)}
.tog input[type=checkbox]:checked::after{content:"V";position:absolute;top:-3px;left:1px;font-size:11px;color:#000;font-weight:700}
.dep{display:flex;align-items:center;gap:.5rem;font-size:.78rem;color:rgba(0,245,255,.6)}
.status-bar{font-size:.72rem;padding:.45rem .9rem;border-radius:6px;margin-bottom:1rem;font-family:'Share Tech Mono',monospace;display:none;border-left:3px solid var(--c1);background:rgba(0,245,255,.06);color:var(--c1)}
.status-bar.err{border-color:var(--c4);background:rgba(255,60,110,.06);color:var(--c4)}
.status-bar.ok{border-color:var(--c3);background:rgba(0,255,136,.06);color:var(--c3)}
.status-bar.warn{border-color:var(--c6);background:rgba(255,140,0,.06);color:var(--c6)}
.bio-row{display:flex;overflow-x:auto;gap:.8rem;margin-bottom:1.2rem;padding:.3rem 0;scrollbar-width:thin}
.bio-row::-webkit-scrollbar{height:3px}
.bio-row::-webkit-scrollbar-thumb{background:var(--c1);border-radius:3px}
.bio-card{flex-shrink:0;min-width:130px;background:var(--surf);border:2px solid rgba(0,245,255,.5);border-radius:10px;padding:1rem 1.2rem;text-align:center;box-shadow:0 0 14px rgba(0,245,255,.15),inset 0 0 10px rgba(0,245,255,.04);position:relative;overflow:hidden;transition:box-shadow .3s}
.bio-card::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--c1),var(--c2))}
.bio-card.flash{box-shadow:0 0 28px rgba(0,245,255,.6),inset 0 0 14px rgba(0,245,255,.08)}
.bio-num{font-family:'Orbitron',monospace;font-size:2rem;font-weight:900;color:var(--c1);text-shadow:0 0 8px rgba(0,245,255,.5);line-height:1;transition:all .25s}
.bio-num.pop{color:#fff;text-shadow:0 0 20px var(--c1);transform:scale(1.08)}
.bio-lbl{font-size:.58rem;text-transform:uppercase;letter-spacing:2px;color:rgba(0,245,255,.45);margin-top:.3rem}
.bio-card.ckpt{border-color:rgba(255,140,0,.5)}
.bio-card.ckpt::before{background:linear-gradient(90deg,var(--c6),var(--c5))}
.bio-card.ckpt .bio-num{color:var(--c6);text-shadow:0 0 8px rgba(255,140,0,.4)}
.rain-box{background:rgba(0,5,15,.85);border:2px solid rgba(0,245,255,.55);border-radius:12px;margin-bottom:1.2rem;overflow:hidden;box-shadow:0 0 16px rgba(0,245,255,.15)}
.rain-hdr{background:rgba(0,245,255,.06);padding:.5rem 1rem;font-family:'Orbitron',monospace;font-size:.62rem;border-bottom:1px solid var(--bdr);display:flex;justify-content:space-between;align-items:center}
.rain-dot{width:8px;height:8px;border-radius:50%;background:rgba(0,245,255,.3);transition:all .3s}
.rain-dot.on{background:var(--c3);box-shadow:0 0 10px var(--c3);animation:dotPulse 1s ease-in-out infinite}
.rain-dot.resuming{background:var(--c6);box-shadow:0 0 10px var(--c6);animation:dotPulse 1s ease-in-out infinite}
@keyframes dotPulse{0%,100%{opacity:1}50%{opacity:.4}}
.rain-stream{height:280px;overflow-y:auto;padding:.5rem .7rem}
.rain-stream::-webkit-scrollbar{width:3px}
.rain-stream::-webkit-scrollbar-thumb{background:var(--c1);border-radius:3px}
.rain-item{display:flex;align-items:baseline;gap:.5rem;padding:4px 8px;margin-bottom:3px;border-left:2px solid var(--c1);background:rgba(0,245,255,.03);font-size:.88rem;word-break:break-all;animation:rainIn .2s ease-out}
.rain-item:hover{background:rgba(0,245,255,.1)}
.rain-item .rt{color:rgba(0,245,255,.35);font-size:.72rem;flex-shrink:0}
.rain-item .ru{color:#e0f8ff;font-size:.85rem}
/* Status badges — lluvia y tabla */
.s-badge{display:inline-block;font-family:'Orbitron',monospace;font-size:.6rem;font-weight:700;
  padding:.08rem .42rem;border-radius:3px;margin:0 .4rem 0 .2rem;flex-shrink:0;letter-spacing:.5px}
.sb-ok  {background:rgba(0,255,136,.15);color:#00ff88;border:1px solid rgba(0,255,136,.35)}
.sb-redir{background:rgba(0,245,255,.12);color:#00f5ff;border:1px solid rgba(0,245,255,.3)}
.sb-warn{background:rgba(255,179,0,.12);color:#ffb300;border:1px solid rgba(255,179,0,.3)}
.sb-err {background:rgba(255,60,110,.12);color:#ff3c6e;border:1px solid rgba(255,60,110,.3)}
.rain-item.resume-marker{border-left-color:var(--c6);background:rgba(255,140,0,.06)}
.rain-item.resume-marker .ru{color:var(--c6)}
@keyframes rainIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
.con-box{background:rgba(0,0,0,.85);border:2px solid rgba(0,245,255,.55);border-radius:12px;overflow:hidden;margin-bottom:1.2rem;box-shadow:0 0 16px rgba(0,245,255,.12)}
.con-hdr{background:rgba(0,245,255,.05);padding:.5rem 1rem;font-family:'Orbitron',monospace;font-size:.62rem;border-bottom:1px solid var(--bdr);display:flex;justify-content:space-between;align-items:center}
.log-stream{height:170px;overflow-y:auto;padding:.5rem .9rem;font-size:.68rem;line-height:1.65}
.log-stream::-webkit-scrollbar{width:3px}
.log-stream::-webkit-scrollbar-thumb{background:var(--c1);border-radius:3px}
.le{display:flex;gap:.6rem;padding:.06rem 0;border-bottom:1px solid rgba(0,245,255,.05)}
.lt{color:rgba(0,245,255,.3);flex-shrink:0}
.lm-info{color:rgba(0,245,255,.7)}.lm-process{color:#4af}.lm-ok{color:var(--c3)}.lm-check{color:#7cf}.lm-warn{color:var(--c5)}.lm-error{color:var(--c4)}.lm-start,.lm-finish{color:var(--c2);font-weight:600}
.ctrl-row{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center;margin-bottom:.8rem;display:none}
.fb{background:transparent;border:1px solid rgba(0,245,255,.2);color:rgba(0,245,255,.5);font-family:'Share Tech Mono',monospace;font-size:.65rem;padding:.28rem .75rem;border-radius:4px;cursor:pointer;transition:all .15s;text-transform:uppercase;letter-spacing:.8px}
.fb:hover{border-color:var(--c1);color:var(--c1)}
.fb.active{background:rgba(0,245,255,.1);border-color:var(--c1);color:var(--c1)}
.eb{background:transparent;border:1px solid rgba(123,47,255,.4);color:rgba(123,47,255,.8);font-family:'Share Tech Mono',monospace;font-size:.65rem;padding:.28rem .75rem;border-radius:4px;cursor:pointer;transition:all .15s;text-transform:uppercase}
.eb:hover{background:rgba(123,47,255,.1);border-color:var(--c2);color:var(--c2)}
.srch-f{flex:1;min-width:130px;font-size:.75rem!important;padding:.28rem .7rem!important}
#graphContainer{display:none;background:rgba(0,5,15,.9);border:2px solid rgba(123,47,255,.6);border-radius:12px;margin-bottom:1.2rem;box-shadow:0 0 24px rgba(123,47,255,.2);overflow:hidden}
#graphContainer.active{display:block}
#graphViz{width:100%;height:400px;background:radial-gradient(ellipse at center,rgba(0,20,40,.3) 0%,transparent 70%);cursor:grab;touch-action:none}
#graphViz:active{cursor:grabbing}
.graph-controls{display:flex;gap:.5rem;padding:.5rem 1rem;background:rgba(0,245,255,.05);border-bottom:1px solid var(--bdr);flex-wrap:wrap;align-items:center}
.graph-btn{background:transparent;border:1px solid rgba(123,47,255,.4);color:var(--c2);font-family:'Share Tech Mono',monospace;font-size:.65rem;padding:.28rem .75rem;border-radius:4px;cursor:pointer;transition:all .15s;text-transform:uppercase}
.graph-btn:hover{background:rgba(123,47,255,.15);border-color:var(--c2);color:#fff}
.graph-info{font-size:.7rem;color:rgba(0,245,255,.5);margin-left:auto}
.graph-legend{display:flex;gap:.8rem;font-size:.65rem;color:rgba(0,245,255,.4)}
.legend-item{display:flex;align-items:center;gap:.3rem}
.legend-dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.legend-root{background:var(--c1);box-shadow:0 0 8px var(--c1)}.legend-dir{background:var(--c2)}.legend-file{background:var(--c3)}.legend-cluster{background:var(--c5)}
.graph-tooltip{position:absolute;background:rgba(2,8,16,.95);border:1px solid var(--c1);border-radius:6px;padding:.5rem .8rem;font-size:.75rem;color:var(--c1);pointer-events:none;opacity:0;transition:opacity .15s;z-index:100;max-width:280px}
.graph-tooltip.visible{opacity:1}
.graph-tooltip .tt-url{color:#fff;font-weight:600;word-break:break-all;margin-bottom:.3rem;display:block}
.graph-tooltip .tt-meta{font-size:.65rem;color:rgba(0,245,255,.6)}
.view-toggle{display:flex;gap:.3rem;margin-bottom:.8rem}
.view-btn{flex:1;background:rgba(0,20,40,.6);border:1px solid var(--bdr);color:rgba(0,245,255,.6);font-family:'Share Tech Mono',monospace;font-size:.7rem;padding:.5rem;border-radius:6px;cursor:pointer;transition:all .2s;text-align:center}
.view-btn.active{background:linear-gradient(135deg,rgba(0,245,255,.2),rgba(123,47,255,.2));border-color:var(--c1);color:var(--c1);font-weight:600}
.rtable{background:rgba(0,5,15,.8);border:2px solid rgba(0,245,255,.55);border-radius:12px;overflow:hidden;margin-bottom:2rem;box-shadow:0 0 16px rgba(0,245,255,.12)}
.rtable table{width:100%;border-collapse:collapse;font-size:.95rem}
.rtable thead th{background:rgba(0,245,255,.08);padding:.7rem 1rem;text-align:left;font-family:'Orbitron',monospace;font-size:.65rem;letter-spacing:1px;color:rgba(0,245,255,.85);border-bottom:2px solid rgba(0,245,255,.4)}
.rtable tbody tr{border-bottom:1px solid rgba(0,245,255,.08);transition:background .1s;animation:rowIn .2s ease both}
.rtable tbody tr:hover{background:rgba(0,245,255,.07)}
.rtable tbody tr.row-err{border-left:3px solid var(--c4);background:rgba(255,60,110,.04)}
.rtable tbody tr.row-err:hover{background:rgba(255,60,110,.08)}
.rtable td{padding:.6rem 1rem;vertical-align:middle}
.ucell a{color:rgba(0,230,255,.95);text-decoration:none;font-size:.92rem;
display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
transition:all .15s;line-height:1.5}
.ucell a:hover{color:#fff;text-shadow:0 0 8px var(--c1);white-space:normal;overflow:visible}
.badge{display:inline-block;font-size:.57rem;padding:.12rem .45rem;border-radius:3px;font-weight:700;letter-spacing:.8px}
.bi{background:rgba(0,245,255,.08);color:var(--c1);border:1px solid rgba(0,245,255,.25)}
.be{background:rgba(123,47,255,.08);color:var(--c2);border:1px solid rgba(123,47,255,.25)}
.sok{color:var(--c3)}.serr{color:var(--c4)}.swrn{color:var(--c5)}
@keyframes rowIn{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:translateY(0)}}
footer{text-align:center;font-size:.6rem;color:rgba(0,245,255,.25);letter-spacing:1px;border-top:1px solid var(--bdr);padding-top:.8rem;margin-top:1rem}
footer a{color:rgba(0,245,255,.45);text-decoration:none}footer a:hover{color:var(--c1)}
@media(max-width:600px){.bio-card{min-width:110px;padding:.8rem 1rem}.bio-num{font-size:1.6rem}.hero-title{font-size:clamp(2rem,8vw,4rem)}.btn-resume{font-size:.65rem;padding:.65rem .9rem}}
</style>
</head>
<body>
<div class="wrap">
<div class="hero">
  <div class="hero-title">LINK<wbr>ANALYZER</div>
  <div class="hero-sub">Eje Central &nbsp;&middot;&nbsp; Memoria Persistente &nbsp;&middot;&nbsp; Quantum Live</div>
  <div class="hero-ver">PRO v5.2</div>
  <div class="hero-line"></div>
  <div class="hero-credits">
    <span>Creado por <a href="https://github.com/YoandisR" target="_blank">Yoandis Rodr&#237;guez</a></span>
    <span><a href="mailto:curvadigital0@gmail.com">curvadigital0@gmail.com</a></span>
  </div>
</div>

<div class="card">
  <div class="inp-row">
    <input type="text" id="uIn" placeholder="https://objetivo.com" autocomplete="off" spellcheck="false">
    <button class="btn-scan" id="btnS" onclick="startScan()">&#9654; SCAN</button>
    <button class="btn-resume no-session" id="btnR" onclick="resumeScan()">
      <span>&#9100;</span><span>REANUDAR</span>
      <span class="session-badge" id="resumeTooltip">Sin sesion guardada</span>
    </button>
  </div>
  <div class="session-banner hidden" id="sessionBanner">
    <span>&#9883;</span>
    <span class="session-banner-text" id="sessionBannerText">...</span>
    <button class="session-banner-clear" onclick="clearSession()">&#215; BORRAR</button>
  </div>
  <div class="opts">
    <label class="tog"><input type="checkbox" id="oV"> Verificar HTTP</label>
    <label class="tog"><input type="checkbox" id="oR" onchange="tDepth()"> Crawling recursivo</label>
    <div class="dep" id="dRow" style="display:none">Profundidad: <input type="number" id="oD" value="2" min="1" max="5"></div>
  </div>
</div>

<div class="status-bar" id="sb"></div>

<div class="bio-row">
  <div class="bio-card" id="bPag"><div class="bio-num" id="nPag">0</div><div class="bio-lbl">P&#225;ginas</div></div>
  <div class="bio-card" id="bLnk"><div class="bio-num" id="nLnk">0</div><div class="bio-lbl">Enlaces</div></div>
  <div class="bio-card" id="bVer"><div class="bio-num" id="nVer">0</div><div class="bio-lbl">Verificados</div></div>
  <div class="bio-card" id="bErr"><div class="bio-num" id="nErr">0</div><div class="bio-lbl">Errores</div></div>
  <div class="bio-card ckpt" id="bCkpt"><div class="bio-num" id="nCkpt">&#8212;</div><div class="bio-lbl">&#128190; Guardado</div></div>
</div>

<div class="rain-box">
  <div class="rain-hdr">
    <span>&#9685; FLUJO DE URLS</span>
    <div style="display:flex;align-items:center;gap:.5rem">
      <span id="rainCnt" style="font-size:.6rem;color:rgba(0,245,255,.4)">esperando...</span>
      <div class="rain-dot" id="rainDot"></div>
    </div>
  </div>
  <div class="rain-stream" id="rainStream">
    <div class="rain-item"><span class="rt">--:--:--</span><span class="ru">Esperando URLs...</span></div>
  </div>
</div>

<div class="con-box">
  <div class="con-hdr">
    <span>&#11042; CONSOLA</span>
    <span id="liveInd" style="color:rgba(0,245,255,.4);font-size:.62rem">&#9679; EN ESPERA</span>
  </div>
  <div class="log-stream" id="logStream">
    <div class="le"><span class="lt">--:--:--</span><span class="lm-info">Sistema listo. Ingresa URL y pulsa SCAN, o REANUDAR si hay sesion guardada.</span></div>
  </div>
</div>

<div class="view-toggle" id="viewToggle" style="display:none">
  <button class="view-btn active" onclick="toggleView('table',event)">&#128203; Tabla</button>
  <button class="view-btn" onclick="toggleView('graph',event)">&#128376;&#65039; Eje Central</button>
</div>

<div id="graphContainer">
  <div class="graph-controls">
    <button class="graph-btn" onclick="renderGraph()">&#128260; Recalcular</button>
    <button class="graph-btn" onclick="exportarGrafoJSON()">&#128190; JSON Grafo</button>
    <button class="graph-btn" onclick="resetZoom()">&#128269; Reset</button>
    <div class="graph-info"><span id="graphInfo">0 nodos · 0 conexiones</span></div>
    <div class="graph-legend">
      <span class="legend-item"><span class="legend-dot legend-root"></span>Ra&#237;z</span>
      <span class="legend-item"><span class="legend-dot legend-dir"></span>Carpeta</span>
      <span class="legend-item"><span class="legend-dot legend-file"></span>Archivo</span>
      <span class="legend-item"><span class="legend-dot legend-cluster"></span>Cluster</span>
    </div>
  </div>
  <div id="graphViz"></div>
</div>

<div class="ctrl-row" id="ctrlRow">
  <button class="fb active" onclick="filt('todos',this)">Todos</button>
  <button class="fb" onclick="filt('int',this)">Internos</button>
  <button class="fb" onclick="filt('ext',this)">Externos</button>
  <button class="fb" onclick="filt('ok',this)">Activos</button>
  <button class="fb" onclick="filt('err',this)">Errores</button>
  <input type="text" class="srch-f" id="srch" placeholder="Filtrar URL..." oninput="render()">
  <button class="eb" onclick="expCSV()">&#8595; CSV</button>
  <button class="eb" onclick="expTXT()">&#8595; TXT</button>
  <button class="eb" onclick="expJSON()">&#8595; JSON</button>
  <button class="eb" onclick="expPDF()">&#8595; PDF</button>
</div>
<div id="res"></div>

<footer>
  Link Analyzer PRO v5.2 &nbsp;&middot;&nbsp; Memoria Persistente &nbsp;&middot;&nbsp; MIT License &nbsp;&middot;&nbsp;
  <a href="https://github.com/YoandisR" target="_blank">github.com/YoandisR</a>
  &nbsp;&middot;&nbsp; Yoandis Rodr&#237;guez
</footer>
</div>

<script>
var BASE=window.location.origin;
var links=[],filtro='todos',pollTimer=null,totalRain=0,scanDone=false;
var graphData=null,simulation=null,svg=null,tooltip=null;
var sessionInfo=null,lastCkpt=0;

function esc(t){var d=document.createElement('div');d.textContent=t;return d.innerHTML;}
function tDepth(){document.getElementById('dRow').style.display=document.getElementById('oR').checked?'flex':'none';}
function sb(msg,type){var el=document.getElementById('sb');el.textContent=msg;el.className='status-bar '+(type||'');el.style.display='block';if(type==='ok'||type==='err')setTimeout(function(){el.style.display='none'},7000);}
function setNum(id,cid,val){var el=document.getElementById(id),prev=parseInt(el.textContent)||0;if(val===prev)return;el.textContent=val;if(val>prev){el.classList.add('pop');document.getElementById(cid).classList.add('flash');setTimeout(function(){el.classList.remove('pop');document.getElementById(cid).classList.remove('flash');},350);}}
function applyCounters(c){setNum('nPag','bPag',c.pages||0);setNum('nLnk','bLnk',c.links||0);setNum('nVer','bVer',c.verified||0);setNum('nErr','bErr',c.errors||0);}
function applyLogs(logs){
  if(!logs.length)return;
  var hasCkpt=logs.some(function(l){return l.m&&l.m.indexOf('Checkpoint guardado')!==-1;});
  if(hasCkpt){lastCkpt++;document.getElementById('nCkpt').textContent=lastCkpt;document.getElementById('bCkpt').classList.add('flash');setTimeout(function(){document.getElementById('bCkpt').classList.remove('flash');},400);}
  var s=document.getElementById('logStream');
  s.innerHTML=logs.map(function(l){return '<div class="le"><span class="lt">'+l.t+'</span><span class="lm-'+(l.c||'info')+'">'+esc(l.m)+'</span></div>';}).join('');
  s.scrollTop=s.scrollHeight;
}
function applyUrls(urls){
  if(!urls||!urls.length)return;
  var stream=document.getElementById('rainStream'),frag=document.createDocumentFragment();
  for(var i=urls.length-1;i>=0;i--){
    var u=urls[i];
    var div=document.createElement('div');
    div.className='rain-item';
    // Badge de status code junto a la URL
    var badge='';
    if(u.s&&parseInt(u.s)>=100){
      var sc=parseInt(u.s);
      var bcls=sc<300?'sb-ok':sc<400?'sb-redir':sc<500?'sb-warn':'sb-err';
      badge='<span class="s-badge '+bcls+'">'+sc+'</span>';
    }
    div.innerHTML='<span class="rt">['+u.t+']</span>'+badge+'<span class="ru">'+esc(u.u)+'</span>';
    frag.insertBefore(div,frag.firstChild);
  }
  stream.insertBefore(frag,stream.firstChild);
  while(stream.children.length>80)stream.removeChild(stream.lastChild);
  totalRain+=urls.length;document.getElementById('rainCnt').textContent=totalRain+' URLs';
}

function startPolling(isResume){
  var dot=document.getElementById('rainDot');
  dot.className='rain-dot '+(isResume?'resuming':'on');
  document.getElementById('liveInd').style.color=isResume?'#ff8c00':'#00ff88';
  document.getElementById('liveInd').textContent='\u25CF '+(isResume?'REANUDANDO':'PROCESANDO');
  if(pollTimer)clearInterval(pollTimer);
  pollTimer=setInterval(doPoll,400);
}
function stopPolling(){
  clearInterval(pollTimer);pollTimer=null;
  document.getElementById('rainDot').className='rain-dot';
  document.getElementById('liveInd').style.color='rgba(0,255,136,.8)';
  document.getElementById('liveInd').textContent='\u25CF COMPLETADO';
  setTimeout(checkSession,800);
  fetch(BASE+'/api/stream').then(function(r){return r.json();}).then(function(d){applyCounters(d.counters);applyLogs(d.logs);applyUrls(d.urls);}).catch(function(){});
}
function doPoll(){
  fetch(BASE+'/api/stream').then(function(r){return r.json();}).then(function(d){
    applyCounters(d.counters);applyLogs(d.logs);applyUrls(d.urls);
    if(!d.running&&d.result&&!scanDone){scanDone=true;clearInterval(pollTimer);pollTimer=null;finalize(d.result);}
  }).catch(function(){});
}

function checkSession(){
  fetch(BASE+'/api/session').then(function(r){return r.json();}).then(function(d){
    sessionInfo=d.exists?d.summary:null;updateResumeBtn();
  }).catch(function(){});
}
function updateResumeBtn(){
  var btn=document.getElementById('btnR'),banner=document.getElementById('sessionBanner'),tt=document.getElementById('resumeTooltip');
  if(!sessionInfo){btn.className='btn-resume no-session';tt.textContent='Sin sesion guardada';banner.classList.add('hidden');return;}
  btn.className='btn-resume has-session';
  var pending=sessionInfo.urls_pending>0?sessionInfo.urls_pending+' pendientes':'Completo';
  tt.textContent=(sessionInfo.completed?'OK Completado':'Incompleto')+' · '+sessionInfo.links_found+' links · '+sessionInfo.saved_at;
  var shortUrl=sessionInfo.target.length>50?sessionInfo.target.substring(0,47)+'...':sessionInfo.target;
  document.getElementById('sessionBannerText').innerHTML='<strong>&#9883; Sesion guardada</strong>: '+esc(shortUrl)+'&nbsp;&nbsp;|&nbsp;&nbsp;<strong>'+sessionInfo.links_found+'</strong> links&nbsp;&nbsp;|&nbsp;&nbsp;'+pending+'&nbsp;&nbsp;|&nbsp;&nbsp;<span style="opacity:.7">'+sessionInfo.saved_at+'</span>';
  banner.classList.remove('hidden');
  if(!sessionInfo.completed&&sessionInfo.urls_pending>0){sb('Sesion incompleta encontrada — '+sessionInfo.urls_pending+' URLs pendientes. Pulsa REANUDAR.','warn');}
}
function clearSession(){
  if(!confirm('Borrar la sesion guardada?'))return;
  fetch(BASE+'/api/session/clear').then(function(){sessionInfo=null;updateResumeBtn();sb('Sesion eliminada.','ok');}).catch(function(){});
}

function _resetUI(){
  links=[];totalRain=0;scanDone=false;lastCkpt=0;graphData=null;
  document.getElementById('res').innerHTML='';
  document.getElementById('ctrlRow').style.display='none';
  document.getElementById('viewToggle').style.display='none';
  document.getElementById('graphContainer').classList.remove('active');
  document.getElementById('nCkpt').textContent='\u2014';
  document.getElementById('rainCnt').textContent='0 URLs';
  ['nPag','nLnk','nVer','nErr'].forEach(function(id){document.getElementById(id).textContent='0';});
}

function startScan(){
  var url=document.getElementById('uIn').value.trim();
  if(!url){sb('Ingresa una URL objetivo','err');return;}
  var veri=document.getElementById('oV').checked,rec=document.getElementById('oR').checked,dep=rec?(parseInt(document.getElementById('oD').value)||2):1;
  _resetUI();
  document.getElementById('btnS').disabled=true;document.getElementById('btnR').disabled=true;
  sb('Iniciando escaneo...','');startPolling(false);
  fetch(BASE+'/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:url,verificar:veri,recursivo:rec,profundidad:dep})})
  .then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
  .then(function(d){if(d.error){stopPolling();document.getElementById('btnS').disabled=false;document.getElementById('btnR').disabled=false;sb('Error: '+d.error,'err');}})
  .catch(function(e){stopPolling();document.getElementById('btnS').disabled=false;document.getElementById('btnR').disabled=false;sb('Error: '+(e.message||'desconocido'),'err');});
}

function resumeScan(){
  if(!sessionInfo){sb('No hay sesion guardada.','err');return;}
  _resetUI();
  document.getElementById('uIn').value=sessionInfo.target;
  document.getElementById('btnS').disabled=true;document.getElementById('btnR').disabled=true;
  document.getElementById('rainStream').innerHTML='<div class="rain-item resume-marker"><span class="rt">'+new Date().toLocaleTimeString()+'</span><span class="ru">&#9100; REANUDANDO · '+sessionInfo.links_found+' links previos cargados...</span></div>';
  sb('Reanudando sesion guardada...','warn');startPolling(true);
  fetch(BASE+'/api/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})})
  .then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
  .then(function(d){if(d.error){stopPolling();document.getElementById('btnS').disabled=false;document.getElementById('btnR').disabled=false;sb('Error: '+d.error,'err');}else{sb('Sesion reanudada · continuando...','warn');}})
  .catch(function(e){stopPolling();document.getElementById('btnS').disabled=false;document.getElementById('btnR').disabled=false;sb('Error: '+(e.message||'desconocido'),'err');});
}

function finalize(data){
  document.getElementById('rainDot').className='rain-dot';
  document.getElementById('liveInd').style.color='rgba(0,255,136,.8)';
  document.getElementById('liveInd').textContent='\u25CF COMPLETADO';
  document.getElementById('btnS').disabled=false;document.getElementById('btnR').disabled=false;
  if(data.error){sb('Error: '+data.error,'err');document.getElementById('res').innerHTML='<div style="padding:2rem;color:var(--c4);text-align:center">&#9888; '+esc(data.error)+'</div>';checkSession();return;}
  links=data.internos.concat(data.externos);
  sb('Escaneo completado: '+data.total+' enlaces encontrados. Guardado en ./workspace/','ok');
  if(data.internos&&data.internos.length>0)document.getElementById('viewToggle').style.display='flex';
  document.getElementById('ctrlRow').style.display='flex';
  filtro='todos';document.querySelectorAll('.fb').forEach(function(b,i){b.classList.toggle('active',i===0);});
  render();checkSession();
}

function filt(f,b){filtro=f;document.querySelectorAll('.fb').forEach(function(x){x.classList.remove('active');});b.classList.add('active');render();}
function getFilt(){var q=document.getElementById('srch').value.toLowerCase();return links.filter(function(e){var ms=!q||e.url.toLowerCase().indexOf(q)!==-1,mf=true;if(filtro==='int')mf=e.interno;else if(filtro==='ext')mf=!e.interno;else if(filtro==='ok')mf=e.ok===true;else if(filtro==='err')mf=e.ok===false;return ms&&mf;});}
function dotHtml(e){
  // Sin datos o status=0 → guión neutro (0 no es un código HTTP real)
  if(e.status===null||e.status===undefined||parseInt(e.status)===0){
    return '<span style="color:rgba(0,245,255,.3)">&#8212;</span>';
  }
  var sc=parseInt(e.status);
  var cls=sc<300?'sb-ok':sc<400?'sb-redir':sc<500?'sb-warn':'sb-err';
  return '<span class="s-badge '+cls+'">'+sc+'</span>';
}
function render(){
  var l=getFilt(),rc=document.getElementById('res');
  if(!l.length){rc.innerHTML='<div style="padding:2rem;text-align:center;color:rgba(0,245,255,.3)">Sin resultados.</div>';return;}
  var html='<div class="rtable"><table><thead><tr>'+
    '<th style="width:36px">#</th>'+
    '<th>URL &nbsp;<span style="color:rgba(0,245,255,.3);font-weight:400;font-size:.55rem">tipo &middot; status</span></th>'+
    '</tr></thead><tbody>';
  l.forEach(function(e,i){
    var tbadge='<span class="badge '+(e.interno?'bi':'be')+'">'+(e.interno?'INT':'EXT')+'</span>';
    var sbadge='';
    if(e.status!==null&&e.status!==undefined){
      var sc=parseInt(e.status);
      var cls=sc<300?'sb-ok':sc<400?'sb-redir':sc<500?'sb-warn':'sb-err';
      sbadge=sc===0?'<span class="s-badge sb-err">Timeout</span>':'<span class="s-badge '+cls+'">'+sc+'</span>';
    }
    var isErr=e.status&&parseInt(e.status)>=400;
    html+='<tr class="'+(isErr?'row-err ':'')+ '" style="animation-delay:'+Math.min(i*.015,.4)+'s">'+
      '<td style="color:rgba(0,245,255,.3);font-size:.63rem;width:36px;text-align:right;vertical-align:top;padding-top:.8rem">'+(i+1)+'</td>'+
      '<td>'+
        '<div style="display:flex;gap:.4rem;align-items:center;margin-bottom:.25rem;flex-wrap:wrap">'+
          tbadge+sbadge+
          '<span style="color:rgba(0,245,255,.3);font-size:.6rem">lvl '+(e.nivel||0)+'</span>'+
        '</div>'+
        '<div class="ucell"><a href="'+esc(e.url)+'" target="_blank">'+esc(e.url)+'</a></div>'+
      '</td>'+
    '</tr>';
  });
  rc.innerHTML=html+'</tbody></table></div>';
}

function dl(name,content,type){var b=new Blob([content],{type:type}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;a.click();}
function expCSV(){var l=getFilt();if(!l.length)return;dl('enlaces.csv','url,tipo,status,nivel\n'+l.map(function(e){return '"'+e.url+'","'+(e.interno?'interno':'externo')+'","'+(e.status!==null?e.status:'')+'","'+(e.nivel||0)+'"';}).join('\n'),'text/csv');}
function expTXT(){var l=getFilt();if(!l.length)return;dl('enlaces.txt',l.map(function(e){return e.url;}).join('\n'),'text/plain');}
function expJSON(){if(!links.length)return;var internos=links.filter(function(e){return e.interno;}),externos=links.filter(function(e){return !e.interno;});dl('enlaces.json',JSON.stringify({meta:{herramienta:'Link Analyzer PRO v5.2',autor:'Yoandis Rodriguez',fecha:new Date().toLocaleString(),total:links.length,internos:internos.length,externos:externos.length},internos:internos,externos:externos},null,2),'application/json');}
function expPDF(){if(!links.length)return;var filas='',internos=links.filter(function(e){return e.interno;}),externos=links.filter(function(e){return !e.interno;});links.forEach(function(e,i){var tipo=e.interno?'INT':'EXT',tcolor=e.interno?'#00ff88':'#aa88ff',stxt=e.status?(e.ok?'ok '+e.status:'err '+e.status):'-',scol=e.ok?'#00ff88':e.status?'#ff5555':'#7af';filas+='<tr><td style="color:#7af;text-align:right">'+(i+1)+'</td><td style="word-break:break-all;font-size:11px">'+esc(e.url)+'</td><td style="color:'+tcolor+';text-align:center;font-weight:700">'+tipo+'</td><td style="color:'+scol+';text-align:center">'+stxt+'</td><td style="color:#7af;text-align:center">'+(e.nivel||0)+'</td></tr>';});var html='<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Link Analyzer PRO — Reporte</title><style>body{background:#020810;color:#00f5ff;font-family:monospace;padding:2rem;font-size:12px}h1{font-size:1.8rem;background:linear-gradient(135deg,#00f5ff,#7b2fff);-webkit-background-clip:text;color:transparent}table{width:100%;border-collapse:collapse}th{background:#0a1a2a;color:#00f5ff;padding:6px 10px;text-align:left;border-bottom:2px solid #0ff3}td{padding:5px 10px;border-bottom:1px solid #0ff1}tr:nth-child(even){background:rgba(0,245,255,.03)}@media print{body{background:#fff;color:#000}}</style></head><body><h1>LINK ANALYZER PRO v5.2</h1><p style="color:#7af;font-size:.8rem">'+new Date().toLocaleString()+' | Total: '+links.length+' | Int: '+internos.length+' | Ext: '+externos.length+'</p><table><thead><tr><th>#</th><th>URL</th><th>Tipo</th><th>Status</th><th>Lvl</th></tr></thead><tbody>'+filas+'</tbody></table></body></html>';var win=window.open('','_blank');if(win){win.document.write(html);win.document.close();setTimeout(function(){win.print();},800);}}

function toggleView(view,event){var tableEl=document.querySelector('.rtable'),graphEl=document.getElementById('graphContainer');document.querySelectorAll('.view-btn').forEach(function(b){b.classList.remove('active');});if(event&&event.target)event.target.classList.add('active');if(view==='graph'){if(tableEl)tableEl.style.display='none';graphEl.classList.add('active');if(graphData)renderGraph();}else{graphEl.classList.remove('active');if(tableEl)tableEl.style.display='block';}}
function buildGraphData(){if(!links||!links.length)return null;var pi=links.find(function(l){return l.interno;});if(!pi)return null;try{var urlObj=new URL(pi.url),dom=urlObj.protocol+'//'+urlObj.hostname,nodes={},lg=[],rootId=dom+'/';nodes[rootId]={id:rootId,name:"RAIZ",group:0,type:"root",size:25,url_count:0,depth:0};links.filter(function(l){return l.interno;}).forEach(function(entry){try{var parsed=new URL(entry.url),parts=parsed.pathname.split('/').filter(function(p){return p;}),acc="";parts.forEach(function(part,idx){var pp=acc;acc=pp?pp+'/'+part:'/'+part;var nid=dom+acc,isF=part.includes('.')&&!part.endsWith('/');if(!nodes[nid]){nodes[nid]={id:nid,name:part,group:Math.min(idx+1,6),type:isF?"file":"directory",size:isF?8:(15-Math.min(idx+1,7)),url_count:0,depth:idx+1};}if(idx===parts.length-1)nodes[nid].url_count+=1;var pid=pp?dom+pp:rootId;if(nodes[pid]&&pid!==nid&&!lg.some(function(e){return e.source===pid&&e.target===nid;})){lg.push({source:pid,target:nid,value:1,type:"contains"});}});}catch(e){}});var na=Object.values(nodes);return{nodes:na,links:lg,metadata:{dominio:dom,total_nodos:na.length,total_enlaces:lg.length,generado:new Date().toLocaleString()}};}catch(e){return null;}}
function renderGraph(){if(!graphData){graphData=buildGraphData();if(!graphData){document.getElementById('graphViz').innerHTML='<div style="padding:2rem;text-align:center;color:var(--c5)">Sin datos internos.</div>';return;}}if(typeof d3==='undefined'){var script=document.createElement('script');script.src='https://d3js.org/d3.v7.min.js';script.onload=function(){_initD3Graph();};document.head.appendChild(script);return;}_initD3Graph();}
function _initD3Graph(){d3.selectAll('.graph-tooltip').remove();var container=document.getElementById('graphViz');container.innerHTML='';var width=container.clientWidth||800,height=400;svg=d3.select('#graphViz').append('svg').attr('width','100%').attr('height',height).attr('viewBox',[0,0,width,height]).call(d3.zoom().on('zoom',function(e){g.attr('transform',e.transform);}));var g=svg.append('g');tooltip=d3.select('body').append('div').attr('class','graph-tooltip');var colors=d3.scaleOrdinal().domain(['root','directory','file','cluster']).range(['#00f5ff','#7b2fff','#00ff88','#ffb300']);simulation=d3.forceSimulation(graphData.nodes).force('link',d3.forceLink(graphData.links).id(function(d){return d.id;}).distance(80).strength(0.1)).force('charge',d3.forceManyBody().strength(function(d){return d.type==='root'?-500:-80;})).force('center',d3.forceCenter(width/2,height/2)).force('collision',d3.forceCollide().radius(function(d){return d.size+5;}));var link=g.append('g').selectAll('line').data(graphData.links).join('line').attr('stroke','rgba(0,245,255,.15)').attr('stroke-width',0.5);var node=g.append('g').selectAll('circle').data(graphData.nodes).join('circle').attr('r',function(d){return d.size;}).attr('fill',function(d){return colors(d.type);}).attr('stroke','#020810').attr('stroke-width',1.5).attr('cursor','pointer').call(d3.drag().on('start',function(e,d){if(!e.active)simulation.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y;}).on('drag',function(e,d){d.fx=e.x;d.fy=e.y;}).on('end',function(e,d){if(!e.active)simulation.alphaTarget(0);d.fx=null;d.fy=null;}));node.on('mouseover',function(e,d){tooltip.html('<span class="tt-url">'+esc(d.name)+'</span><span class="tt-meta">Tipo: '+d.type+'<br>Prof: '+(d.depth||0)+'<br>URLs: '+(d.url_count||0)+'</span>').style('left',(e.pageX+15)+'px').style('top',(e.pageY-30)+'px').classed('visible',true);}).on('mouseout',function(){tooltip.classed('visible',false);}).on('click',function(e,d){if(d.type!=='root'&&d.id)window.open(d.id.replace('#CLUSTER',''),'_blank');});var label=g.append('g').selectAll('text').data(graphData.nodes.filter(function(n){return n.type==='root'||n.size>=12;})).join('text').text(function(d){return d.name.length>15?d.name.substring(0,12)+'...':d.name;}).attr('font-size','9px').attr('fill','rgba(0,245,255,.8)').attr('text-anchor','middle').attr('dy',function(d){return d.size+12;}).style('pointer-events','none');simulation.on('tick',function(){link.attr('x1',function(d){return d.source.x;}).attr('y1',function(d){return d.source.y;}).attr('x2',function(d){return d.target.x;}).attr('y2',function(d){return d.target.y;});node.attr('cx',function(d){d.x=Math.max(d.size,Math.min(width-d.size,d.x));return d.x;}).attr('cy',function(d){d.y=Math.max(d.size,Math.min(height-d.size,d.y));return d.y;});label.attr('x',function(d){return d.x;}).attr('y',function(d){return d.y;});});var meta=graphData.metadata||{};document.getElementById('graphInfo').textContent=(meta.total_nodos||graphData.nodes.length)+' nodos \xb7 '+(meta.total_enlaces||graphData.links.length)+' conexiones';}
function exportarGrafoJSON(){if(!graphData)graphData=buildGraphData();if(!graphData){sb('Sin datos de grafo','warn');return;}var b=new Blob([JSON.stringify(graphData,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='grafo_'+new Date().toISOString().slice(0,10)+'.json';a.click();sb('Grafo exportado','ok');}
function resetZoom(){if(svg){svg.transition().duration(300).call(d3.zoom().transform,d3.zoomIdentity);}}

window.addEventListener('DOMContentLoaded',function(){
  fetch(BASE+'/api/health').then(function(r){return r.json();}).then(function(d){sb('Servidor v'+d.version+' conectado.','ok');}).catch(function(){sb('No se pudo conectar.','err');});
  checkSession();
  document.getElementById('uIn').addEventListener('keydown',function(e){if(e.key==='Enter')startScan();});
  tDepth();
  setInterval(function(){if(!pollTimer)checkSession();},30000);
});
</script>
<script src="https://d3js.org/d3.v7.min.js" async></script>
</body>
</html>"""


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def show_help():
    print(f"""
{C.CYAN}{C.BOLD}╔════════════════════════════════════════════════════════════════╗
║   🔗 LINK ANALYZER PRO v5.2 — AYUDA                           ║
╚════════════════════════════════════════════════════════════════╝{C.END}

{C.BOLD}USO:{C.END}
  {C.GREEN}python3 link_analyzer_v5.2.py{C.END}           → Interfaz web (modo por defecto)
  {C.GREEN}python3 link_analyzer_v5.2.py cli{C.END}       → Modo CLI en terminal
  {C.GREEN}python3 link_analyzer_v5.2.py help{C.END}      → Muestra esta ayuda

{C.BOLD}MODOS:{C.END}
  {C.CYAN}[web]{C.END}  Lanza un servidor HTTP local en el puerto 5000 y abre el
         navegador automáticamente. Desde la interfaz puedes configurar
         la URL objetivo, profundidad, verificación y reanudar sesiones.

  {C.CYAN}[cli]{C.END}  Panel de métricas en tiempo real directamente en la terminal.
         Muestra velocidad (U/s), páginas, enlaces encontrados y
         código de estado HTTP de cada URL procesada.

{C.BOLD}PARÁMETROS DE CONFIGURACIÓN (interfaz web / CLI):{C.END}
  {C.YELLOW}url{C.END}           URL objetivo del crawling
  {C.YELLOW}verificar{C.END}     Verifica el código HTTP de cada enlace   (default: false)
  {C.YELLOW}recursivo{C.END}     Sigue enlaces internos recursivamente     (default: false)
  {C.YELLOW}profundidad{C.END}   Profundidad máxima del crawling           (default: 1)
  {C.YELLOW}resume{C.END}        Reanuda desde el último checkpoint        (default: false)

{C.BOLD}MEMORIA PERSISTENTE:{C.END}
  Checkpoint automático cada {C.CYAN}10 URLs{C.END} descubiertas.
  Archivo: {C.GRAY}linkanalyzer_session.json{C.END} (junto al script)
  Workspace: {C.GRAY}workspace/scans/{C.END}   y   {C.GRAY}workspace/exports/{C.END}

{C.BOLD}EXPORTACIÓN:{C.END}
  {C.GREEN}JSON{C.END}   Metadatos completos de la sesión
  {C.GREEN}TXT{C.END}    Lista de URLs para procesamiento externo
  {C.GREEN}PDF{C.END}    Reporte imprimible generado desde el navegador

{C.BOLD}REQUISITOS:{C.END}
  pip install requests beautifulsoup4 urllib3 {C.GRAY}[--break-system-packages]{C.END}

{C.BOLD}RENDIMIENTO COMPROBADO:{C.END}
  {C.MAGENTA}>{C.END} 1,100,000 enlaces procesados en sesión única
  {C.MAGENTA}>{C.END} 8,700 páginas rastreadas sin interrupción
  {C.MAGENTA}>{C.END} 23 URLs/segundo en Termux/Android

{C.BOLD}AUTOR:{C.END}
  Yoandis Rodríguez · {C.BLUE}github.com/YoandisR{C.END} · curvadigital0@gmail.com
""")


if __name__ == '__main__':
    args = [a.lower() for a in sys.argv[1:]]
    if 'help' in args or '--help' in args or '-h' in args:
        show_help()
    elif 'cli' in args:
        modo_cli()
    else:
        launch_ui(port=5000)
