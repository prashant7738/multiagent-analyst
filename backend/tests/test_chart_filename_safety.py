import os
import tempfile
import unittest
from pathlib import Path

import matplotlib.pyplot as plt

from agents import agent_4
from agents.chart_render_static import render_spec_png
from agents.report_style import safe_filename_component


class TestChartFilenameSafety(unittest.TestCase):
    def test_safe_filename_component_handles_arbitrary_labels(self):
        labels = [
            "Type (Credit/Debit) in Account",
            "../../../etc/passwd",
            "foo\\bar",
            "\x00control",
            "🎉",
            ".",
            "..",
            "x" * 400,
        ]

        for label in labels:
            with self.subTest(label=label):
                component = safe_filename_component(label)
                self.assertTrue(component)
                self.assertNotIn("/", component)
                self.assertNotIn("\\", component)
                self.assertNotIn("\x00", component)
                self.assertNotIn(component, {".", ".."})
                self.assertLessEqual(len(component), 120)

    def test_save_keeps_chart_inside_output_directory_and_disambiguates_labels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = agent_4.CHARTS_DIR
            agent_4.CHARTS_DIR = tmpdir
            try:
                paths = []
                for name in ("Type (Credit/Debit) in Account", "Type Credit/Debit in Account"):
                    fig = plt.figure()
                    try:
                        paths.append(agent_4._save(fig, f"dist_{name}"))
                    finally:
                        plt.close(fig)

                output_dir = Path(tmpdir).resolve()
                self.assertEqual(len(set(paths)), 2)
                for path in paths:
                    resolved = Path(path).resolve()
                    self.assertEqual(resolved.parent, output_dir)
                    self.assertTrue(resolved.is_file())
                    self.assertGreater(resolved.stat().st_size, 0)
            finally:
                agent_4.CHARTS_DIR = original_dir

    def test_static_renderer_sanitizes_chart_spec_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = {
                "id": "../evil/chart",
                "chart_type": "bar",
                "title": "Test",
                "why_it_matters": "Test",
                "data": {"labels": ["A"], "values": [1]},
                "axis": {},
            }

            path = render_spec_png(spec, tmpdir)

            self.assertIsNotNone(path)
            resolved = Path(path).resolve()
            self.assertEqual(resolved.parent, Path(tmpdir).resolve())
            self.assertTrue(resolved.is_file())
            self.assertGreater(os.path.getsize(path), 0)


if __name__ == "__main__":
    unittest.main()