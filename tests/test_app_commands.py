import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.backend import commands, store  # noqa: E402


class ValidateCommandTests(unittest.TestCase):
    def test_unknown_type_rejected(self):
        self.assertIsNotNone(commands.validate_command("fly_to_moon", {}))

    def test_params_must_be_object(self):
        self.assertIsNotNone(commands.validate_command("inspection_round", "nope"))

    def test_inspection_round_needs_nothing(self):
        self.assertIsNone(commands.validate_command("inspection_round", {}))

    def test_recheck_requires_station(self):
        self.assertIsNone(commands.validate_command("recheck_station", {"station_id": "desk-03"}))
        self.assertIsNotNone(commands.validate_command("recheck_station", {}))

    def test_acceptance_station_optional(self):
        self.assertIsNone(commands.validate_command("acceptance", {}))
        self.assertIsNone(commands.validate_command("acceptance", {"station_id": "desk-03"}))

    def test_find_item_needs_target_and_valid_mode(self):
        self.assertIsNone(commands.validate_command("find_item", {"asset_id": 3}))
        self.assertIsNone(commands.validate_command("find_item", {"name": "示波器", "mode": "laser"}))
        self.assertIsNotNone(commands.validate_command("find_item", {}))                    # no target
        self.assertIsNotNone(commands.validate_command("find_item", {"name": "x", "mode": "fly"}))

    def test_voice_requires_text(self):
        self.assertIsNone(commands.validate_command("voice_prompt", {"text": "请整理"}))
        self.assertIsNotNone(commands.validate_command("voice_prompt", {"station_id": "desk-03"}))

    def test_laser_requires_station_or_location(self):
        self.assertIsNone(commands.validate_command("laser_point", {"station_id": "desk-03"}))
        self.assertIsNone(commands.validate_command("laser_point", {"location": "柜2/抽屉3"}))
        self.assertIsNotNone(commands.validate_command("laser_point", {}))

    def test_set_volume_requires_int_0_100(self):
        self.assertIsNone(commands.validate_command("set_volume", {"level": 0}))
        self.assertIsNone(commands.validate_command("set_volume", {"level": 100}))
        self.assertIsNone(commands.validate_command("set_volume", {"level": 60}))
        for bad in ({}, {"level": -1}, {"level": 101}, {"level": 50.5}, {"level": "80"}, {"level": True}):
            self.assertEqual(commands.validate_command("set_volume", bad),
                             "set_volume 需要整数 params.level (0-100)")

    def test_voice_control_requires_bool_enabled(self):
        self.assertIsNone(commands.validate_command("voice_control", {"enabled": True}))
        self.assertIsNone(commands.validate_command("voice_control", {"enabled": False}))
        # missing enabled, or non-bool (incl. truthy 1) -> rejected with the contract message
        self.assertEqual(commands.validate_command("voice_control", {}),
                         "voice_control 需要布尔 params.enabled")
        self.assertEqual(commands.validate_command("voice_control", {"enabled": 1}),
                         "voice_control 需要布尔 params.enabled")

    def test_normalize_defaults(self):
        self.assertEqual(commands.normalize_params("find_item", {"name": "x"})["mode"], "navigate")
        self.assertEqual(commands.normalize_params("generate_report", {})["report_type"], "periodic_summary")


class CommandStoreTests(unittest.TestCase):
    def setUp(self):
        self.s = store.Store(":memory:")

    def test_insert_shapes_and_id_and_status(self):
        c = self.s.insert_command("recheck_station", {"station_id": "desk-03"})
        self.assertTrue(c["command_id"].startswith("cmd-"))
        self.assertEqual(c["status"], "queued")
        self.assertEqual(c["type"], "recheck_station")
        self.assertEqual(c["params"], {"station_id": "desk-03"})
        self.assertEqual(c["issued_by"], "app")
        self.assertEqual(self.s.get_command(c["command_id"])["status"], "queued")

    def test_unique_ids_within_same_second(self):
        a = self.s.insert_command("inspection_round", {})
        b = self.s.insert_command("inspection_round", {})
        self.assertNotEqual(a["command_id"], b["command_id"])

    def test_list_filters_and_pagination(self):
        self.s.insert_command("inspection_round", {})
        self.s.insert_command("recheck_station", {"station_id": "d1"})
        self.assertEqual(self.s.list_commands(type="recheck_station")["total"], 1)
        self.assertEqual(self.s.list_commands(status="queued")["total"], 2)
        self.assertEqual(len(self.s.list_commands(limit=1)["items"]), 1)

    def test_pending_is_fifo_and_only_queued(self):
        a = self.s.insert_command("inspection_round", {})
        b = self.s.insert_command("voice_prompt", {"text": "x"})
        pend = self.s.pending_commands()
        self.assertEqual([p["command_id"] for p in pend], [a["command_id"], b["command_id"]])
        self.s.ack_command(a["command_id"])
        self.assertEqual([p["command_id"] for p in self.s.pending_commands()], [b["command_id"]])

    def test_ack_moves_queued_to_sent(self):
        c = self.s.insert_command("inspection_round", {})
        out = self.s.ack_command(c["command_id"])
        self.assertEqual(out["status"], "sent")
        self.assertIsNone(self.s.ack_command("cmd-nope"))

    def test_result_sets_status_and_text(self):
        c = self.s.insert_command("recheck_station", {"station_id": "d1"})
        self.s.ack_command(c["command_id"])
        out = self.s.set_command_result(c["command_id"], "done", "已到位并复核")
        self.assertEqual(out["status"], "done")
        self.assertEqual(out["result"], "已到位并复核")
        # bad status coerced to done; missing command -> None
        bad = self.s.insert_command("inspection_round", {})
        self.assertEqual(self.s.set_command_result(bad["command_id"], "weird", "x")["status"], "done")
        self.assertIsNone(self.s.set_command_result("cmd-nope", "done", "x"))


if __name__ == "__main__":
    unittest.main()
