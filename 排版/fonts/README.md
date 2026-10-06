# 排版字体

本目录保存两期编辑部排版共用的字体。`YZSong-*.ttf` 由 `NotoSerifSC-VF.ttf` 生成；`YZLatin-*.ttf` 由 `NotoSerif-VF.ttf` 和 `NotoSerif-Italic-VF.ttf` 生成。可运行 `../第一期/fonts.py` 重新生成缺失的静态字重。

Noto Serif SC 源字体及静态字重采用 SIL Open Font License 1.1，许可文本见 [OFL-NotoSerifSC.txt](OFL-NotoSerifSC.txt)，第三方说明见 [README-third_party-NotoSerifSC.md](README-third_party-NotoSerifSC.md)；字体版权标识为 © 2017–2024 Adobe。Noto Serif 西文字体及静态字重采用同一许可，文本见 [OFL-NotoSerif.txt](OFL-NotoSerif.txt)，版权标识为 © 2022 The Noto Project Authors。

`CONSTAN*.TTF` 为 Microsoft Constantia，`FZHengFSJF-*.TTF` 为方正恒仿宋。项目维护者确认拥有这些字体在本公开仓库中的再分发授权；它们不受上述开源字体许可覆盖。其他用途须遵守各自的授权条款。

### 封面字体

`封面/CoverSong-*.ttf` 是原封面所用思源宋体 SC 的静态 TrueType 字形子集，字重为 600、700、900；`CoverLatin-*.ttf` 是 Noto Serif 的静态字重子集。原思源宋体的 SIL Open Font License 1.1 文本见 [OFL-SourceHanSerif.txt](OFL-SourceHanSerif.txt)，Noto Serif 的许可见上文。子集沿用原封面的字形；修改封面文字时须确认子集包含新增字。

封面另用 `FW筑紫E老明朝.TTF` 与 `金陵刻经W.ttf`。项目维护者于 2026 年 10 月 6 日确认拥有这两款字体在本公开仓库中的再分发授权；它们不受上述开源许可覆盖，其他用途须遵守各自授权条款。

### 版本校验

`manifest.json` 记录变量源字体、封面静态字体及商业字体的 SHA-256。构建前逐一校验，缺失或不一致时报错。两期的静态 `YZSong-*.ttf`、`YZLatin-*.ttf` 缺失时，由锁定版本的 FontTools 从仓库变量源字体生成；不从网络获取可能变更的字体。
