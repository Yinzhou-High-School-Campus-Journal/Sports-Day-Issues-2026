"""回归检查：构建不覆盖来源目录，缺失拼页输入或错误字体必须退出。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

LAYOUT = Path(__file__).resolve().parents[1]
ROOT = LAYOUT.parent
sys.path.insert(0, str(LAYOUT))
import preflight


def load_issue(issue: str):
    folder = LAYOUT / issue
    sys.path.insert(0, str(folder))
    for name in ("art", "fonts"):
        sys.modules.pop(name, None)
    name = "build_" + issue
    spec = importlib.util.spec_from_file_location(name, folder / "build.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    sys.path.remove(str(folder))
    return module


class BuildSafety(unittest.TestCase):
    def test_second_issue_preserves_archive_index(self):
        module = load_issue("第二期")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            shutil.copytree(ROOT / "第二期", tmp / "第二期")
            index = tmp / "第二期/目录.md"
            before = index.read_bytes()
            out = tmp / "排版/第二期"
            out.mkdir(parents=True)
            with patch.object(module, "ROOT", tmp), patch.object(module, "OUT_DIR", out):
                module.write_build_index("第二期", {}, {1: "扉页", 2: "人员表", 3: "目录", 4: "空白页"})
            self.assertEqual(index.read_bytes(), before)
            generated = (out / "第二期重建页码.md").read_text(encoding="utf-8")
            self.assertIn("# 第二期重建页码", generated)
            self.assertIn("../../第二期/1_红砖絮语/", generated)

    def test_first_issue_stops_before_render_when_frontmatter_missing(self):
        module = load_issue("第一期")
        for present in ("第一期封面.pdf", "第一期扉页.pdf"):
            with self.subTest(present=present), tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                folder = tmp / "排版/封面"
                folder.mkdir(parents=True)
                (folder / present).write_bytes(b"placeholder: must not be opened before existence checks")
                missing = "第一期扉页.pdf" if present == "第一期封面.pdf" else "第一期封面.pdf"
                with patch.object(module, "ROOT", tmp), patch.object(module, "OUT_DIR", tmp / "out"), \
                     patch.object(module, "render_pdf") as renderer, patch.object(sys, "argv", ["build.py", "第一期"]):
                    with self.assertRaisesRegex(FileNotFoundError, missing):
                        module.main()
                    renderer.assert_not_called()
                    self.assertFalse((tmp / "out").exists())

    def test_font_version_mismatch_is_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            expected = hashlib.sha256(b"locked version").hexdigest()
            (tmp / "manifest.json").write_text(json.dumps({"test.ttf": expected}))
            (tmp / "test.ttf").write_bytes(b"different version")
            with patch.object(preflight, "FONTS", tmp):
                with self.assertRaisesRegex(RuntimeError, "字体版本不符"):
                    preflight.check_fonts()
                (tmp / "test.ttf").unlink()
                with self.assertRaisesRegex(RuntimeError, "缺少字体"):
                    preflight.check_fonts()


if __name__ == "__main__":
    unittest.main()
