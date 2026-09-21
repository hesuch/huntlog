"""Small local sprite cache backed by the public PXG MediaWiki API."""
from pathlib import Path
from urllib.parse import urlencode, urlparse, unquote
from urllib.request import Request, urlopen
import hashlib
import json
import re
import threading
import time
import unicodedata

API = 'https://wiki.pokexgames.com/api.php'
HEADERS = {'User-Agent': 'Huntlog/0.4 (personal PXG hunt tracker)'}
TYPES = {'.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
FILE_ALIASES = {'fortuneelixir': 'Fortune.png', 'solidicecube': 'SolidIce.png',
                'goldensudowoodo': 'ShiSudowoodo.gif', 'premierball': 'Premier-ball(1).png'}


def key(name):
    return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower())


def wiki_query(params):
    with urlopen(Request(API + '?' + urlencode({'format': 'json', **params}), headers=HEADERS), timeout=8) as response:
        return json.load(response)


class WikiSprites:
    def __init__(self, bundled, cache):
        self.bundled, self.cache = Path(bundled), Path(cache)
        self.seed = self._read(self.bundled / 'catalog.json')
        self.catalog = self._read(self.cache / 'catalog.json')
        self.references = self._read(self.bundled.parent / 'sprite-references.json')
        self.lock = threading.RLock()
        self.locks = {}
        self.network = threading.BoundedSemaphore(3)

    @staticmethod
    def _read(path):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _cached(self, name):
        for catalog, folder in ((self.seed, self.bundled), (self.catalog, self.cache)):
            entry = catalog.get(name, {})
            filename = entry.get('file', '')
            if re.fullmatch(r'[a-f0-9]{20}\.(png|gif|webp)', filename):
                path = folder / filename
                if path.is_file():
                    return path
        return None

    def _remember(self, name, entry):
        with self.lock:
            self.catalog[name] = entry
            self.cache.mkdir(parents=True, exist_ok=True)
            temp = self.cache / 'catalog.tmp'
            temp.write_text(json.dumps(self.catalog, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(self.cache / 'catalog.json')

    @staticmethod
    def _info(titles):
        result = wiki_query({'action': 'query', 'titles': '|'.join(titles[:50]),
                             'prop': 'imageinfo', 'iiprop': 'url|size'})
        return [p for p in result.get('query', {}).get('pages', {}).values() if 'imageinfo' in p]

    def _discover(self, name):
        # Empty balls use the corresponding ball icon, not a separate empty-ball page.
        lookup_name = name[6:] if name.lower().startswith('empty ') and name.lower().endswith(' ball') else name
        normalized = key(lookup_name)
        reference = self.references.get(normalized)
        alias = FILE_ALIASES.get(normalized)
        if normalized == 'nightmaretyranitar':
            reference = self.references.get('tyranitar')
        if reference:
            alias = unquote(urlparse(reference['url']).path.rsplit('/', 1)[-1]).replace('_', ' ')
        if alias:
            files = self._info(['File:' + alias])
            if files:
                return files[0]
        name = lookup_name
        forms = list(dict.fromkeys([name[:1].upper() + name[1:], name.title(),
                                    name.title().replace(' ', ''), name.title().replace(' ', '-')]))
        files = self._info(['File:' + form + ext for form in forms for ext in TYPES])
        if not files:
            # Match only this name's image; never pick unrelated images from a page.
            result = wiki_query({'action': 'query', 'titles': name + '|' + name.title(), 'prop': 'images', 'imlimit': 'max', 'redirects': 1})
            titles = []
            for page in result.get('query', {}).get('pages', {}).values():
                for image in page.get('images', []):
                    stem = image['title'].split(':', 1)[-1].rsplit('.', 1)[0]
                    stem = re.sub(r'^\d+[ -]*', '', stem)
                    stem = re.sub(r'^Sh[ -]+', 'Shiny ', stem, flags=re.I)
                    if key(stem) == key(name):
                        titles.append(image['title'])
            files = self._info(titles) if titles else []
        candidates = [p for p in files if 0 < p['imageinfo'][0].get('width', 0) <= 256
                      and 0 < p['imageinfo'][0].get('height', 0) <= 256
                      and p['imageinfo'][0].get('size', 3_000_000) <= 2_000_000
                      and Path(urlparse(p['imageinfo'][0]['url']).path).suffix.lower() in TYPES]
        candidates.sort(key=lambda p: (not p['title'].lower().endswith('.png'), p['imageinfo'][0]['size']))
        return candidates[0] if candidates else None

    def get(self, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            return None
        name = name.strip()
        normalized = key(name)
        with self.lock:
            cached = self._cached(normalized)
            if cached:
                return cached
            if self.catalog.get(normalized, {}).get('retry_after', 0) > time.time():
                return None
            guard = self.locks.setdefault(normalized, threading.Lock())
        with guard:
            with self.lock:
                cached = self._cached(normalized)
                if cached:
                    return cached
                if self.catalog.get(normalized, {}).get('retry_after', 0) > time.time():
                    return None
            try:
                with self.network:
                    page = self._discover(name)
                    if not page:
                        self._remember(normalized, {'name': name, 'retry_after': time.time() + 3600, 'reason': 'not_found'})
                        return None
                    info = page['imageinfo'][0]
                    url = info['url'].replace('http://', 'https://', 1)
                    if urlparse(url).hostname != 'wiki.pokexgames.com' or urlparse(url).scheme != 'https':
                        raise ValueError('Unexpected image host')
                    suffix = Path(urlparse(url).path).suffix.lower()
                    with urlopen(Request(url, headers=HEADERS), timeout=10) as response:
                        data = response.read(2_000_001)
                        if response.headers.get_content_type() != TYPES[suffix] or len(data) > 2_000_000:
                            raise ValueError('Unexpected image format')
                    valid = (suffix == '.png' and data.startswith(b'\x89PNG\r\n\x1a\n') or
                             suffix == '.gif' and data[:6] in (b'GIF87a', b'GIF89a') or
                             suffix == '.webp' and data[:4] == b'RIFF' and data[8:12] == b'WEBP')
                    if not valid:
                        raise ValueError('Invalid image content')
                    filename = hashlib.sha256(url.encode()).hexdigest()[:20] + suffix
                    self.cache.mkdir(parents=True, exist_ok=True)
                    target = self.cache / filename
                    target.write_bytes(data)
                    self._remember(normalized, {'name': name, 'file': filename, 'source': url,
                                               'page': info.get('descriptionurl', '').replace('http://', 'https://', 1)})
                    return target
            except (OSError, ValueError, KeyError, TypeError) as exc:
                # Network failures must never interrupt importing or reading a hunt.
                try:
                    self._remember(normalized, {'name': name, 'retry_after': time.time() + 60, 'reason': 'download_failed', 'error': str(exc)[:200]})
                except OSError:
                    pass
                return None
