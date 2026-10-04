# 2026 校运会特刊

本仓库保存《校园运动会特别刊物》2026 年版的稿件、制作材料和版本记录。两期的印刷、发放均已完成。第一期实际付印版为《云途试骏》，编辑部方案为《云图试骏》；第二期为《骋风逐曜》。两种第一期期名照各自成品保留。

此仓库未经媒体部授权，为《鄞年・思叙》编辑部自行上传；归档范围是技术上能够整理和保存的文件。

## 为什么建立仓库

2026 学年媒体部招新后，制作工作面临技术人手与经验不足的问题。《鄞年・思叙》编辑部因此参与了校运会特刊的排版。仓库保存成品稿件，也保留未采用的方案和稿件，希望下一次合作可以追溯取舍与制作过程。

| 参与方 | 主要工作 |
| --- | --- |
| 学校 | 划定框架，决定部分稿件与编排，继续编辑提交后的 PDF |
| 学生会媒体部 | 初审、封面与稿件编排 |
| 《鄞年・思叙》编辑部 | 提供第一期方案，制作第二期编辑部版本并协助校对 |
| 上期执行编辑 | 制作第一期实际采用的排版版本 |

除征稿与仓库整理外，制作工作集中在 2026 年 9 月 28 日夜至 30 日晨。

## 分支与成品

`print` 是默认分支和主说明入口。三条分支分别保存与各自成品对应的稿件，通用规则集中写在此处。

