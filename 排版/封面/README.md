### 封面与扉页制作

两期扉页和封面使用同一套制作程序；扉页是在内页完成后另行制作、拼入的内容。

| 文件 | 用途 |
| --- | --- |
| `make_pages.py` | 第一期《云图试骏》封面与扉页 HTML。 |
| `make_issue2.py` | 第二期《骋风逐曜》封面与扉页 HTML。 |
| `fontprep.py` | 将封面用到的字体转成静态 TrueType 子集。 |
| `build.sh` | 调用上面程序，以 Chrome 输出 PDF 与 PNG。 |

```bash
cd 排版/封面
./build.sh
```

需要 `python3`、`uv` 和 Google Chrome，可用 `CHROMIUM_EXECUTABLE` 指定浏览器路径。默认读取制作机器 `~/Library/Fonts` 中的字体：思源宋体 SemiBold／Bold／Heavy、Noto Serif 可变字体、方正恒仿宋、FW筑紫E老明朝及金陵刻经W；朱雀仿宋作为备用。字体未齐时先补足本机字体。

输出默认放在本目录，或以 `OUT` 指定另一个已有或新建位置。PDF、PNG、临时 HTML 与字体子集均不提交；正式成品只在 Release 提供。生成的 `第一期封面.pdf`、两期 `扉页.pdf` 可供内页脚本拼页或封面线稿复用。
