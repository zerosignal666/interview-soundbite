"""Behavioral checks using synthetic subtitles; no personal media required."""
import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "clip_srt.py"
SPEC = importlib.util.spec_from_file_location("clip_srt", SCRIPT)
clip = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clip)

SOURCE = """1
00:00:01,000 --> 00:00:02,000
第一行
第二行

2
00:00:03,000 --> 00:00:04,500
同一段的后一句

3
00:00:10,000 --> 00:00:12,000
另一个完整语段

"""


class ClipSrtTests(unittest.TestCase):
    def setUp(self):
        self.cues = clip.parse_srt(SOURCE)

    def test_reordering_preserves_independent_source_and_edit_timelines(self):
        source, edited, report = clip.build(self.cues, {"segments": [
            {"first": 3, "last": 3}, {"first": 1, "last": 2}
        ]})
        self.assertEqual([c["id"] for c in source], [1, 2, 3])
        self.assertEqual([c["source_id"] for c in report["cues"]], [3, 1, 2])
        self.assertEqual([c["start_ms"] for c in edited], [0, 2000, 4000])
        self.assertEqual(report["actual_duration_ms"], 5500)
        self.assertEqual(report["major_joins"], 1)

    def test_internal_silence_and_multiline_text_round_trip(self):
        _, edited, report = clip.build(self.cues, {"segments": [{"first": 1, "last": 2}]})
        self.assertEqual(report["actual_duration_ms"], 3500)
        self.assertEqual(edited[1]["start_ms"] - edited[0]["end_ms"], 1000)
        restored = clip.parse_srt(clip.srt(edited))
        self.assertEqual(restored[0]["text"], "第一行\n第二行")
        self.assertEqual(restored[-1]["end_ms"], 3500)

    def test_invalid_selections_are_rejected(self):
        for selection in [
            [{"first": 1, "last": 2}, {"first": 2, "last": 3}],
            [{"first": 1, "last": 999}],
            [{"first": 3, "last": 1}],
            [{"first": True, "last": 2}],
        ]:
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                clip.build(self.cues, {"segments": selection})

    def test_source_timeline_reset_is_rejected(self):
        with self.assertRaises(ValueError):
            clip.parse_srt(SOURCE.replace("00:00:10,000", "00:00:00,000"))

    def test_overlapping_selected_cues_are_rejected(self):
        cues = clip.parse_srt(SOURCE.replace("00:00:03,000", "00:00:01,500"))
        with self.assertRaises(ValueError):
            clip.build(cues, {"segments": [{"first": 1, "last": 2}]})

    def test_target_length_does_not_rewrite_or_stretch_audio(self):
        _, edited, report = clip.build(self.cues, {
            "target_seconds": 60, "segments": [{"first": 3, "last": 3}]
        })
        self.assertEqual(report["actual_duration_ms"], 2000)
        self.assertEqual(edited[0]["text"], self.cues[2]["text"])
        self.assertEqual(edited[0]["end_ms"], 2000)


if __name__ == "__main__":
    unittest.main()
