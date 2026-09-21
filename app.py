"""PXG Hunt Tracker — aplicação local, sem dependências externas."""
from __future__ import annotations

import base64
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import threading
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen
import webbrowser
from wiki_assets import WikiSprites, TYPES as IMAGE_TYPES, key as pokemon_key, canonical_pokemon_name

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "hunts.sqlite3"
APP_VERSION = "0.6.4-desktop"
TERROR_IMAGES = json.loads((ROOT / "static" / "terror-images.json").read_text(encoding="utf-8"))
DUNGEONS = json.loads((ROOT / "static" / "dungeons.json").read_text(encoding="utf-8"))
DUNGEON_IMAGES = json.loads((ROOT / "static" / "dungeon-images.json").read_text(encoding="utf-8"))
NIGHTMARE_HUNTS = json.loads((ROOT / "static" / "nightmare-hunts.json").read_text(encoding="utf-8"))
BOSS_CATALOG = json.loads((ROOT / "static" / "bosses.json").read_text(encoding="utf-8"))
def boss_key(name):
    return pokemon_key(name) or name.strip().casefold()
BOSS_RULES = {
    'terror': [boss_key(n) for n in BOSS_CATALOG['terror']],
    'unique': [boss_key(n) for n in BOSS_CATALOG['unique_dungeon_bosses']],
    'dungeons': {boss_key(k): [boss_key(n) for n in v] for k, v in BOSS_CATALOG['dungeons'].items()},
}



BOSS_IMAGES = json.loads((ROOT / 'static/boss-images.json').read_text(encoding='utf-8'))
BOSS_RULES['images'] = BOSS_IMAGES

def boss_image(name, category):
    normalized = boss_key(name)
    if normalized in ('entei', 'raikou', 'suicune') and category not in ('terror', 'mixed'):
        return ''
    return BOSS_IMAGES.get(normalized, '')

DUNGEON_BOSS_IMAGES = {alias: DUNGEON_IMAGES[location] for location, aliases in BOSS_RULES['dungeons'].items()
                       if location in DUNGEON_IMAGES for alias in aliases if alias in BOSS_RULES['unique']}
BOSS_RULES['dungeon_images'] = DUNGEON_BOSS_IMAGES

def battle_image(name, category):
    return boss_image(name, category) or DUNGEON_BOSS_IMAGES.get(boss_key(name), '')

def battle_group(enemy, record):
    name = boss_key(enemy['name'])
    if boss_image(enemy['name'], record['category']):
        return 'boss'
    if name in BOSS_RULES['unique'] or (record['category'] == 'mystery_dungeon' and
            name in allowed_bosses('mystery_dungeon', record['location'])):
        return 'dungeon'
    return 'pokemon'


def counted_enemy(enemy):
    return enemy['included'] and enemy.get('counted', True) and enemy['count'] > 0


def allowed_bosses(category, location):
    if category == 'terror':
        return BOSS_RULES['terror']
    return BOSS_RULES['dungeons'].get(boss_key(location), BOSS_RULES['unique'])
NORMAL_ENCOUNTERS = {pokemon_key(name) for name in (
    "Mega Falinkz", "Mega Falinks", "Mega Sharpedo", "Mega Baxcalibur",
    "Mega Glimmora", "Mega Scovillain", "Mega Raichu X", "Mega Chimecho",
)}


POKEMON_TIERS = {pokemon_key(name): tier for name, tier in json.loads(
    (ROOT / "static" / "pokemon-tiers.json").read_text(encoding="utf-8"))["tiers"].items()}
NORMAL_ENCOUNTERS |= {name for name, tier in POKEMON_TIERS.items() if tier in ("2", "3")}


def is_rare_encounter(name, reported):
    normalized = pokemon_key(canonical_pokemon_name(name))
    return normalized not in NORMAL_ENCOUNTERS and (reported is True or normalized == "nightmarecrystal")


def nightmare_hunt(name):
    normalized = pokemon_key(name)
    matches = [hunt for hunt in NIGHTMARE_HUNTS
               if normalized in {pokemon_key(alias) for alias in hunt['aliases']}]
    return matches[0] if len(matches) == 1 else None


def location_suggestions(enemies):
    totals = {}
    names = {}
    for enemy in enemies or []:
        if enemy["included"] and enemy["count"] > 0:
            key = pokemon_key(enemy["name"])
            totals[key] = totals.get(key, 0) + enemy["count"]
            names.setdefault(key, enemy["name"])
    highest = max(totals.values(), default=0)
    leaders = [names[k] for k, count in totals.items() if count == highest]
    hunt = leaders[0] if len(leaders) == 1 else ""
    known = nightmare_hunt(hunt)
    if known:
        hunt = known['name']
    matches = {name for name in DUNGEONS if pokemon_key(name) in totals}
    if "gianttyranitar" in totals:
        matches.add("The Darkness")
    dungeon = next(iter(matches)) if len(matches) == 1 else ""
    return {"hunt": hunt, "terror": "Terror", "mystery_dungeon": dungeon, "mixed": "Mista"}