| 分支 | 第一期 | 第二期 | 详细说明 |
| --- | --- | --- | --- |
| `print` | 《云途试骏》，24 篇，实际付印版 | 《骋风逐曜》，39 篇，校方最终编辑版 | 本文 |
| `DuanJiarui` | 与 Print 第一期同一份成品 | 未参与制作，无第二期成品目录 | [分支说明](https://github.com/Yinzhou-High-School-Campus-Journal/Sports-Day-Issues-2026/blob/DuanJiarui/README.md) |
| `ShenZehou` | 《云图试骏》，38 篇，未采用的五板块方案 | 《骋风逐曜》，39 篇，编辑部提交版本 | [分支说明](https://github.com/Yinzhou-High-School-Campus-Journal/Sports-Day-Issues-2026/blob/ShenZehou/README.md) |

第一期 Print／Duan 的现行文件名是 `Sports_Day_Issues_2026_No_1_Print.pdf`，即原 V5。校方与上期执行编辑共同修改第一期，贡献无法从成品中细分；第二期在编辑部提交 PDF 后继续由校方编辑，因此两份文件的字句、板块、选稿和图片都有差异。

逐篇对照见 ShenZehou 的[稿件区别表格](https://github.com/Yinzhou-High-School-Campus-Journal/Sports-Day-Issues-2026/blob/ShenZehou/%E7%A8%BF%E4%BB%B6%E5%8C%BA%E5%88%AB%E8%A1%A8%E6%A0%BC.md)。

## 成品下载

完整发布见 [2026.9.29 Release](https://github.com/Yinzhou-High-School-Campus-Journal/Sports-Day-Issues-2026/releases/tag/2026.9.29)。内页与封面分别提供；以下 PDF 不含封面，首页是扉页。

| 文件 | 内容 | PDF 页数 |
| --- | --- | ---: |
| [Sports_Day_Issues_2026_No_1_Print.pdf](https://github.com/Yinzhou-High-School-Campus-Journal/Sports-Day-Issues-2026/releases/download/2026.9.29/Sports_Day_Issues_2026_No_1_Print.pdf) | 第一期付印版《云途试骏》 | 51 |
| [Sports_Day_Issues_2026_No_2_Print.pdf](https://github.com/Yinzhou-High-School-Campus-Journal/Sports-Day-Issues-2026/releases/download/2026.9.29/Sports_Day_Issues_2026_No_2_Print.pdf) | 第二期付印版《骋风逐曜》 | 59 |
| [Sports_Day_Issues_2026_No_1_ShenZehou.pdf](https://github.com/Yinzhou-High-School-Campus-Journal/Sports-Day-Issues-2026/releases/download/2026.9.29/Sports_Day_Issues_2026_No_1_ShenZehou.pdf) | 第一期编辑部方案《云图试骏》 | 53 |
| [Sports_Day_Issues_2026_No_2_ShenZehou.pdf](https://github.com/Yinzhou-High-School-Campus-Journal/Sports-Day-Issues-2026/releases/download/2026.9.29/Sports_Day_Issues_2026_No_2_ShenZehou.pdf) | 第二期编辑部提交版本《骋风逐曜》 | 60 |

## 文件夹与命名规则

各分支使用同一套规则，板块名称和稿件内容按对应成品确定。

| 位置 | 规则 |
| --- | --- |
| `第一期/`、`第二期/` | 本分支成品实际刊载的稿件、索引与前后置内容。未制作第二期的分支不设第二期成品目录。 |
| `0_前置/` | 人员表、卷首语和开幕式致辞等，以两位数字按刊载顺序编号。 |
| `1_板块名/`、`2_板块名/`…… | 板块用单数字前缀，按成品顺序与实际板块名排列。 |
| `0_导读.md` | 所属板块的导读；没有独立导读的版本不补写。 |
| `01_篇名_班级_作者.md` | 正文在板块内用两位数字编号。题名、班级和姓名按成品记录，未署名时省略缺项。 |
| `目录.md` | 本期稿件链接、刊面页与 PDF 物理页，以发布文件核对。 |
| `卷尾语.md` | 放在期刊根目录，保存该版本的卷尾语。 |
| `待选稿/` | 未进入本分支成品的稿件，去掉旧排序号；旧已过审、未过审归拢至此。未采用导读放在其 `导读/` 子目录。 |
| `信息缺失/` | 未刊载且作者、班级等资料仍缺失的稿件。 |
| `原稿/` | 需要与刊载署名区别的重要原稿，例如正确署名为 2616 吴彦初的《形言》。 |
| `资产/` | 原稿照片、封面、扉页和素材。Print 特有或最终替换图按期收在 `资产/配图/第一期/`、`第二期/`。 |
| `排版/` | 制作源码、字体与历史输出。各分支入口见自己的制作说明；旧 HTML、PDF、版面 JSON 保留当时状态。 |
| `策划/`、`output/` | 早期选稿、审核、封面制作与文本初稿；旧五板块 50 篇方案不代表最终选稿。 |

班级号沿用本项目四位表示法：2026 年刊载时，高一、高二、高三分别对应 26、25、24 开头的班号，“高三（6）班”记为 2406。序号表示阅读顺序。同稿件确实刊于两期或两版时，各自保存刊载文字。

正文保留成品实际字词和分节；字体、网格及生成线描由排版源码负责。ShenZehou 保留原图片引用和配图方式；Print 仅把成品专有或最终替换图提取后嵌入对应稿件，见[新增成品配图](<资产/配图/新增成品配图.md>)。

刊载记录与核实后的作者归属分别保存。《形言》在 Print／Duan 中误署为“高三（6）班 冯欣悦”，成品稿按 2406 冯欣悦归档；正确署名原稿见[原稿/形言_2616_吴彦初.md](<原稿/形言_2616_吴彦初.md>)。

## 本分支目录

| 期刊 | 板块与正文篇数 | 索引 |
| --- | --- | --- |
| 《云途试骏》 | 1_赴新征 7；2_奋云程 6；3_笃前行 4；4_逐韶光 7 | [第一期目录](<第一期/目录.md>) |
| 《骋风逐曜》 | 1_启新章 9；2_竞风华 8；3_踏平川 8；4_溯光行 14 | [第二期目录](<第二期/目录.md>) |

第二期 Print 撤去了《于喘息之间，寻得生命的旷野》，加入《星与路灯》。导读、人员表、卷尾语与部分正文也分别按最终文件归档。

本分支 `排版/` 保留第二期制作源码，输入路径已同步。历史输出来自编辑部制作阶段；校方后来直接编辑 PDF，正式印刷成品以 Release 为准，制作细节见[排版说明](<排版/README.md>)。

第一期历史勘误只保留在 DuanJiarui 的 [V5校样更正.md](https://github.com/Yinzhou-High-School-Campus-Journal/Sports-Day-Issues-2026/blob/DuanJiarui/V5%E6%A0%A1%E6%A0%B7%E6%9B%B4%E6%AD%A3.md)。“V5”仅保留为历史文件名，正文引用采用新成品名。
