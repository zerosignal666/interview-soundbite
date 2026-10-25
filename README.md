# Interview Soundbite｜采访同期声选段

A reusable skill for selecting and arranging interview soundbites, with traceable source timecodes and a dependency-free SRT helper.

为各类采访整理可剪辑的同期声：从原话中确定内容重点，组织段落、处理剪口，并按需输出原片定位字幕、成片参考字幕和剪辑单。

题材、时长、语段数量、叙事风格和结尾方式由每次任务决定。适合人物访谈、新闻报道、纪录片、活动采访、经验分享等内容。

## 使用 skill

将本仓库克隆到本地，在支持读取 `SKILL.md` 的工具中加载 [SKILL.md](SKILL.md)。技能目录的安装或发现方式按所使用工具的要求设置；也可直接指定该文件。

```sh
git clone https://github.com/zerosignal666/interview-soundbite.git
```

示例请求：

> 读取 interview-soundbite/SKILL.md，帮我整理这份采访。我要约90秒纯同期声，突出人物在关键选择时的想法，尽量少切，保留原片时间码，并列出排列顺序。

可按任务提供字幕或转写、主题与受众、目标长度、画面条件及其他要求。已有答案会沿用；只有影响选段的关键信息缺失时再澄清。

## 内容与时间码

- 根据用途权衡事实、观点、细节、情绪和人物状态，不固定套用某种题材或结尾。
- 保留原意、来源、条件和时间关系，避免重排后制造原本不存在的陈述。
- 将字幕分句、声音拼接点和画面切换分开考虑。
- 区分原片定位与成片时间轴，并说明尚未回听、看画面或核实的内容。

skill 提供编辑工作流；附带脚本只按已经选定的区间换算时间码。两者均不保证自动剪出、试听或验证音视频。

## 单独使用 SRT 脚本

需要 Python 3.9 或更新版本，无第三方依赖。在仓库根目录运行：

```sh
python scripts/clip_srt.py --source examples/interview.srt --plan examples/selection.json --out output/demo
```

示例对白为虚构内容，只演示文件格式。该方案合计31秒，包含选中长语段内部的停顿；脚本不会自动删词、压缩停顿或变速以贴合目标长度。

输出：

| 文件 | 用途 |
| --- | --- |
| `01_source_timecodes.srt` | 选中字幕按源时间排列，供原采访时间轴定位 |
| `02_edit_timecodes.srt` | 按方案顺序从零拼接，保留段内间隔 |
| `03_edit_sheet.md` | 原话、入出点、时长、顺序与填写的剪口建议 |
| `04_edit_map.json` | 每段和每条字幕的源／成片映射及源文件哈希 |

修改 `selection.json` 中的 `segments` 数组即可调整选段与成片顺序。`first`、`last` 对应源字幕序号，包含两端。已有输出默认不覆盖；明确更新时可加 `--overwrite`。详见 [方案格式与校验边界](references/selection-plan.md)。

脚本每次处理一条源时间轴；多人、多源或音节级细剪需另行确认来源与边界。只有字幕时，无法验证声音接点是否自然、画面是否合适或转写是否正确。

## 验证

```sh
python -m unittest discover -s tests -v
```

测试覆盖段落重排、源／成片映射、段内停顿与多行文本，以及重复、缺失、重叠或重置时间轴等异常。测试使用合成内容，不依赖个人采访素材。

## 协议

本仓库采用 [MIT License](LICENSE)。外部采访音视频及其转写内容不因使用本工具而自动适用此协议。
