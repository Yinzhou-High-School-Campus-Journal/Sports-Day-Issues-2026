import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pdf_metadata import ROOT, build_epoch, document_metadata, outline_from_html, save_pdf, set_page_labels


class MetadataConsistency(unittest.TestCase):
    def test_both_issues_use_shared_format(self):
        for issue, name in [('第一期', '云图试骏'), ('第二期', '骋风逐曜')]:
            for part in ['内页', '正文', '封面', '扉页', '含封面预览']:
                m = document_metadata(issue, part, 'Actual producer')
                self.assertEqual(m['title'], f'校运会特刊 {issue} {name} {part}')
                self.assertEqual(m['producer'], 'Actual producer')
                self.assertEqual(m['author'], '《鄞年・思叙》编辑部')
                self.assertIn('校园运动会特别刊物', m['subject'])


class Reproducible(unittest.TestCase):
    EPOCH = "1791389674"                  # 2026-10-07 16:14:34 UTC

    def setUp(self):
        build_epoch.cache_clear()
        self.addCleanup(build_epoch.cache_clear)

    def test_dates_follow_source_date_epoch(self):
        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": self.EPOCH}):
            m = document_metadata('第一期', '内页')
        self.assertEqual(m['creationDate'], "D:20261007161434+00'00'")
        self.assertEqual(m['modDate'], m['creationDate'])

    @unittest.skipUnless(shutil.which('git') and (ROOT / '.git').exists(), '需要 Git 仓库')
    def test_dates_default_to_last_commit(self):
        with patch.dict(os.environ):
            os.environ.pop('SOURCE_DATE_EPOCH', None)
            commit = subprocess.run(['git', '-C', str(ROOT), 'log', '-1', '--format=%ct'],
                                    capture_output=True, text=True, check=True).stdout
            self.assertEqual(build_epoch(), int(commit))

    def test_save_is_byte_identical(self):
        """输入带着按时间生成的 /ID（Chromium 的输出就是这样），隔一秒保存两次，字节仍相同。"""
        def save(path):
            doc = pymupdf.open()
            doc.new_page().insert_text((72, 72), 'Sports Day')
            doc = pymupdf.open('pdf', doc.tobytes())
            doc.set_metadata(document_metadata('第二期', '内页', 'Producer'))
            save_pdf(doc, path)
            return path.read_bytes()

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"SOURCE_DATE_EPOCH": self.EPOCH}):
            first = save(Path(tmp, 'a.pdf'))
            time.sleep(1.1)
            second = save(Path(tmp, 'b.pdf'))
        self.assertEqual(first, second)
        self.assertIn(b'/ID[<', first)
        # 不写空的关键词、陷印等条目
        self.assertNotIn(b'/Keywords', first)
        self.assertNotIn(b'/Trapped', first)


class PageLabels(unittest.TestCase):
    def labels(self, pages, uncounted):
        doc = pymupdf.open()
        for _ in range(pages):
            doc.new_page()
        set_page_labels(doc, uncounted)
        doc = pymupdf.open("pdf", doc.tobytes())

        def decode(label):    # PyMuPDF 对十六进制串原样返回 <FEFF…>，阅读器显示为中文
            if label.startswith("<FEFF") and label.endswith(">"):
                return bytes.fromhex(label[5:-1]).decode("utf-16-be")
            return label
        return [decode(doc[i].get_label()) for i in range(pages)]

    def test_title_page_then_numbers(self):
        self.assertEqual(self.labels(4, {1: '扉页'}), ['扉页', '1', '2', '3'])

    def test_several_uncounted_pages(self):
        self.assertEqual(self.labels(6, {1: '扉页', 2: '人员表', 3: '目录', 4: '空白页'}),
                         ['扉页', '人员表', '目录', '空白页', '1', '2'])


class Outline(unittest.TestCase):
    def test_titles_come_from_html(self):
        html = '<h1 class="title">凌汐</h1><h2>（三<span class="hw">）</span></h2><h2>A &amp; B</h2>'
        toc = [[1, '凌汐', 1], [2, '（三（三））', 2], [2, 'A & B', 3]]
        self.assertEqual(outline_from_html(toc, html), [[1, '凌汐', 1], [2, '（三）', 2], [2, 'A & B', 3]])

    def test_mismatched_count_is_fatal(self):
        with self.assertRaises(RuntimeError):
            outline_from_html([[1, '甲', 1]], '<h1>甲</h1><h2>乙</h2>')


if __name__ == '__main__':
    unittest.main()
