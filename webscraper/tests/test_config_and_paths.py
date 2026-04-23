import tempfile
import unittest
from pathlib import Path

from webscraper.core.config_loader import load_config
from webscraper.core.paths import ensure_output_dir, runtime_edge_profile_dir, write_run_metadata


class ConfigAndPathsTests(unittest.TestCase):
    def test_load_config_has_expected_defaults(self) -> None:
        cfg = load_config()
        self.assertTrue(hasattr(cfg, "DEFAULT_OUTPUT_DIR"))

    def test_paths_helpers_create_output_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = ensure_output_dir(td)
            self.assertTrue(Path(out).exists())
            edge_tmp = runtime_edge_profile_dir(out)
            self.assertEqual(edge_tmp, str(Path(out) / "edge_tmp_profile"))
            metadata_path = write_run_metadata(out, {"handles": ["ABC"]})
            self.assertTrue(Path(metadata_path).exists())


if __name__ == "__main__":
    unittest.main()
