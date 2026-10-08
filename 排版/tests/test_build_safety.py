"""回归检查：构建不改动来源稿，缺失拼页输入、错误字体或依赖写法须报错，生成的字体可复现。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

LAYOUT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAYOUT))
import preflight


def load_issue(issue: str):
    folder = LAYOUT / issue
    sys.path.insert(0, str(folder))
    sys.modules.pop("art", None)
    name = "build_" + issue
    spec = importlib.util.spec_from_file_location(name, folder / "build.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    sys.path.remove(str(folder))
    return module


class BuildSafety(unittest.TestCase):
    def test_changed_source_is_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "第二期").mkdir()
            index = tmp / "第二期/目录.md"
            index.write_text("原目录", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "第二期/目录.md"):
                with preflight.sources_unchanged(tmp):
                    index.write_text("被构建改写", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "第二期/新文件.md"):
                with preflight.sources_unchanged(tmp):
                    (tmp / "第二期/新文件.md").write_text("", encoding="utf-8")
            with preflight.sources_unchanged(tmp):
                pass

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
                     patch.object(module, "prepare_fonts"), patch.object(module, "render_pdf") as renderer, \
                     patch.object(sys, "argv", ["build.py", "第一期"]):
                    with self.assertRaisesRegex(FileNotFoundError, missing):
                        module.main()
                    renderer.assert_not_called()
                    self.assertFalse((tmp / "out").exists())

    def test_second_issue_needs_only_its_title_page(self):
        module = load_issue("第二期")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "排版/封面").mkdir(parents=True)
            with patch.object(module, "ROOT", tmp), patch.object(module, "prepare_fonts"), \
                 patch.object(module, "render_pdf") as renderer, patch.object(sys, "argv", ["build.py", "第二期"]):
                with self.assertRaisesRegex(FileNotFoundError, "第二期扉页.pdf"):
                    module.main()
                renderer.assert_not_called()
            with patch.object(module, "ROOT", tmp), patch.object(module, "prepare_fonts"), \
                 patch.object(module, "require_single_page") as required, patch.object(module, "build"), \
                 patch.object(module, "sources_unchanged"), patch.object(sys, "argv", ["build.py", "第二期"]):
                module.main()
                self.assertEqual(required.call_args.args[0], [tmp / "排版/封面/第二期扉页.pdf"])

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

    def test_requirements_allow_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "requirements.txt").write_text("# 锁定版本\n\npymupdf==1.28.2  # PDF\nPillow == 12.3.0\n",
                                                  encoding="utf-8")
            with patch.object(preflight, "HERE", tmp):
                self.assertEqual(preflight.requirements(), {"pymupdf": "1.28.2", "Pillow": "12.3.0"})
            (tmp / "requirements.txt").write_text("pymupdf>=1.28\n", encoding="utf-8")
            with patch.object(preflight, "HERE", tmp):
                with self.assertRaisesRegex(ValueError, "包名==版本"):
                    preflight.requirements()

    def test_preflight_loads_before_dependencies_are_installed(self):
        # 依赖没装时也要能载入 preflight，好给出安装提示，而不是 ImportError
        code = ("import sys; sys.modules['pymupdf'] = None; sys.modules['fontTools'] = None; "
                f"sys.path.insert(0, {str(LAYOUT)!r}); import preflight")
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_same_output_image_with_different_crop_is_fatal(self):
        module = load_issue("第二期")
        photo = LAYOUT.parent / "资产/配图/2019校园_窗外_鄞中电视台.jpg"
        with tempfile.TemporaryDirectory() as tmp, patch.object(module, "IMG_DIR", Path(tmp)), \
             patch.object(module, "_PROCESSED", {}):
            module.process_image(photo, out_name="x.jpg")
            module.process_image(photo, out_name="x.jpg")          # 同一组参数：直接复用
            with self.assertRaisesRegex(RuntimeError, "x.jpg"):
                module.process_image(photo, (0, 0, 0.5, 0.5), out_name="x.jpg")

    def test_generated_font_matches_manifest(self):
        name = "YZLatin-Italic-350.ttf"
        expected = json.loads((preflight.FONTS / "manifest.json").read_text(encoding="utf-8"))[name]
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / name
            preflight.make_static_font(name, dest)
            self.assertEqual(hashlib.sha256(dest.read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
