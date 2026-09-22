import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import Store


class EnergyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'test.db')
        self.store.save_profile({'name': 'Test', 'characters': ['Alpha', 'Beta']})

    def configure(self, **kw):
        return self.store.save_energy(dict(name='Alpha', action='configure', current=100, maximum=105, talent=15, rainbow=True, **kw))

    def test_intervals(self):
        for talent, rh, minutes in [(15, True, 36), (15, False, 51), (10, False, 54), (20, False, 48)]:
            v=Store.energy_value(dict(talent=talent, rainbow=rh))
            self.assertEqual(Store.energy_now(v, 0)['interval'], minutes*60)

    def test_regen_actions_and_cap(self):
        with patch('time.time', return_value=1000):
            self.configure()
            self.store.save_energy(dict(name='Alpha', action='spend52'))
        with patch('time.time', return_value=2080):
            c=self.store.energy()['characters'][0]
            self.assertEqual(c['current'],48.5)
            self.store.save_energy(dict(name='Alpha', action='spend40'))
            self.assertEqual(self.store.energy()['characters'][0]['current'],8.5)
            self.store.save_energy(dict(name='Alpha', action='potion'))
            self.assertEqual(self.store.energy()['characters'][0]['current'],48.5)
        with patch('time.time', return_value=999999):
            self.assertEqual(self.store.energy()['characters'][0]['current'],105)
            self.store.save_energy(dict(name='Alpha', action='spend40'))
            self.assertEqual(self.store.energy()['characters'][0]['current'],65)
        with patch('time.time', return_value=1001079):
            self.assertEqual(self.store.energy()['characters'][0]['current'],65.5)

    def test_backup_and_isolation(self):
        self.configure()
        self.store.save_energy(dict(name='Alpha',action='image',image='https://example.com/photo.gif'))
        backup=self.store.backup()
        other=Store(Path(self.tmp.name)/'other.db');other.restore(backup)
        c=other.energy()['characters']
        self.assertEqual(c[0]['image'],'https://example.com/photo.gif')
        self.assertFalse(c[1]['configured'])
        old={k:v for k,v in backup.items() if k not in ('energy','profile')}
        other.restore(old)
        self.assertEqual(len(other.energy()['characters']),2)

    def test_validation_and_photo_before_setup(self):
        self.store.save_energy(dict(name='Beta',action='image',image='https://example.com/a.png'))
        self.assertFalse(self.store.energy()['characters'][1]['configured'])
        for body in [dict(name='Beta',action='spend40'), dict(name='Other',action='potion'),dict(name='Alpha',action='configure',current=106,maximum=105,talent=15,rainbow=False)]:
            with self.assertRaises(ValueError):self.store.save_energy(body)

if __name__ == '__main__':unittest.main()
