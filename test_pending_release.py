import json,tempfile,unittest,copy
from pathlib import Path
from app import Store,parse_report,normalize_record,statistics,boss_image
from wiki_assets import WikiSprites

class PendingReleaseTests(unittest.TestCase):
    def test_prices_duplicates_backup_restore_and_ghost(self):
        report=json.loads(Path('exemplo.json').read_text(encoding='utf-8'))
        record=parse_report(report)
        record.update(category='mixed',items=[dict(kind='drop',name='Ghostly loot bag (Expert)',count=1,price=100,included=True),dict(kind='supply',name='Spell tag',count=8,price=1,included=True)],enemies=[dict(name=n,count=c,rare=False,included=True) for n,c in [('Boss Giant Ghost',1),('Gastly',7)]])
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'a.sqlite3');store.save(record)
            saved=store.all()[0];self.assertEqual(saved['kills'],1)
            with self.assertRaises(FileExistsError):store.save(record)
            record['notes']='Updated';store.save(record,replace=True);self.assertEqual(len(store.all()),1)
            row=dict(kind='drop',name='Ghostly loot bag (Expert)',price=200)
            store.save_prices([row],scope='future');self.assertEqual(store.all()[0]['profit'],92)
            newer=copy.deepcopy(record);newer['session_id']='new';store.save(newer)
            self.assertEqual(store.get(normalize_record(newer)['id'])['profit'],192)
            row['price']=300;store.save_prices([row],scope='history')
            self.assertEqual([r['profit'] for r in store.all()],[292,292])
            backup=store.backup();restored=Store(Path(d)/'b.sqlite3');restored.restore(backup)
            self.assertEqual(restored.all(),store.all())
            self.assertEqual(restored.all()[0]['enemies'][1]['reported_count'],7)
            restored.restore(restored.backup());self.assertEqual(restored.all()[0]['kills'],1)

    def test_all_boss_art_and_context(self):
        from app import battle_image
        aliases=json.loads(Path('static/boss-images.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            sprites=WikiSprites('static/sprites',d)
            for image in set(aliases.values()):self.assertIsNotNone(sprites.get(image),image)
        self.assertEqual(boss_image('Suicune','hunt'),'')
        self.assertEqual(boss_image('Suicune','mixed'),'Boss Fight - Suicune')
        self.assertEqual(boss_image('Terror Gyarados','mixed'),'Nightmare Terror - Gyakkyo')
        self.assertEqual(boss_image('Gyarados','mixed'),'')
        self.assertEqual(battle_image('Noctu','mixed'),'Mystery Dungeon Defeat The Darkness')
        self.assertEqual(battle_image('Iron-Masked Marauder','mixed'),'Mystery Dungeon The Iron-Masked Marauder')

    def test_ambiguous_ghost_does_not_discount(self):
        from app import adjust_ghost_helpers
        enemies=[dict(name='Boss Giant Ghost',count=1,included=True),dict(name='Gastly',count=7,included=True)]
        items=[dict(kind='drop',name='Ghostly loot bag (Expert)',count=1,included=True),dict(kind='drop',name='Ghostly loot bag (Hard)',count=1,included=True),dict(kind='supply',name='Spell tag',count=8,included=True)]
        self.assertIsNone(adjust_ghost_helpers(enemies,items));self.assertEqual(enemies[1]['count'],7)
