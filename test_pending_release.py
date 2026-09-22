import json,tempfile,unittest,copy
from pathlib import Path
from app import Store,parse_report,normalize_record,statistics,boss_image
from wiki_assets import WikiSprites

class PendingReleaseTests(unittest.TestCase):
    def test_profession_partition(self):
        from app import resource_profession
        base=parse_report(json.loads(Path('exemplo.json').read_text(encoding='utf-8')))
        base['items']=[dict(kind=k,name=n,count=c,price=p,included=i) for k,n,c,p,i in [
            ('drop','Food Bag',10,100,True),('drop','stone',2,50,True),('supply','Food Bag',1,100,True),
            ('drop','Tech Data',2,200,False)]]
        r=normalize_record(base)
        self.assertEqual(r['profession_raw'],1000)
        self.assertEqual(r['hunt_profit']+r['profession_raw'],r['profit'])
        self.assertEqual(r['items'][2]['profession'],'')
        self.assertEqual(resource_profession('FOOD BAGS'),'Cozinheiro')
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'a.sqlite3');store.save(r)
            other=Store(Path(d)/'b.sqlite3');other.restore(store.backup())
            self.assertEqual(other.all()[0]['profession_raw'],1000)

    def test_noctu_dungeon_location_and_suggestion(self):
        base=parse_report(json.loads(Path('exemplo.json').read_text(encoding='utf-8')))
        base.update(location='',location_source='auto',enemies=[dict(name='Noctu',count=1,rare=False,included=True)])
        record=normalize_record(base)
        self.assertEqual(record['suggested_category'],'mystery_dungeon')
        record['category']='mystery_dungeon'
        record=normalize_record(record)
        self.assertEqual(record['location'],'Defeat The Darkness')
        self.assertTrue(record['dungeon_image'])
        self.assertEqual(record['kills'],1)
        record['location']='Minha dungeon';record['location_source']='manual'
        self.assertEqual(normalize_record(record)['location'],'Minha dungeon')

    def test_terror_pair_and_damage_fallback(self):
        from app import add_terror_zoroark
        base=parse_report(json.loads(Path('exemplo.json').read_text(encoding='utf-8')))
        for a,b,expected in [(2,1,1),(1,2,1),(2,2,2),(1,0,0)]:
            record=dict(base,category='terror',enemies=[dict(name=n,count=c,included=True,rare=False) for n,c in [('Terror Alakazam',a),('Terror Gengar',b)]])
            normalized=normalize_record(record)
            self.assertEqual(normalized['kills'],expected)
            self.assertEqual(normalize_record(normalized)['kills'],expected)
        rows=[{'Enemy':n,'Damage dealt':100} for n in ('Terror Machamp','Terror Machamp','Terror Alakazam','Terror Gengar','Pikachu')]
        inferred=add_terror_zoroark({'Damage':rows},[])
        record=normalize_record(dict(base,category='terror',enemies=inferred))
        self.assertEqual(record['kills'],2)
        self.assertEqual(len([e for e in record['enemies'] if e['name']=='Terror Machamp']),1)
        self.assertTrue(next(e for e in record['enemies'] if e['name']=='Seishin & Yurei')['damage_inferred'])

    def test_individual_rare_choices(self):
        report=json.loads(Path('exemplo.json').read_text(encoding='utf-8'))
        record=parse_report(report)
        record.update(category='mixed', enemies=[
            dict(name='Nightmare Crystal',count=2,rare=True,included=False),
            dict(name='Mega Aggron',count=3,rare=True,included=True),
            dict(name='Aron',count=4,rare=False,included=True)])
        saved=normalize_record(record)
        self.assertEqual(saved['kills'],7)
        self.assertEqual(saved['rare_kills'],3)
        self.assertEqual(saved['profit'],record['profit'])
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'a.sqlite3');store.save(saved)
            other=Store(Path(d)/'b.sqlite3');other.restore(store.backup())
            restored=other.all()[0]
            self.assertFalse(restored['enemies'][0]['included'])
            report['Enemies Defeated']=[dict(Enemy=e['name'],Count=5,Rare=e['rare'],Player=record['player']) for e in record['enemies']]
            updated=store.preview(report)['record']
            self.assertFalse(updated['enemies'][0]['included'])
            self.assertTrue(updated['enemies'][1]['included'])
            restored['enemies'][0]['included']=True
            self.assertEqual(normalize_record(restored)['rare_kills'],5)

    def test_terror_zoroark_damage_counts_once(self):
        from app import add_terror_zoroark
        report = {'Damage': [dict(Enemy='Terror Zoroark', Player=p, **{'Damage dealt': 100})
                             for p in ('A', 'B', 'C', 'D')]}
        enemies = add_terror_zoroark(report, [])
        self.assertEqual(len(enemies), 1)
        self.assertEqual(enemies[0]['count'], 1)
        self.assertEqual(add_terror_zoroark(report, enemies), enemies)
        explicit = [dict(name='Terror Zoroark', count=2, included=False)]
        self.assertEqual(add_terror_zoroark(report, explicit), explicit)
        self.assertEqual(add_terror_zoroark({'Damage': [{'Enemy':'Terror Zoroark','Damage dealt':0}]}, []), [])
        self.assertEqual(add_terror_zoroark({'Damage': [{'Enemy':'Zoroark','Damage dealt':100}]}, []), [])
        solo = json.loads(Path('exemplo.json').read_text(encoding='utf-8'))
        solo['Damage'] = [dict(report['Damage'][0], Player=solo['Drops'][0]['Player'])]
        parsed = parse_report(solo)
        self.assertEqual(sum(e['count'] for e in parsed['enemies'] if e['name']=='Terror Zoroark'), 1)

    def test_party_uses_profile_characters_and_shared_bosses(self):
        report = {'Session': {'Session type':'party','Session ID':1,'Start':'2026-09-21 15:00:00',
                             'Duration seconds':3600,'Profit':999999},
                  'Drops':[{'Player':p,'Item':'stone','Count':1,'Unit price':v} for p,v in [('Mine',100),('Maker',200),('Other',900)]],
                  'Supplies':[{'Player':'Mine','Item':'potion','Count':1,'Unit price':10}],
                  'Enemies Defeated':[{'Player':'Other','Enemy':'Terror Gyarados','Count':1},
                                      {'Player':'Other','Enemy':'Pikachu','Count':9}],
                  'Damage':[{'Player':'Other','Enemy':'Terror Zoroark','Damage dealt':100}]}
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'party.sqlite3')
            with self.assertRaisesRegex(ValueError,'Cadastre'): store.preview(report)
            store.save_profile({'name':'Test','characters':[' mine ','MAKER']})
            record=store.preview(report)['record']
            self.assertEqual(record['profit'],290)
            self.assertIsNone(record['reported_profit'])
            self.assertEqual(record['player'],'Maker + Mine')
            self.assertEqual({e['name'] for e in record['enemies']},{'Terror Gyarados','Terror Zoroark'})
            store.save(record)
            self.assertTrue(store.preview(report)['exists'])
            store.save_profile({'name':'Test','characters':['Missing']})
            with self.assertRaisesRegex(ValueError,'Nenhum personagem'): store.preview(report)

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
