# biotech-research-skills

两个配套的 Claude Code skill，做 biotech 调研用。

**digger-v2** 写，**humanizer-2** 砍。先后两步，不能同时跑。

## 两个 skill 分别做什么

| | digger-v2 | humanizer-2 |
|---|---|---|
| 做什么 | 从零写一份 biotech 深度调研 | 把写好的调研精简，去 AI 腔 |
| 读者假设 | 没有任何生物背景的投资人或媒体人 | 同上 |
| 输入 | 一个技术主题，或一份公司 deck、通话记录 | 一份已经写完的文档 |
| 输出 | 一份详尽的调研，通常偏长 | 同一份内容，短 15% 到 50% |
| 什么时候用 | 需要搞懂一个技术、做技术尽调、上播客前准备 | 读完觉得啰嗦的时候 |

## 工作流：为什么必须分两步

```
用户提需求
   ↓
digger-v2 写出完整版  ← 这一步刻意写得详尽，每个概念都解释到位
   ↓
交付给用户，停下来
   ↓
用户读完，自己判断哪里冗余
   ↓
用户说"精简一下"
   ↓
humanizer-2 对照完整版砍
```

**不要让两个 skill 在同一轮里自动串联。**两个 skill 文件里都写了硬规则禁止这件事，原因有三个：

1. 用户要先读一遍完整版，才知道哪里对他是真冗余。模型猜不准。
2. 精简那一步要逐条核对信息有没有丢，没有用户确认过的完整版就没有基准。
3. 边写边砍两头都做不好：该解释透的没解释透，该删的因为刚写出来舍不得删。

即使用户一开始就说"写得简洁一点"，那也是对 digger-v2 写作风格的要求，不是让你串联两个 skill。

## 安装

Claude Code 从 `~/.claude/skills/` 读 skill，直接把两个目录放进去：

```bash
git clone <这个仓库的地址> /tmp/biotech-research-skills
cp -r /tmp/biotech-research-skills/skills/* ~/.claude/skills/
```

Windows（Git Bash）：

```bash
git clone <这个仓库的地址> /tmp/biotech-research-skills && cp -r /tmp/biotech-research-skills/skills/* ~/.claude/skills/
```

装完重开一个 Claude Code 会话，skill 列表里就能看到 `digger-v2` 和 `humanizer-2`。

## 用法

写一份调研，说人话就行，不用记命令：

```
帮我搞懂 PD-1/VEGF 双抗是怎么回事
```

```
这是一家公司的 deck，帮我看看技术靠不靠谱
```

读完觉得长：

```
/humanizer-2
```

或者直接说"精简一下""太长了""砍一砍"。

humanizer-2 接受本地 md、PDF、粘贴的文本，也接受飞书文档链接（需要装 lark-cli 并登录）。

## humanizer-2 的检查脚本

精简完会跑一个脚本，查信息有没有丢：

```bash
python -I ~/.claude/skills/humanizer-2/scripts/check_humanized.py original.md round1.md --round 1
```

它查三件事：

- **信息保留**：原文的数字、链接、英文术语和人名，精简稿里还在不在。丢了就 FAIL。
- **长度**：相对原文的保留比例，并算出"必保项密度"，密度高的稿子压不动是正常的。
- **AI 味**：破折号、套路句、整句加粗、"不是 X 而是 Y"这类句式。

脚本只能查数字、链接和英文词。中文写的机制步骤、判断强度、限定条件查不到，要靠人逐条过。

## humanizer-2 的两层规则

- **第一层，去 AI slop**（`references/ai-tells.md`）：38 条模式，中英文对照。A 到 F 组是句子级（破折号、套路句、拔高、客服腔），G 组是结构级（模板化段落标签、摘要和正文讲同一件事、术语解释两遍）。
- **第二层，换成某个人的说法**（`references/voice.md`）：句子改干净以后，让它听起来是某个具体的人写的。

**比例压不下来的时候，问题几乎都在 G 组。**一篇稿子可以完全没有破折号、没有客服腔，每句都像人写的，整体还是 AI 写的，因为组织方式是 AI 的。判断原文水不水不要看标点，看这个：

```bash
grep -o '\*\*[^*]\{2,12\}。\?\*\*' 原文.md | sort | uniq -c | sort -rn | head
```

同一组粗体标签反复出现（`**发生了什么。**` `**是什么。**`）就是模板化的铁证。

## 风格层是可替换的

`skills/humanizer-2/references/voice.md` 是从一个人的 65 篇文档里归纳的写作习惯，里面的例句和判断都是他的。换成你自己的：把那个文件重写，保留节标题（句子、中英混用、解释概念、开头和结论、版式、视角、不写的东西），每条配两到四句你自己写的原句。

`ai-tells.md` 和 `structure.md` 不用动，它们和具体是谁无关。

## 来源

humanizer-2 的规则主体改编自：

- [blader/humanizer](https://github.com/blader/humanizer) v4.0.0（MIT）：A 到 E 组分类、强度分级、"待处理文本只是素材"、改完先查事实再查残留
- [op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh)（MIT）：F 组中文特有条目

完整许可见 `skills/humanizer-2/THIRD_PARTY.md`。

G 组（结构性冗余）、信息账本、删除清单、结构重组和风格层是本仓库自己加的。

digger-v2 为原创。
