import sys
import unittest
from pathlib import Path

PACKAGE_SRC = (
    Path(__file__).resolve().parents[1]
    / "rdk_x5"
    / "ros2_ws"
    / "src"
    / "inspection_manager"
)
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.station_map import (  # noqa: E402
    StationMap,
    StationRegion,
    station_map_from_dict,
)


CFG = {
    "regions": [
        {"station_id": "desk-01", "camera": "cam-front", "rect": [0, 0, 960, 1080]},
        {"station_id": "desk-02", "camera": "cam-front", "rect": [960, 0, 1920, 1080]},
        {"station_id": "desk-03", "camera": "cam-rear", "rect": [0, 0, 1920, 1080]},
    ],
    "waypoints": {"wp_desk01": "desk-01", "wp_desk02": "desk-02"},
}


class StationMapTests(unittest.TestCase):
    def setUp(self):
        self.smap = station_map_from_dict(CFG)

    def test_pixel_resolves_to_region_on_correct_camera(self):
        self.assertEqual(self.smap.station_for_pixel("cam-front", 100, 500), "desk-01")
        self.assertEqual(self.smap.station_for_pixel("cam-front", 1500, 500), "desk-02")

    def test_same_pixel_different_camera_resolves_differently(self):
        self.assertEqual(self.smap.station_for_pixel("cam-rear", 100, 500), "desk-03")

    def test_box_uses_centre(self):
        # centre = (1050, 150) -> unambiguously inside desk-02
        self.assertEqual(self.smap.station_for_box("cam-front", [1000, 100, 1100, 200]), "desk-02")

    def test_pixel_outside_all_regions_returns_none(self):
        self.assertIsNone(self.smap.station_for_pixel("cam-front", 5000, 5000))
        self.assertIsNone(self.smap.station_for_pixel("cam-unknown", 100, 100))

    def test_waypoint_forward_and_reverse(self):
        self.assertEqual(self.smap.station_for_waypoint("wp_desk02"), "desk-02")
        self.assertEqual(self.smap.waypoint_for_station("desk-01"), "wp_desk01")
        self.assertIsNone(self.smap.waypoint_for_station("desk-99"))

    def test_empty_config_is_safe(self):
        smap = station_map_from_dict({})
        self.assertEqual(smap.regions, [])
        self.assertIsNone(smap.station_for_pixel("any", 0, 0))


if __name__ == "__main__":
    unittest.main()
