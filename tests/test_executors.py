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

from inspection_manager.events import parse_event  # noqa: E402
from inspection_manager.recheck import parse_recheck, pose_for_waypoint  # noqa: E402
from inspection_manager.sim_scenarios import make_event, sample_events  # noqa: E402
from inspection_manager.tts import (  # noqa: E402
    MockTTSBackend,
    SubprocessTTSBackend,
    VoiceThrottle,
    aplay_args,
    espeak_args,
    make_tts_backend,
    piper_synth_args,
)


class VoiceThrottleTests(unittest.TestCase):
    def test_same_text_suppressed_within_window(self):
        t = VoiceThrottle(window_sec=10.0)
        self.assertTrue(t.allow("请处理", now=0.0))
        self.assertFalse(t.allow("请处理", now=3.0))
        self.assertTrue(t.allow("请处理", now=11.0))  # window passed

    def test_different_text_not_suppressed(self):
        t = VoiceThrottle(window_sec=10.0)
        self.assertTrue(t.allow("A", now=0.0))
        self.assertTrue(t.allow("B", now=1.0))

    def test_mock_backend_records(self):
        b = MockTTSBackend()
        b.speak("hi")
        b.speak("bye")
        self.assertEqual(b.spoken, ["hi", "bye"])


class TTSArgBuilderTests(unittest.TestCase):
    def test_espeak_text_is_its_own_argv_element(self):
        # Dangerous text must stay one argv element — never split / interpreted.
        nasty = '他说"危险"; rm -rf / && echo $(whoami)'
        args = espeak_args(nasty, voice="zh", speed=160)
        self.assertEqual(args[:5], ["espeak-ng", "-v", "zh", "-s", "160"])
        self.assertEqual(args[-1], nasty)  # intact, last element
        self.assertEqual(len(args), 6)

    def test_aplay_args_with_and_without_device(self):
        self.assertEqual(aplay_args("/tmp/a.wav"), ["aplay", "-q", "/tmp/a.wav"])
        self.assertEqual(
            aplay_args("/tmp/a.wav", "plughw:1,0"),
            ["aplay", "-q", "-D", "plughw:1,0", "/tmp/a.wav"],
        )

    def test_piper_synth_args(self):
        self.assertEqual(
            piper_synth_args("/opt/piper/piper", "/opt/piper/zh.onnx", "/tmp/o.wav"),
            ["/opt/piper/piper", "--model", "/opt/piper/zh.onnx", "--output_file", "/tmp/o.wav"],
        )


class SubprocessTTSBackendTests(unittest.TestCase):
    def _recorder(self):
        calls = []

        def run(args, stdin_text=None):
            calls.append((list(args), stdin_text))

        return calls, run

    def test_espeak_passes_text_as_argv_not_shell(self):
        calls, run = self._recorder()
        b = SubprocessTTSBackend(engine="espeak", espeak_voice="zh", runner=run)
        nasty = '电烙铁"未关"; danger'
        b.speak(nasty)
        self.assertEqual(len(calls), 1)
        args, stdin = calls[0]
        self.assertEqual(args[0], "espeak-ng")
        self.assertEqual(args[-1], nasty)  # text isolated as one arg
        self.assertIsNone(stdin)

    def test_piper_pipes_text_on_stdin_then_plays(self):
        calls, run = self._recorder()
        b = SubprocessTTSBackend(
            engine="piper", piper_bin="piper", piper_model="zh.onnx",
            aplay_device="plughw:1,0", runner=run,
        )
        b.speak("三号工位电烙铁未关")
        self.assertEqual(len(calls), 2)
        synth_args, synth_stdin = calls[0]
        play_args, play_stdin = calls[1]
        self.assertEqual(synth_args[0], "piper")
        self.assertEqual(synth_stdin, "三号工位电烙铁未关")  # text on stdin, not argv
        self.assertNotIn("三号工位电烙铁未关", synth_args)
        self.assertEqual(play_args[0], "aplay")
        self.assertIn("plughw:1,0", play_args)
        # piper writes a wav; aplay plays the same wav
        self.assertEqual(synth_args[-1], play_args[-1])

    def test_empty_text_does_not_speak(self):
        calls, run = self._recorder()
        SubprocessTTSBackend(engine="espeak", runner=run).speak("")
        self.assertEqual(calls, [])

    def test_runner_exception_propagates(self):
        def boom(args, stdin_text=None):
            raise RuntimeError("no audio device")

        with self.assertRaises(RuntimeError):
            SubprocessTTSBackend(engine="espeak", runner=boom).speak("hi")


class MakeTTSBackendTests(unittest.TestCase):
    def test_none_and_mock_give_mock(self):
        self.assertIsInstance(make_tts_backend("none"), MockTTSBackend)
        self.assertIsInstance(make_tts_backend(""), MockTTSBackend)
        self.assertIsInstance(make_tts_backend("mock"), MockTTSBackend)

    def test_engine_gives_subprocess_backend(self):
        b = make_tts_backend("espeak", espeak_voice="cmn")
        self.assertIsInstance(b, SubprocessTTSBackend)
        self.assertEqual(b.espeak_voice, "cmn")


class RecheckTests(unittest.TestCase):
    CFG = {"poses": {"wp_desk03": [1.5, 2.0, 0.0], "wp_desk05": [3.0, 1.0, 1.57]}}

    def test_parse_recheck_string_and_dict(self):
        self.assertEqual(
            parse_recheck('{"station_id":"desk-03","waypoint":"wp_desk03"}'),
            {"station_id": "desk-03", "waypoint": "wp_desk03"},
        )
        self.assertEqual(parse_recheck({"station_id": "x"})["waypoint"], None)

    def test_pose_lookup(self):
        self.assertEqual(pose_for_waypoint("wp_desk05", self.CFG), (3.0, 1.0, 1.57))

    def test_pose_lookup_missing_returns_none(self):
        self.assertIsNone(pose_for_waypoint("nope", self.CFG))
        self.assertIsNone(pose_for_waypoint(None, self.CFG))
        self.assertIsNone(pose_for_waypoint("wp_desk03", {}))


class SimScenarioTests(unittest.TestCase):
    def test_make_event_is_parseable(self):
        ev = make_event("e1", "desk-01", "warning", "x")
        parsed = parse_event(ev)  # must satisfy the schema
        self.assertEqual(parsed.station_id, "desk-01")
        self.assertEqual(parsed.event_type, "thermal_risk")

    def test_desk_messy_event_uses_camera_source(self):
        ev = make_event("e2", "desk-01", "warning", "乱", event_type="desk_messy")
        self.assertEqual(ev["source"], "camera")

    def test_sample_events_mixed_and_valid(self):
        events = sample_events()
        self.assertEqual(len(events), 3)
        for e in events:
            parse_event(e)  # all valid
        severities = {e["severity"] for e in events}
        self.assertIn("critical", severities)


if __name__ == "__main__":
    unittest.main()
