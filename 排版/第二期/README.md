# 第二期编辑部排版

本目录保存《骋风逐曜》编辑部版本的 HTML → Chromium → PDF 制作源码，来自完成阶段提交 944375c。正文 39 篇，输入目录为第二期的 1_红砖絮语、2_赛道秋声、3_青衿问道、4_思接千载。导读为 0_导读.md，人员表在 0_前置/01_人员表.md，卷尾语在第二期根目录。

build.py 读取稿件、按配图配置量取留白，调用 render.cjs 输出 PDF；art.py 生成线描，fonts.py 使用上一级 fonts/ 中已收录的字体。照片素材在仓库的资产/配图/。

~~~bash
cd 排版/第二期
npm install
npx playwright install chromium
python3 build.py 第二期
~~~

需要 Python 3 及 pymupdf、pillow、fonttools。可用 CHROMIUM_EXECUTABLE 指定本机 Chromium。字体许可见[字体说明](<../fonts/README.md>)。

本次整理没有重新导出 PDF；发布成品和目录页码以现存成品对照记录为准。生成的 HTML、PDF 和版面报告属于后续重建输出。
