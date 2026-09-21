import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import updater

class UpdaterTests(unittest.TestCase):
    def test_release_notes(self):
        for body, expected in [(None, 'Esta versão não possui novidades descritas.'),
                               ('  Novas abas\n- Correção do Ghost  ', 'Novas abas\n- Correção do Ghost'),
                               ('', 'Esta versão não possui novidades descritas.')]:
            release=self.release();release['body']=body
            with patch('updater.read_url',return_value=json.dumps(release).encode()):
                self.assertEqual(updater.latest('0.6.1')['notes'],expected)

    def release(self, tag='v0.6.2'):
        return {'tag_name': tag, 'assets': [
            {'name': name, 'browser_download_url': f'https://github.com/hesuch/huntlog/releases/download/{tag}/{name}'}
            for name in (updater.ASSET, updater.ASSET + '.sha256.txt')]}

    def test_versions_and_release_validation(self):
        with patch('updater.read_url', return_value=json.dumps(self.release()).encode()):
            self.assertEqual(updater.latest('0.6.1-desktop')['tag'], 'v0.6.2')
            self.assertIsNone(updater.latest('0.6.2-desktop'))
            self.assertIsNone(updater.latest('0.7.0'))
        release = self.release()
        release['assets'][0]['browser_download_url'] = 'https://example.com/untrusted.zip'
        with patch('updater.read_url', return_value=json.dumps(release).encode()):
            with self.assertRaises(ValueError): updater.latest('0.6.1')

    def test_extract_rejects_traversal_and_incomplete_package(self):
        for name in ('../outside', 'Huntlog/../../outside', 'Huntlog/a:stream', 'Huntlog\\bad', 'Huntlog/readme.txt'):
            with tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / 'test.zip'
                with zipfile.ZipFile(archive, 'w') as package: package.writestr(name, 'test')
                with self.assertRaises(ValueError): updater.extract(archive, Path(directory) / 'stage')

    def test_download_checksum_and_valid_package(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as package:
            package.writestr('Huntlog/Huntlog.exe', 'test')
            package.writestr('Huntlog/_internal/test.dll', 'test')
        payload = buffer.getvalue()
        release = {'assets': {updater.ASSET: 'zip', updater.ASSET+'.sha256.txt': 'sum'}}
        with patch('updater.read_url', side_effect=[b'0'*64, payload]):
            with self.assertRaises(ValueError): updater.download(release)
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / 'work'; work.mkdir()
            with patch('updater.tempfile.mkdtemp', return_value=str(work)), patch('updater.read_url', side_effect=[hashlib.sha256(payload).hexdigest().encode(), payload]):
                result = updater.download(release)
                self.assertTrue((result / 'Huntlog.exe').exists())

if __name__ == '__main__': unittest.main()