POKEMON_NAMES = {pokemon_key(name) for name in json.loads(
    (ROOT / "static" / "pokemon-names.json").read_text(encoding="utf-8"))}


def number(value, field, integer=False, negative=False):
    try:
        if isinstance(value, bool):
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite() or (not negative and result < 0) or abs(result) > 10**14:
            raise ValueError()
        if integer and result != result.to_integral_value():
            raise ValueError()
        return int(result) if integer else float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError(f"{field}: informe um número válido" + (" e não negativo." if not negative else "."))


def money_sum(values):
    return float(sum((Decimal(str(v)) for v in values), Decimal(0)).quantize(Decimal("0.01")))


def label(value, maximum=200):
    if value is None:
        return ""
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError("Texto inválido no resumo.")
    return str(value).strip()[:maximum]



def adjust_ghost_helpers(enemies, items):
    """Keep original counts so reads, edits and backup restores are idempotent."""
    if not any(pokemon_key(e['name']) == 'bossgiantghost' and e['included'] and e['count'] > 0 for e in enemies):
        return None
    costs = {'normal': 1, 'hard': 2, 'expert': 4}
    difficulties = {difficulty for difficulty in costs if any(
        i['kind'] == 'drop' and i['included'] and i['count'] > 0 and
        pokemon_key(i['name']) == 'ghostlylootbag' + difficulty for i in items)}
    if len(difficulties) != 1:
        return None
    difficulty = next(iter(difficulties))
    tags = sum(i['count'] for i in items if i['kind'] == 'supply' and i['included'] and
               pokemon_key(i['name']) in ('spelltag', 'spelltags'))
    if not tags or tags % costs[difficulty]:
        return None
    attempts = tags // costs[difficulty]
    remaining = {name: count * attempts for name, count in
                 {'gastly': 4, 'haunter': 2, 'gengar': 1, 'shinygengar': 1}.items()}
    removed = 0
    for enemy in enemies:
        name = pokemon_key(enemy['name'])
        if enemy['included'] and name in remaining:
            discount = min(enemy['count'], remaining[name])
            enemy['count'] -= discount
            enemy['ghost_excluded'] = discount
            remaining[name] -= discount
            removed += discount
    return {'difficulty': difficulty, 'attempts': attempts, 'spell_tags': tags, 'excluded': removed}


