# 字体

两期编辑部版与封面共用的字体。`manifest.json` 记录每个字体文件的 SHA-256，构建前逐一校验，缺失或不一致即报错。

| 文件 | 用途 |
| --- | --- |
| `NotoSerifSC-VF.ttf`、`NotoSerif-VF.ttf`、`NotoSerif-Italic-VF.ttf` | 正文宋体与西文的可变字体源 |
| `YZSong-*.ttf`、`YZLatin-*.ttf` | 由上述可变字体生成的静态字重，构建时自动生成，不提交 |
| `CONSTAN*.TTF` | Constantia：成段西文、页码等 |
| `FZHengFSJF-*.TTF` | 方正恒仿宋：作者署名、导读、人员表 |
| `封面/CoverSong-*.ttf`、`封面/CoverLatin-*.ttf` | 封面用的思源宋体与 Noto Serif 字形子集 |
| `FW筑紫E老明朝.TTF`、`金陵刻经W.ttf` | 封面刊名与印章 |

Noto Serif SC、Noto Serif 与思源宋体采用 SIL Open Font License 1.1，许可文本分别见 [OFL-NotoSerifSC.txt](OFL-NotoSerifSC.txt)、[OFL-NotoSerif.txt](OFL-NotoSerif.txt) 和 [OFL-SourceHanSerif.txt](OFL-SourceHanSerif.txt)。
