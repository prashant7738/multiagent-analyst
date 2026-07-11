import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt

from agents import agent_4


class TestAgent4ChartOverwrite(unittest.TestCase):
    def test_save_removes_existing_chart_before_writing_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = agent_4.CHARTS_DIR
            agent_4.CHARTS_DIR = tmpdir
            try:
                chart_path = Path(tmpdir) / "correlation_heatmap.png"
                chart_path.write_bytes(b"old chart bytes")

                fig = plt.figure()
                try:
                    with patch.object(agent_4.os, "remove", wraps=agent_4.os.remove) as remove_spy:
                        saved_path = agent_4._save(fig, "correlation_heatmap")
                finally:
                    plt.close(fig)

                self.assertEqual(saved_path, str(chart_path))
                self.assertTrue(chart_path.exists())
                self.assertNotEqual(chart_path.read_bytes(), b"old chart bytes")
                remove_spy.assert_called_once_with(str(chart_path))
            finally:
                agent_4.CHARTS_DIR = original_dir


if __name__ == "__main__":
    unittest.main()
