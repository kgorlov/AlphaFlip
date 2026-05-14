import argparse
import struct
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from apps.dashboard_screenshot_smoke import (
    PNG_SIGNATURE,
    _parse_size,
    build_parser,
    run,
    validate_png,
)


class DashboardScreenshotSmokeTests(TestCase):
    def test_parse_size_requires_positive_dimensions(self) -> None:
        self.assertEqual(_parse_size("390x900"), (390, 900))
        with self.assertRaises(SystemExit):
            _parse_size("390")
        with self.assertRaises(SystemExit):
            _parse_size("0x900")

    def test_validate_png_reads_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shot.png"
            path.write_bytes(_png_header(320, 240) + b"payload")

            result = validate_png(path)

        self.assertEqual(result["width"], 320)
        self.assertEqual(result["height"], 240)
        self.assertTrue(result["valid_png"])

    def test_run_captures_desktop_and_mobile_with_safety_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dashboard = root / "dashboard.html"
            browser = root / "chrome.exe"
            desktop = root / "desktop.png"
            mobile = root / "mobile.png"
            dashboard.write_text("<!doctype html><html><body>ok</body></html>", encoding="utf-8")
            browser.write_text("", encoding="utf-8")
            args = argparse.Namespace(
                dashboard=str(dashboard),
                browser=str(browser),
                desktop_out=str(desktop),
                mobile_out=str(mobile),
                desktop_size="1440x900",
                mobile_size="390x900",
                out=None,
            )

            def fake_capture(_browser, _dashboard, viewport, _user_data_dir):
                viewport.out.write_bytes(_png_header(viewport.width, viewport.height) + b"payload")

            with patch("apps.dashboard_screenshot_smoke.capture_screenshot", side_effect=fake_capture):
                result = run(args)

        self.assertEqual(len(result["captures"]), 2)
        self.assertEqual(result["captures"][0]["name"], "desktop")
        self.assertEqual(result["captures"][1]["width"], 390)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["orders_submitted"])
        self.assertFalse(result["orders_cancelled"])
        self.assertFalse(result["live_trading_enabled"])

    def test_parser_defaults_are_local_report_paths(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.dashboard, "reports/dashboard.html")
        self.assertEqual(args.desktop_out, "reports/dashboard_desktop_smoke.png")
        self.assertEqual(args.mobile_out, "reports/dashboard_mobile_smoke.png")


def _png_header(width: int, height: int) -> bytes:
    return PNG_SIGNATURE + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