def normalize_record(candidate):
    """Store only selected session, item and defeated-Pokémon fields."""
    if not isinstance(candidate, dict):
        raise ValueError("O registro deve ser um objeto JSON.")
    category = candidate.get("category", "hunt")
    if category not in ("hunt", "terror", "mystery_dungeon", "mixed"):
        raise ValueError("Escolha Hunt, Terror, Mystery Dungeon ou Mista.")
    started = label(candidate.get("started"))
    try:
        parsed = datetime.fromisoformat(started)
        started = parsed.isoformat(sep=" ", timespec="seconds")
    except ValueError:
        raise ValueError("A sessão precisa de uma data de início válida.")
    duration = number(candidate.get("duration", 0), "Duração", integer=True)
    if duration <= 0:
        raise ValueError("A duração da hunt precisa ser maior que zero.")
    player = label(candidate.get("player"))
    if not player:
        raise ValueError("Informe o personagem desta hunt.")
    session_id = label(candidate.get("session_id"))
    if not session_id:
        raise ValueError("O JSON precisa conter Session ID.")
    entries = candidate.get("items", [])
    if not isinstance(entries, list):
        raise ValueError("A lista de itens é inválida.")
    items = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("kind") not in ("drop", "supply"):
            raise ValueError("Item inválido na lista.")
        name = label(entry.get("name"))
        if not name:
            raise ValueError("Existe um item sem nome.")
        count = number(entry.get("count"), f"Quantidade de {name}", integer=True)
        price = number(entry.get("price"), f"Preço de {name}")
        items.append({"kind": entry["kind"], "name": name, "count": count,
                      "price": price, "included": entry.get("included") is not False,
                      "reported_price": None if entry.get("reported_price") is None else
                                        number(entry["reported_price"], f"Preço original de {name}"),
                      "price_source": entry.get("price_source") if entry.get("price_source") in
                                      ("report", "table", "manual", "snapshot") else "report",
                      "total": number(Decimal(str(price)) * count, f"Total de {name}")})
    enemies = candidate.get("enemies")
    if enemies is not None:
        if not isinstance(enemies, list):
            raise ValueError("A lista de Pokémon derrotados é inválida.")
        cleaned = []
        for enemy in enemies:
            if not isinstance(enemy, dict) or not label(enemy.get("name")):
                raise ValueError("Existe um Pokémon derrotado sem nome válido.")
            cleaned.append({"name": canonical_pokemon_name(label(enemy["name"])),
                            "count": number(enemy.get("reported_count", enemy.get("count")), "Pokémon derrotados", integer=True),
                            "reported_count": number(enemy.get("reported_count", enemy.get("count")), "Pokémon derrotados", integer=True),
                            "rare": is_rare_encounter(enemy["name"], enemy.get("rare")),
                            "included": enemy.get("included") is not False})
        enemies = cleaned
    ghost_adjustment = adjust_ghost_helpers(enemies or [], items)
    pokemon_names = POKEMON_NAMES | {pokemon_key(e["name"]) for e in enemies or []}
    pokemon_names |= {name.removeprefix("nightmare") for name in pokemon_names}
    for item in items:
        item["is_capture"] = item["kind"] == "drop" and pokemon_key(item["name"]) in pokemon_names
    capture_count = sum(i["count"] for i in items if i["is_capture"] and i["included"])
    suggested_location = location_suggestions(enemies)[category]
    boss_location = label(candidate.get('location')) or suggested_location
    allowed = allowed_bosses(category, boss_location)
    for enemy in enemies or []:
        enemy['image_name'] = battle_image(enemy['name'], category)
        enemy['counted'] = category in ('hunt', 'mixed') or boss_key(enemy['name']) in allowed or (category == 'terror' and bool(boss_image(enemy['name'], category)))
    kills = None if enemies is None else sum(e["count"] for e in enemies if counted_enemy(e))
    rare_kills = None if enemies is None else sum(e["count"] for e in enemies if counted_enemy(e) and e["rare"])
    raw = money_sum(i["total"] for i in items if i["kind"] == "drop" and i["included"])
    supplies = money_sum(i["total"] for i in items if i["kind"] == "supply" and i["included"])
    extras = number(candidate.get("extras", 0), "Gastos extras")
    profit = money_sum([raw, -supplies, -extras])
    identity = json.dumps([player.casefold(), started, session_id], ensure_ascii=False)
    suggestions = location_suggestions(enemies)
    location = label(candidate.get("location"))
    location_source = "manual" if location and candidate.get("location_source") != "auto" else "auto"
    if location_source == "auto":
        location = suggestions[category]
    if category == "terror":
        location, location_source = "Terror", "auto"
    record = {
        "terror_image": TERROR_IMAGES[int(hashlib.sha256(identity.encode()).hexdigest(), 16) % len(TERROR_IMAGES)] if category == "terror" else "",
        "id": hashlib.sha256(identity.encode()).hexdigest()[:24],
        "session_id": session_id, "started": started, "date": started[:10],
        "status": label(candidate.get("status"), 80),
        "player": player, "duration": duration, "category": category,
        "location": location, "location_source": location_source,
        "dungeon_image": (DUNGEON_IMAGES.get(pokemon_key(location)) or
                          DUNGEON_IMAGES.get(pokemon_key(suggestions["mystery_dungeon"]), ""))
                         if category == "mystery_dungeon" else "",
        "hunt_image": (nightmare_hunt(location) or {}).get("image", "") if category == "hunt" else "",
        "location_suggestions": suggestions, "dungeon_options": DUNGEONS,
        "hunt_options": [hunt['name'] for hunt in NIGHTMARE_HUNTS],
        "server": label(candidate.get("server")),
        "pokemon": label(candidate.get("pokemon")), "notes": label(candidate.get("notes"), 2000),
        "extras": extras, "items": items, "raw": raw, "supplies": supplies,
        "ghost_adjustment": ghost_adjustment,
        "enemies": enemies, "kills": kills, "rare_kills": rare_kills, "capture_count": capture_count,
        "boss_rules": BOSS_RULES,
        "kills_per_hour": kills * 3600 / duration if kills is not None else None,
        "profit": profit, "hourly": profit * 3600 / duration,
        "zero_prices": sum(1 for i in items if i["included"] and i["price"] == 0 and i["count"] > 0),
    }
    for field in ("reported_profit", "reported_raw", "reported_supplies"):
        value = candidate.get(field)
        record[field] = None if value is None else number(value, field, negative=field == "reported_profit")
    return record


