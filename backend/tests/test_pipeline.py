import tempfile
import unittest

from PIL import Image

from backend.fusion import fuse_signals
from backend.pipeline import analyze_media_file


class PipelineTests(unittest.TestCase):
    def test_analyze_media_file_returns_core_fields(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
            img = Image.new("RGB", (64, 64), color=(120, 90, 200))
            img.save(tmp.name, "JPEG")

            result = analyze_media_file(tmp.name, "sample.jpg")

        self.assertIn("trust_score", result)
        self.assertIn("label", result)
        self.assertIn("signals", result)
        self.assertTrue(0 <= result["trust_score"] <= 100)

    def test_fusion_penalizes_broken_provenance(self):
        base = {
            "metadata_completeness": {"score_0_to_3": 2},
            "metadata_consistency": {"status": "CONSISTENT"},
            "ai_disclosure": {"declared": "NO"},
            "transformation_hints": {"screenshot_likelihood": "LOW", "forwarded_or_reencoded": "UNKNOWN"},
            "container_anomalies": {"status": "OK", "notes": []},
            "visual_forensics": {"status": "CLEAR"},
        }
        good = fuse_signals(
            provenance_state="VERIFIED_ORIGINAL",
            c2pa_summary={"present": True, "validation": "VALID"},
            **base,
        )
        bad = fuse_signals(
            provenance_state="ALTERED_OR_BROKEN_PROVENANCE",
            c2pa_summary={"present": True, "validation": "FAILED"},
            **base,
        )
        self.assertLess(bad["trust_score"], good["trust_score"])


if __name__ == "__main__":
    unittest.main()