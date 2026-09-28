# 排版

《云图试骏》内页用 HTML 排版、Chromium 打印成 PDF。封面和扉页另做（见 `资产/`），不在这里生成。

## 文件

| 文件 | 说明 |
| --- | --- |
| `第一期.html` | 排版源文件（由 `build.py` 从稿件生成，可直接用 Chrome 打开或打印） |
| `style.css` | 版式样式 |
| `第一期内页.pdf` | 印刷用内页 |
| `第一期（含封面预览）.pdf` | 封面 + 扉页 + 内页，仅供翻阅 |
| `第一期版面.json` | 每篇的起止页和末页留白行数 |
| `build.py` | 稿件 → HTML → PDF，自动回填目录页码 |
| `render.cjs` | 调用 Chromium 输出 PDF |
| `fonts.py` | 准备字体（输出到 `fonts/`，不进仓库） |
| `images/` | 处理成灰度的配图 |

## 版式

- A4，页边距上 24.5 mm、下 27.5 mm、内外侧 27.2 mm；版心恰好是双栏各 20 字 × 40 行。
- 正文：思源宋体 Regular + Noto Serif 350，10.5 pt，行距 17.35 pt，首行缩进 21 pt，双栏，栏间距 21 pt，两端对齐。
- 裸大标题（卷首语、致辞、目录）：思源宋体 Bold 18 pt，行距 26.04 pt，段后 3.5 行。
- 大标题：思源宋体 Bold 18 pt，行距 26.04 pt。副标题 12 pt，紧跟大标题。
- 作者：方正恒仿宋 Medium 10.5 pt，行距 17.35 pt，段前段后 2.5 行。
- 中标题：思源宋体 SemiBold 14 pt，行距 17.35 pt，段前段后 1 行，居中。
- 小标题：思源宋体 Medium 12 pt，行距 17.35 pt，段前段后 0.5 行，左齐。
- 标点挤压：`text-spacing-trim: trim-start`（行首开口标点和相邻标点挤压）；样式里同时写了 `trim-both`，浏览器支持后行尾也会压缩（Chromium 141 尚不支持）。
- 中西文自动加空：`text-autospace: normal`。稿件里不要手打中西文之间的空格。
- 每篇另起一页；页眉为栏目名，页脚为页码（内页第 1 页起算）。
- 图片一律转灰度（自动色阶、提亮中间调抵消网点扩大），栏内图高度取整行，保证两栏行线对齐。

## 稿件写法

```markdown
# 标题

2503 作者姓名

——副标题（可选）

---

正文段落……

### 中标题

> 引文或歌词，每行末尾两个空格  
> ——出处

诗行，每行末尾两个空格  
下一行

![说明](../../资产/图片.jpeg)
```

- 文中出现的第一级 `#` 标题排成中标题，第二级排成小标题。
- 整篇都是诗行时，单栏居中排。
- 文末连着两张以上的图，排成通栏并排的图组。
- 引号用「」，嵌套用『』；破折号 `——`、省略号 `……`。

## 生成

需要 Python 3（`pip install pymupdf pillow fonttools`）和 Node.js。

```bash
cd 排版
npm install                      # 安装 Playwright
npx playwright install chromium  # 首次使用时下载 Chromium
python3 fonts.py                 # 下载并生成字体
python3 build.py 第一期
```

方正恒仿宋是商业字体，请把 `FZHengFSJF-R.TTF`、`FZHengFSJF-M.TTF` 放进 `fonts/`；
没有时会退回开源的朱雀仿宋（`ZhuqueFangsong-Regular.ttf`）。