def parse_report(report):
    if isinstance(report, str):
        try:
            report = json.loads(report.lstrip("\ufeff"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido na linha {exc.lineno}. Confira o conteúdo colado.")
    if not isinstance(report, dict) or not isinstance(report.get("Session"), dict):
        raise ValueError("Não encontrei a seção Session. Cole o resumo completo da hunt.")
    session = report["Session"]
    items, players = [], set()
    for key, kind in (("Drops", "drop"), ("Supplies", "supply")):
        rows = report.get(key, [])
        if not isinstance(rows, list):
            raise ValueError(f"A seção {key} deve ser uma lista.")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"Existe um item inválido em {key}.")
            player = label(row.get("Player"))
            if player:
                players.add(player)
            items.append({"kind": kind, "name": row.get("Item"), "count": row.get("Count"),
                          "price": row.get("Unit price", 0), "reported_price": row.get("Unit price", 0),
                          "included": row.get("Ignored") is not True})
    enemies = None
    if "Enemies Defeated" in report:
        rows = report["Enemies Defeated"]
        if not isinstance(rows, list):
            raise ValueError("A seção Enemies Defeated deve ser uma lista.")
        enemies = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Existe um Pokémon inválido em Enemies Defeated.")
            player = label(row.get("Player"))
            if player:
                players.add(player)
            enemies.append({"name": row.get("Enemy"), "count": row.get("Count"),
                            "rare": row.get("Rare") is True, "included": row.get("Ignored") is not True})
    if len(players) > 1:
        raise ValueError("Esta primeira versão aceita hunts de um personagem por resumo.")
    return normalize_record({
        "session_id": session.get("Session ID"), "started": session.get("Start"),
        "status": session.get("Status"),
        "player": next(iter(players), label(session.get("Player")) or "Meu personagem"),
        "duration": session.get("Duration seconds"), "items": items, "enemies": enemies,
        "reported_profit": session.get("Profit"), "reported_raw": session.get("Raw gains"),
        "reported_supplies": session.get("Supplies"),
    })


def profit_comparison(records):
    known = [r for r in records if r.get("reported_profit") is not None]
    reported = money_sum(r["reported_profit"] for r in known)
    adjusted = money_sum(r["profit"] for r in known)
    extras = money_sum(r["extras"] for r in known)
    return {"count": len(known), "missing": len(records) - len(known),
            "reported": reported if known else None, "adjusted": adjusted if known else None,
            "delta": money_sum([adjusted, -reported]) if known else None,
            "item_adjustment": money_sum([adjusted, extras, -reported]) if known else None,
            "extras": extras}


def weekly_summary(records, weeks_ago=1, now=None):
    # The game's reset is fixed to Brasilia (UTC-3), independent of the PC timezone.
    brasilia = timezone(timedelta(hours=-3))
    now = now or datetime.now(brasilia)
    now = now.replace(tzinfo=brasilia) if now.tzinfo is None else now.astimezone(brasilia)
    reset = (now - timedelta(days=now.weekday())).replace(hour=7, minute=45, second=0, microsecond=0)
    if now < reset:
        reset -= timedelta(days=7)
    start = reset - timedelta(weeks=weeks_ago)
    end = start + timedelta(days=7)
    selected = []
    for record in records:
        moment = datetime.fromisoformat(record['started'])
        moment = moment.replace(tzinfo=brasilia) if moment.tzinfo is None else moment.astimezone(brasilia)
        if start <= moment < end:
            selected.append(record)
    stats = statistics(selected)
    contents, defeated, rare, captures = {}, {}, {}, {}
    def add(target, name, count):
        if count > 0:
            row = target.setdefault(pokemon_key(name), {'name': name, 'count': 0})
            row['count'] += count
    for record in selected:
        category = record.get('category', 'hunt')
        name = record['location'] or 'Local não informado'
        row = contents.setdefault((category, name.casefold()), {'name': name, 'category': category, 'profit': 0, 'duration': 0, 'count': 0})
        row['profit'] = money_sum([row['profit'], record['profit']])
        row['duration'] += record['duration']
        row['count'] += 1
        for enemy in record.get('enemies') or []:
            if counted_enemy(enemy):
                add(defeated, enemy['name'], enemy['count'])
                if enemy['rare']:
                    add(rare, enemy['name'], enemy['count'])
        for item in record['items']:
            if item['included'] and item.get('is_capture'):
                add(captures, item['name'], item['count'])
    order = lambda rows: sorted(rows.values(), key=lambda r: (-r['count'], r['name']))
    ranking = sorted(contents.values(), key=lambda r: (-r['profit'], r['name']))
    return {'start': start.isoformat(), 'end': end.isoformat(), 'weeks_ago': weeks_ago,
            'stats': stats, 'contents': ranking, 'defeated': order(defeated),
            'rares': order(rare), 'captures': order(captures)}


def statistics(records):
    profit = money_sum(r["profit"] for r in records)
    duration = sum(r["duration"] for r in records)
    daily = {}
    for record in records:
        day = daily.setdefault(record["date"], {"date": record["date"], "profit": 0, "duration": 0, "count": 0})
        day["profit"] = money_sum([day["profit"], record["profit"]])
        day["duration"] += record["duration"]
        day["count"] += 1
    tracked = [r for r in records if r.get("enemies") is not None]
    tracked_seconds = sum(r["duration"] for r in tracked)
    defeated = {}
    for record in tracked:
        for enemy in record["enemies"]:
            if counted_enemy(enemy):
                division = battle_group(enemy, record)
                group = defeated.setdefault((enemy["name"], division), {"name": enemy["name"], "battle_group": division, "image_name": battle_image(enemy["name"], record["category"]), "count": 0, "rare_count": 0})
                group["count"] += enemy["count"]
                group["rare_count"] += enemy["count"] if enemy["rare"] else 0
    kills = sum(e["count"] for e in defeated.values())
    return {"count": len(records), "profit": profit, "duration": duration,
            "comparison": profit_comparison(records),
            "capture_count": sum(r.get("capture_count", 0) for r in records),
            "raw": money_sum(r["raw"] for r in records),
            "cost": money_sum(r["supplies"] + r["extras"] for r in records),
            "hourly": profit * 3600 / duration if duration else 0,
            "active_days": len(daily), "daily_average": profit / len(daily) if daily else 0,
            "zero_prices": sum(r["zero_prices"] for r in records),
            "kills": kills if tracked else None,
            "rare_kills": sum(e["rare_count"] for e in defeated.values()) if tracked else None,
            "kills_per_hour": kills * 3600 / tracked_seconds if tracked_seconds else None,
            "tracked_hunts": len(tracked),
            "defeated": sorted(defeated.values(), key=lambda e: (-e["count"], e["name"])),
            "daily": sorted(daily.values(), key=lambda d: d["date"])}


def validate_image(value):
    if not isinstance(value, str):
        raise ValueError("Imagem inválida.")
    if value.startswith("data:"):
        try:
            header, encoded = value.split(",", 1)
            raw = base64.b64decode(encoded, validate=True)
        except Exception:
            raise ValueError("Arquivo de imagem inválido.")
        valid = ((header == "data:image/png;base64" and raw.startswith(b"\x89PNG\r\n\x1a\n")) or
                 (header == "data:image/gif;base64" and raw[:6] in (b"GIF87a", b"GIF89a")) or
                 (header == "data:image/jpeg;base64" and raw.startswith(b"\xff\xd8\xff")) or
                 (header == "data:image/webp;base64" and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"))
        if not valid or len(raw)>2_000_000:
            raise ValueError("Use PNG, JPG, GIF ou WebP de até 2 MB.")
    elif value:
        url = urlparse(value)
        if url.scheme not in ("https", "http") or not url.hostname or url.username or len(value)>4000:
            raise ValueError("Use um link direto HTTP ou HTTPS para a imagem.")
    return value


class Store:
    def profile(self):
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE name='profile'").fetchone()
        return json.loads(row[0]) if row else {"name": "Meu diário", "characters": [], "image": ""}

    def save_profile(self, value):
        name = label(value.get("name"), 80)
        if not name:
            raise ValueError("Informe o nome do perfil.")
        characters = value.get("characters", [])
        if not isinstance(characters, list) or len(characters) > 500 or any(not isinstance(n, str) for n in characters):
            raise ValueError("Informe até 500 personagens.")
        unique = {}
        for character in characters:
            character = label(character, 80)
            if character:
                unique.setdefault(character.casefold(), character)
        profile = {"name": name, "characters": list(unique.values()), "image": validate_image(value.get("image", ""))}
        with self.connect() as connection:
            connection.execute("INSERT INTO settings VALUES ('profile', ?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (json.dumps(profile, ensure_ascii=False),))
        return profile

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS custom_images (name TEXT PRIMARY KEY, image TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS hunts (
                    id TEXT PRIMARY KEY, started TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prices (
                    kind TEXT NOT NULL, name TEXT NOT NULL, price REAL NOT NULL,
                    PRIMARY KEY (kind, name)
                );
            """)
            columns = {r[1] for r in connection.execute("PRAGMA table_info(prices)")}
            if "custom" not in columns:
                connection.execute("ALTER TABLE prices ADD COLUMN custom INTEGER NOT NULL DEFAULT 0")
                first_prices = {}
                for row in connection.execute("SELECT data FROM hunts ORDER BY rowid"):
                    for item in json.loads(row[0])["items"]:
                        first_prices.setdefault((item["kind"], item["name"]), item["price"])
                # Preserve any user-edited prices from the first application version.
                for kind, name, price in connection.execute("SELECT kind, name, price FROM prices").fetchall():
                    if (kind, name) not in first_prices or price != first_prices[(kind, name)]:
                        connection.execute("UPDATE prices SET custom=1 WHERE kind=? AND name=?", (kind, name))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def all(self):
        with self.connect() as connection:
            return [normalize_record(json.loads(row[0])) for row in connection.execute("SELECT data FROM hunts ORDER BY started DESC")]

    def get(self, key):
        with self.connect() as connection:
            row = connection.execute("SELECT data FROM hunts WHERE id=?", (key,)).fetchone()
        return normalize_record(json.loads(row[0])) if row else None

    def preview(self, report):
        record = parse_report(report)
        existing = self.get(record["id"])
        if existing:
            record["status"] = record["status"] or existing["status"]
            for field in ("location", "location_source", "server", "pokemon", "notes", "extras", "category"):
                record[field] = existing[field]
            if record["enemies"] is None:
                record["enemies"] = existing["enemies"]
            snapshots = {(i["kind"], i["name"]): i for i in existing["items"]}
            for item in record["items"]:
                saved = snapshots.get((item["kind"], item["name"]))
                if saved:
                    item.update(price=saved["price"], included=saved["included"], price_source="snapshot")
        else:
            self.apply_custom_prices(record, self.prices())
        return {"record": normalize_record(record), "exists": bool(existing),
                "previous": {key: existing[key] for key in ("duration", "kills", "profit", "status")}
                            if existing else None}

    @staticmethod
    def apply_custom_prices(record, prices):
        custom = {(p["kind"], p["name"]): p["price"] for p in prices if p["custom"]}
        for item in record["items"]:
            key = (item["kind"], item["name"])
            if key in custom and item["price_source"] != "manual":
                item.update(price=custom[key], price_source="table")

    def save(self, candidate, replace=False):
        record = normalize_record(candidate)
        with self.connect() as connection:
            exists = connection.execute("SELECT id FROM hunts WHERE id=?", (record["id"],)).fetchone()
            if exists and not replace:
                raise FileExistsError("Essa sessão já está no histórico. Abra o registro existente ou escolha atualizar.")
            if not exists:
                prices = [{"kind": r[0], "name": r[1], "price": r[2], "custom": bool(r[3])} for r in
                          connection.execute("SELECT kind, name, price, custom FROM prices")]
                self.apply_custom_prices(record, prices)
                record = normalize_record(record)
            serialized = json.dumps(record, ensure_ascii=False, allow_nan=False)
            connection.execute("INSERT INTO hunts VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET started=excluded.started, data=excluded.data",
                               (record["id"], record["started"], serialized))
            for item in record["items"]:
                connection.execute("INSERT OR IGNORE INTO prices (kind, name, price) VALUES (?, ?, ?)",
                                   (item["kind"], item["name"], item["price"]))
        return record

    def delete(self, key):
        with self.connect() as connection:
            connection.execute("DELETE FROM hunts WHERE id=?", (key,))

    def prices(self):
        with self.connect() as connection:
            return [{"kind": r[0], "name": r[1], "price": r[2], "custom": bool(r[3])} for r in
                    connection.execute("SELECT kind, name, price, custom FROM prices ORDER BY kind, name COLLATE NOCASE")]

    def save_prices(self, rows, scope="future"):
        if scope not in ("future", "history"):
            raise ValueError("Escolha se os preços valem para o futuro ou também para o histórico.")
        if not isinstance(rows, list):
            raise ValueError("Tabela de preços inválida.")
        cleaned = []
        for row in rows:
            if not isinstance(row, dict) or row.get("kind") not in ("drop", "supply") or not label(row.get("name")):
                raise ValueError("Item inválido na tabela de preços.")
            cleaned.append((row["kind"], label(row["name"]), number(row.get("price"), "Preço")))
        with self.connect() as connection:
            previous = {(r[0], r[1]): r[2] for r in connection.execute("SELECT kind,name,price FROM prices")}
            changed = {(kind, name): price for kind, name, price in cleaned
                       if previous.get((kind, name)) != price}
            updated = 0
            if scope == "history" and changed:
                for row in connection.execute("SELECT id,data FROM hunts").fetchall():
                    record = json.loads(row[1])
                    touched = False
                    for item in record["items"]:
                        key = (item["kind"], item["name"])
                        if key in changed and item["price"] != changed[key]:
                            item.update(price=changed[key], price_source="table")
                            touched = True
                    if touched:
                        record = normalize_record(record)
                        connection.execute("UPDATE hunts SET data=? WHERE id=?", (json.dumps(record, ensure_ascii=False), row[0]))
                        updated += 1
            connection.executemany("""INSERT INTO prices (kind, name, price, custom) VALUES (?, ?, ?, 1)
                ON CONFLICT(kind,name) DO UPDATE SET price=excluded.price,
                custom=CASE WHEN prices.price != excluded.price THEN 1 ELSE prices.custom END""", cleaned)
        return {"ok": True, "updated_hunts": updated}

    @staticmethod
    def backup_payload(connection):
        return {"format": "huntlog-backup", "version": 1, "app_version": APP_VERSION,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "hunts": [normalize_record(json.loads(r[0])) for r in
                          connection.execute("SELECT data FROM hunts ORDER BY started DESC")],
                "prices": [{"kind": r[0], "name": r[1], "price": r[2], "custom": bool(r[3])}
                           for r in connection.execute("SELECT kind, name, price, custom FROM prices ORDER BY kind,name COLLATE NOCASE")]}

    def backup(self):
        with self.connect() as connection:
            connection.execute("BEGIN")
            return self.backup_payload(connection)

    @staticmethod
    def validate_backup(payload):
        if not isinstance(payload, dict) or payload.get("format") != "huntlog-backup":
            raise ValueError("Selecione um backup do Huntlog. O resumo de uma hunt deve ser importado em Registrar hunt.")
        if type(payload.get("version")) is not int or payload["version"] != 1:
            raise ValueError("Versão de backup não suportada por este aplicativo.")
        if not isinstance(payload.get("hunts"), list) or not isinstance(payload.get("prices"), list):
            raise ValueError("O backup precisa conter o histórico e a tabela de preços.")
        required = {"session_id", "started", "player", "duration", "items", "enemies", "extras",
                    "reported_profit", "reported_raw", "reported_supplies"}
        for row in payload["hunts"]:
            if not isinstance(row, dict) or not required.issubset(row) or not isinstance(row["items"], list):
                raise ValueError("O backup contém uma hunt incompleta. Nenhum dado foi alterado.")
            for item in row["items"]:
                if not isinstance(item, dict) or not isinstance(item.get("included"), bool):
                    raise ValueError("O backup contém um item incompleto ou inválido.")
                if item.get("price_source") not in ("report", "table", "manual", "snapshot"):
                    raise ValueError("O backup contém uma origem de preço inválida.")
        hunts = [normalize_record(row) for row in payload["hunts"]]
        if len({h["id"] for h in hunts}) != len(hunts):
            raise ValueError("O backup contém sessões repetidas. Nenhum dado foi alterado.")
        prices, keys = [], set()
        for row in payload["prices"]:
            if not isinstance(row, dict) or row.get("kind") not in ("drop", "supply") or not label(row.get("name")):
                raise ValueError("Item inválido na tabela de preços do backup.")
            if not isinstance(row.get("custom"), bool):
                raise ValueError("O backup contém uma configuração de preço inválida.")
            key = (row["kind"], label(row["name"]))
            if key in keys:
                raise ValueError("O backup contém preços repetidos.")
            keys.add(key)
            prices.append({"kind": key[0], "name": key[1], "price": number(row.get("price"), "Preço do backup"),
                           "custom": row["custom"]})
        return {"hunts": hunts, "prices": prices, "created_at": label(payload.get("created_at"), 80)}

    def restore_preview(self, payload):
        backup = self.validate_backup(payload)
        dates = sorted(h["date"] for h in backup["hunts"])
        return {"hunts": len(backup["hunts"]), "prices": len(backup["prices"]),
                "profit": money_sum(h["profit"] for h in backup["hunts"]),
                "created_at": backup["created_at"], "start": dates[0] if dates else None,
                "end": dates[-1] if dates else None}

    def recovery_file(self):
        return next(iter(sorted((self.path.parent / "backups").glob("before-restore-*.json"), reverse=True)), None)

    def restore(self, payload):
        backup = self.validate_backup(payload)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            recovery = self.backup_payload(connection)
            folder = self.path.parent / "backups"
            folder.mkdir(parents=True, exist_ok=True)
            filename = "before-restore-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json"
            with (folder / filename).open("x", encoding="utf-8") as file:
                json.dump(recovery, file, ensure_ascii=False, allow_nan=False, indent=2)
            connection.execute("DELETE FROM hunts")
            connection.execute("DELETE FROM prices")
            connection.executemany("INSERT INTO hunts (id,started,data) VALUES (?,?,?)", [
                (h["id"], h["started"], json.dumps(h, ensure_ascii=False, allow_nan=False)) for h in backup["hunts"]])
            connection.executemany("INSERT INTO prices (kind,name,price,custom) VALUES (?,?,?,?)", [
                (p["kind"], p["name"], p["price"], int(p["custom"])) for p in backup["prices"]])
        return {"hunts": len(backup["hunts"]), "prices": len(backup["prices"]), "recovery_available": True}


class LocalHTTPServer(ThreadingHTTPServer):
    # Windows otherwise permits two Python HTTPServer processes to share a port.
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    store: Store
    sprites = WikiSprites(ROOT / "static" / "sprites", ROOT / "data" / "sprites")

    def log_message(self, *args):
        pass

    def send_json(self, value, status=200, filename=None):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2 if filename else None).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/weekly":
            try:
                weeks = int(parse_qs(parsed.query).get('weeks_ago', ['1'])[0])
                if not 0 <= weeks <= 520:
                    raise ValueError()
            except ValueError:
                self.send_json({'error': 'Semana inválida.'}, 400)
                return
            self.send_json(weekly_summary(self.store.all(), weeks))
            return
        if parsed.path == "/api/profile":
            self.send_json(self.store.profile())
            return
        if parsed.path == "/api/status":
            self.send_json({"app": "huntlog", "version": APP_VERSION})
        elif parsed.path == "/api/images":
            with self.store.connect() as connection:
                self.send_json(dict(connection.execute("SELECT name,image FROM custom_images")))
        elif parsed.path == "/api/sprite":
            name = parse_qs(parsed.query).get("name", [""])[0]
            file = self.sprites.get(name)
            found = file is not None
            file = file or ROOT / "static" / "sprite-placeholder.svg"
            data = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", IMAGE_TYPES.get(file.suffix, "image/svg+xml"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=" + ("604800" if found else "300"))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
        elif parsed.path == "/api/hunts":
            records = self.store.all()
            query = parse_qs(parsed.query)
            start, end = query.get("start", [""])[0], query.get("end", [""])[0]
            location = query.get("location", [""])[0]
            filtered = [r for r in records if (not start or r["date"] >= start) and
                        (not end or r["date"] <= end) and (not location or r["location"] == location)]
            self.send_json({"hunts": filtered, "stats": statistics(filtered),
                            "locations": sorted(set(r["location"] for r in records if r["location"]))})
        elif parsed.path == "/api/prices":
            self.send_json([{**p, "is_capture": p["kind"] == "drop" and pokemon_key(p["name"]) in POKEMON_NAMES}
                            for p in self.store.prices()])
        elif parsed.path == "/api/backup":
            self.send_json(self.store.backup(), filename="huntlog-backup-" + datetime.now().strftime("%Y-%m-%d-%H%M%S") + ".json")
        elif parsed.path == "/api/backup/info":
            with self.store.connect() as connection:
                self.send_json({"hunts": connection.execute("SELECT COUNT(*) FROM hunts").fetchone()[0],
                                "prices": connection.execute("SELECT COUNT(*) FROM prices").fetchone()[0],
                                "recovery_available": self.store.recovery_file() is not None})
        elif parsed.path == "/api/backup/recovery":
            file = self.store.recovery_file()
            if file:
                self.send_json(json.loads(file.read_text(encoding="utf-8")), filename="huntlog-antes-da-restauracao.json")
            else:
                self.send_json({"error": "Ainda não há uma cópia de recuperação."}, 404)
        elif parsed.path == "/api/sample":
            self.send_json(json.loads((ROOT / "exemplo.json").read_text(encoding="utf-8")))
        elif parsed.path in ("/vendor/html2canvas.min.js", "/", "/index.html", "/app.js", "/style.css", "/pokemon.css", "/favicon.svg", "/sprite-placeholder.svg"):
            name = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
            file = ROOT / "static" / name
            content_types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}
            data = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_types[file.suffix] + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_json({"error": "Página não encontrada."}, 404)

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            size = int(self.headers.get("Content-Length", 0))
            limit = 52_000_000 if path.startswith("/api/restore") else 5_000_000
            if size <= 0 or size > limit:
                raise ValueError(f"Envie um JSON de até {limit // 1_000_000} MB.")
            body = json.loads(self.rfile.read(size).decode("utf-8-sig"))
            if path == "/api/profile":
                self.send_json(self.store.save_profile(body))
            elif path == "/api/images":
                name = pokemon_key(label(body.get("name")))
                if not name:
                    raise ValueError("Informe o nome do Pokémon.")
                value = body.get("image", "")
                validate_image(value)
                with self.store.connect() as connection:
                    if value:
                        connection.execute("INSERT INTO custom_images VALUES (?,?) ON CONFLICT(name) DO UPDATE SET image=excluded.image", (name,value))
                    else:
                        connection.execute("DELETE FROM custom_images WHERE name=?", (name,))
                self.send_json({"ok": True})
            elif path == "/api/preview":
                self.send_json(self.store.preview(body.get("report")))
            elif path == "/api/hunts":
                record = self.store.save(body.get("record"), body.get("replace") is True)
                self.send_json({"record": record})
            elif path == "/api/delete":
                self.store.delete(label(body.get("id")))
                self.send_json({"ok": True})
            elif path == "/api/prices":
                self.send_json(self.store.save_prices(body.get("prices"), body.get("scope", "future")))
            elif path == "/api/restore/preview":
                self.send_json(self.store.restore_preview(body.get("backup")))
            elif path == "/api/restore":
                if body.get("confirmed") is not True:
                    raise ValueError("Revise o backup e confirme a substituição dos dados para restaurar.")
                self.send_json(self.store.restore(body.get("backup")))
            else:
                self.send_json({"error": "Ação não encontrada."}, 404)
        except FileExistsError as exc:
            self.send_json({"error": str(exc)}, 409)
        except (ValueError, TypeError, AttributeError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except sqlite3.Error:
            self.send_json({"error": "Não foi possível salvar no banco local. Tente novamente."}, 500)
        except OSError:
            self.send_json({"error": "Não foi possível criar a cópia de recuperação. A restauração não foi aplicada."}, 500)


def main():
    parser = argparse.ArgumentParser(description="PXG Hunt Tracker local")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--seed", action="store_true", help="Importa uma vez a hunt de exemplo fornecida")
    args = parser.parse_args()
    Handler.store = Store(args.db)
    if args.seed:
        record = parse_report(json.loads((ROOT / "exemplo.json").read_text(encoding="utf-8")))
        if not Handler.store.get(record["id"]):
            Handler.store.save(record)
    url = f"http://127.0.0.1:{args.port}"
    try:
        server = LocalHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        try:
            with urlopen(url + "/api/status", timeout=2) as response:
                existing = json.load(response)
            if existing.get("app") == "huntlog":
                print(f"O Huntlog já está aberto em {url}", flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                return
        except Exception:
            pass
        parser.exit(1, f"Não foi possível abrir a porta {args.port}. Tente outra com --port 8766.\n")
    print(f"PXG Hunt Tracker em {url}\nBanco: {args.db}\nCtrl+C para encerrar.", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
