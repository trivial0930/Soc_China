import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.backend import assets, store  # noqa: E402

CSV = """name,category,station_id,area,cabinet,drawer,box,quantity,note
示波器,large,desk-03,A区,,,,1,Tektronix
万用表,large,desk-01,A区,,,,4,
0.25W电阻10k,small,,,元件柜2,抽屉3,盒B,500,
杜邦线,small,,,耗材柜1,抽屉1,盒A,200,
,large,desk-09,B区,,,,1,空名应被跳过
"""


class AssetsTests(unittest.TestCase):
    def setUp(self):
        self.s = store.Store(":memory:")
        fd = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        fd.write(CSV)
        fd.close()
        self.csv_path = fd.name
        assets.seed_assets(self.s, assets.load_assets_csv(self.csv_path))

    def test_load_skips_blank_name(self):
        rows = assets.load_assets_csv(self.csv_path)
        self.assertEqual(len(rows), 4)  # blank-name row skipped

    def test_location_text_large_and_small(self):
        self.assertEqual(
            assets.location_text({"category": "large", "station_id": "desk-03", "area": "A区"}),
            "工位 desk-03 / A区")
        self.assertEqual(
            assets.location_text({"category": "small", "cabinet": "元件柜2", "drawer": "抽屉3", "box": "盒B"}),
            "元件柜2 / 抽屉3 / 盒B")

    def test_query_by_name_fuzzy(self):
        r = assets.query_assets(self.s, name="电阻")
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["items"][0]["name"], "0.25W电阻10k")
        self.assertEqual(r["items"][0]["location_text"], "元件柜2 / 抽屉3 / 盒B")

    def test_query_by_category(self):
        self.assertEqual(assets.query_assets(self.s, category="large")["total"], 2)
        self.assertEqual(assets.query_assets(self.s, category="small")["total"], 2)

    def test_query_by_station(self):
        r = assets.query_assets(self.s, station="desk-03")
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["items"][0]["name"], "示波器")

    def test_update_asset(self):
        oid = assets.query_assets(self.s, name="示波器")["items"][0]["id"]
        self.s.upsert_asset({"id": oid, "name": "示波器", "category": "large",
                             "station_id": "desk-05", "area": "B区", "quantity": 1})
        r = assets.query_assets(self.s, name="示波器")["items"][0]
        self.assertEqual(r["location_text"], "工位 desk-05 / B区")


if __name__ == "__main__":
    unittest.main()
