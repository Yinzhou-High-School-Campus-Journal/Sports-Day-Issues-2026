import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pdf_metadata import document_metadata

class MetadataConsistency(unittest.TestCase):
    def test_both_issues_use_shared_format(self):
        for issue, name in [('第一期', '云图试骏'), ('第二期', '骋风逐曜')]:
            for part in ['内页', '正文', '封面', '扉页', '含封面预览']:
                m = document_metadata(issue, part, 'Actual producer')
                self.assertEqual(m['title'], f'校运会特刊 {issue} {name} {part}')
                self.assertEqual(m['producer'], 'Actual producer')
                self.assertEqual(m['author'], '鄞州中学媒体部')
    def test_note_and_common_fields(self):
        a = document_metadata('第一期', '内页')
        b = document_metadata('第二期', '内页', note='（页码用齐线数字）')
        for key in ['author', 'subject', 'creator']:
            self.assertEqual(a[key], b[key])
        self.assertTrue(b['title'].endswith('（页码用齐线数字）'))
