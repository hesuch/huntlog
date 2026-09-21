import json, tempfile, unittest
from pathlib import Path
from datetime import datetime
from app import Store, parse_report, normalize_record, weekly_summary

class ReleaseTests(unittest.TestCase):
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
