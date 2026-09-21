import json, tempfile, unittest
from pathlib import Path
from datetime import datetime
from app import Store, parse_report, normalize_record, weekly_summary

class ReleaseTests(unittest.TestCase):
    def test_battle_divisions_mixed_without_duplicate_counts(self):
        from app import statistics
        r=parse_report(json.loads(Path('exemplo.json').read_text(encoding='utf-8')))
        r.update(category='mixed',enemies=[dict(name=n,count=c,rare=rare,included=True) for n,c,rare in
            [('Boss Giant Ghost',1,False),('Noctu',1,False),('Iron-Masked Marauder',1,False),
             ('Kame',1,False),('Lairon',4,False),('Shiny Gengar',2,True)]],items=[])
        result=statistics([normalize_record(r)])
        rows={e['name']:e for e in result['defeated']}
        self.assertEqual(rows['Boss Giant Ghost']['battle_group'],'boss')
        self.assertEqual(rows['Kame']['battle_group'],'boss')
        self.assertEqual(rows['Noctu']['battle_group'],'dungeon')
        self.assertEqual(rows['Iron-Masked Marauder']['battle_group'],'dungeon')
        self.assertEqual(rows['Shiny Gengar']['battle_group'],'pokemon')
        self.assertEqual(sum(e['count'] for e in rows.values()),result['kills'])
        self.assertEqual(result['kills'],10)

    def test_ghost_attempts_and_repeat_normalization(self):
        r=parse_report(json.loads(Path('exemplo.json').read_text(encoding='utf-8')))
        r.update(category='mixed',enemies=[dict(name=n,count=c,rare=n=='Shiny Gengar',included=True) for n,c in
            [('Boss Giant Ghost',1),('Gastly',7),('Haunter',4),('Gengar',1),('Shiny Gengar',1),('Noctu',1)]])
        for difficulty,cost in [('Normal',1),('Hard',2),('Expert',4)]:
            r['items']=[dict(kind=k,name=n,count=c,price=0,included=True) for k,n,c in
                        [('drop',f'Ghostly loot bag ({difficulty})',1),('supply','Spell tag',cost*2)]]
            result=normalize_record(r)
            self.assertEqual(result['kills'],2)
            self.assertEqual(result['rare_kills'],0)
            self.assertEqual(result['ghost_adjustment']['attempts'],2)
            self.assertEqual(result['ghost_adjustment']['excluded'],13)
            self.assertEqual(normalize_record(result),result)
        r['enemies'][1]['count']=10
        result=normalize_record(r)
        self.assertEqual(result['enemies'][1]['count'],2)
        self.assertEqual(result['enemies'][1]['reported_count'],10)
        r['enemies']=r['enemies'][1:]
        self.assertIsNone(normalize_record(r)['ghost_adjustment'])

    def test_wiki_item_images_available_offline(self):
        from wiki_assets import WikiSprites
        from unittest.mock import patch
        entries=json.loads(Path('static/item-images.json').read_text(encoding='utf-8'))
        self.assertGreater(len(entries),800)
        with tempfile.TemporaryDirectory() as d, patch('wiki_assets.wiki_query',side_effect=AssertionError('Offline lookup used the network')):
            sprites=WikiSprites('static/sprites',d)
            for entry in entries.values():
                self.assertIsNotNone(sprites.get(entry['name']),entry['name'])

    def test_mixed_category_persistence_and_counting(self):
        r=parse_report(json.loads(Path('exemplo.json').read_text(encoding='utf-8')))
        r.update(category='mixed', location='', location_source='auto', enemies=[
            dict(name='Lairon',count=3,rare=False,included=True),
            dict(name='Nightmare Crystal',count=1,rare=False,included=True),
            dict(name='Aron',count=2,rare=False,included=False)])
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'mixed.sqlite3')
            store.save(r)
            saved=store.all()[0]
            self.assertEqual(saved['category'],'mixed')
            self.assertEqual(saved['location'],'Mista')
            self.assertEqual(saved['kills'],4)
            self.assertEqual(saved['rare_kills'],1)
            saved.update(location='Vários locais',location_source='manual')
            store.save(saved,replace=True)
            self.assertEqual(store.all()[0]['location'],'Vários locais')

    def test_shiny_pack_associations(self):
        from wiki_assets import WikiSprites, key
        import hashlib
        manifest=json.loads(Path('static/shiny-images.json').read_text(encoding='utf-8'))
        catalog=json.loads(Path('static/sprites/catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['associations']),165)
        self.assertEqual(manifest['associations']['Shiny Lairon'],'305.1.png')
        self.assertEqual(manifest['associations']['Shiny Aggron'],'306.3.png')
        with tempfile.TemporaryDirectory() as d:
            sprites=WikiSprites('static/sprites',d)
            for name,member in manifest['associations'].items():
                entry=catalog[key(name)]
                self.assertEqual(entry['source'],'pokemons.zip/pokemons/'+member)
                path=sprites.get(name)
                self.assertIsNotNone(path,name)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest()[:20]+'.png',entry['file'])

    def test_tiers_and_enraged_historical_records(self):
        from app import is_rare_encounter
        from wiki_assets import WikiSprites
        r=parse_report(json.loads(Path("exemplo.json").read_text(encoding="utf-8")))
        r.update(category="hunt", enemies=[dict(name=n,count=2,rare=True,included=True) for n in
            ("Enraged Aggron", "Shiny Lairon", "Mega Beedrill", "Enraged Sharpedo", "Nightmare Crystal")])
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/"test.sqlite3")
            # Exercise the read path for a diary saved before these classification rules.
            import sqlite3
            with sqlite3.connect(store.path) as c:
                c.execute("INSERT INTO hunts (id,started,data) VALUES (?,?,?)", (r['id'],r['started'],json.dumps(r)))
            c.close()
            result=store.all()[0]
            self.assertEqual(result['enemies'][0]['name'], 'Mega Aggron')
            self.assertEqual([e['rare'] for e in result['enemies']], [True,False,False,False,True])
            self.assertEqual(result['rare_kills'],4)
            self.assertEqual(result['kills'],10)
            sprites=WikiSprites('static/sprites',Path(d)/'cache')
            self.assertEqual(sprites.get('Enraged Aggron'),sprites.get('Mega Aggron'))
            self.assertIsNotNone(sprites.get('Enraged Aggron'))
        self.assertFalse(is_rare_encounter('Mega Aggron',False))
        self.assertTrue(is_rare_encounter('Unknown Pokemon',True))
        self.assertTrue(is_rare_encounter('Nightmare Crystal',False))

    def test_empty_diary_and_profile_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.sqlite3"
            s=Store(p)
            self.assertEqual(s.all(), [])
            s.save_profile({"name":"Treinador", "characters":["A","a","B"], "image":""})
            self.assertEqual(Store(p).profile()["characters"], ["A","B"])

    def test_category_and_reset(self):
        r=parse_report(json.loads(Path("exemplo.json").read_text(encoding="utf-8")))
        r.update(category="terror", started="2026-09-21 07:45:00", enemies=[dict(name="Kame",count=1,rare=False,included=True),dict(name="Shiny Politoed",count=1,rare=True,included=True)])
        r=normalize_record(r)
        self.assertEqual(r["kills"],1)
        self.assertEqual(r["rare_kills"],0)
        self.assertEqual(weekly_summary([r],1,datetime(2026,9,21,8))["stats"]["count"],0)
        self.assertEqual(weekly_summary([r],0,datetime(2026,9,21,8))["stats"]["count"],1)

    def test_all_bundled_images_exist(self):
        folder=Path("static/sprites")
        for entry in json.loads((folder/"catalog.json").read_text(encoding="utf-8")).values():
            if entry.get("file"):
                self.assertTrue((folder/entry["file"]).is_file(),entry.get("name"))

    def test_content_image_associations(self):
        from wiki_assets import key
        root = Path("static")
        catalog = json.loads((root / "sprites/catalog.json").read_text(encoding="utf-8"))
        names = json.loads((root / "terror-images.json").read_text(encoding="utf-8"))
        names += list(json.loads((root / "dungeon-images.json").read_text(encoding="utf-8")).values())
        names += [entry["image"] for entry in json.loads((root / "nightmare-hunts.json").read_text(encoding="utf-8"))]
        for name in names:
            self.assertIn(key(name), catalog, name)
            self.assertTrue((root / "sprites" / catalog[key(name)]["file"]).is_file(), name)
