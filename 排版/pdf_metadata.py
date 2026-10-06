"""两期及所有输出共用的 PDF 元数据。"""
ISSUE_NAMES = {"第一期": "云图试骏", "第二期": "骋风逐曜"}

def document_metadata(issue: str, part: str, producer: str = "", note: str = "") -> dict[str, str]:
    return {
        "title": " ".join(x for x in ("校运会特刊", issue, ISSUE_NAMES[issue], part, note) if x),
        "author": "鄞州中学媒体部",
        "subject": "鄞州中学第四十四届暨鄞州蓝青高级中学第二十九届运动会校刊",
        "creator": "校运会特刊排版程序（HTML → Chromium）",
        "producer": producer,
    }
