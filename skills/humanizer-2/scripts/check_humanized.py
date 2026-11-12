#!/usr/bin/env python3
"""Humanizer 2.0 检查脚本。

用法:
    python -I check_humanized.py <原文.md> <精简稿.md> [--round 1|2] [--deletions deletions.md]

检查三件事:
  1. 信息有没有丢: 原文里的数字、链接、英文术语/人名/公司名, 精简稿里还在不在。
  2. 长度: 精简稿相对原文的字数比例。
  3. AI 味: 破折号、套路句、整句加粗、"不是X而是Y" 等。

输出 FAIL / WARN / OK。有 FAIL 不交付。
原文里本来就有、精简后确实该删的项目 (比如重复出现的同一个数字只是被合并), 在 ledger 里写明理由即可:
deletions.md 每行 "- 删除: <原样项目> | <理由>", 脚本会把这些项目从"丢失"里剔除。
注意不要跟信息账本 ledger.md 搞混, 账本不传给脚本。
"""
import re
import sys
import argparse
from collections import Counter

TAG_RE = re.compile(r"<[^>\n]{1,400}>")
URL_RE = re.compile(r"https?://[^\s)\]>\"'，。）]+")
FEISHU_FILE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)]+)\)")
NUM_RE = re.compile(
    r"(?<![A-Za-z0-9_.])"
    r"[$£€¥]?\d+(?:[.,]\d+)*(?:\s?[-–~～]\s?\d+(?:[.,]\d+)*)?"
    r"\s?(?:%|‰|倍|万|亿|千|百|[KkMmBb](?![a-z])|年|月|日|天|周|小时|分钟|岁|人|例|名|家|个|种|只|篇|美元|元|mg|kg|g|ml|μm|nm)?"
)
LATIN_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-+/.]*[A-Za-z0-9+]|[A-Z]")
CJK_RE = re.compile(r"[一-鿿]")

# 英文常用词, 不算"术语"
EN_STOP = set("""a an the of and or to in on at by for with from as is are was were be been being this that these those it its
he she they we you i his her their our your them us not no but if then than so such into over under about after before
between through during without within can could may might will would should must do does did done has have had having
which who whom whose what when where why how all any each both more most other some only own same too very just also
up down out off again further once here there new first last one two three per via vs etc e.g i.e""".split())

DASH_RE = re.compile(r"——|—|–| -- ")
CORNER_QUOTE_RE = re.compile(r"[「」『』]")

# 套路句: 用户全局规则 + humanizer-zh 中文清单 + 用户文档里 AI 段落的高频句式
BANNED_PHRASES = [
    "反直觉的是", "值得深思的是", "值得注意的是", "值得一提的是", "需要指出的是", "这背后折射出", "折射出",
    "意义深远", "那么问题来了", "毫无疑问", "归根结底", "综上所述", "总而言之", "总的来说", "一言以蔽之",
    "一句话抓住", "一句话概括", "一句话点破", "一句话总结", "贯穿全书", "贯穿全文", "这正是", "真正的分量",
    "让我们", "接下来我们", "下面我们来", "本文将", "本节将", "如下表所示", "下表对比",
    "赋能", "抓手", "底层逻辑", "闭环", "颗粒度", "沉淀", "痛点", "范式", "悄然", "护城河",
    "不仅仅是", "不只是.{0,20}更", "不仅.{0,20}更是", "核心在于", "说到底",
    "希望对你有帮助", "希望这对你有帮助", "如有需要", "欢迎进一步",
    "留给读者", "开放问题", "未来可期", "拭目以待", "任重道远", "道阻且长",
    "随着.{1,12}的(?:发展|进步|兴起)",
]
NOT_X_BUT_Y_RE = re.compile(
    r"不[是止仅只][^。！？；\n]{1,30}?(?:，\s*(?:而是|而更是|更是)|\s*而是)[^。！？；\n]{1,30}"
)
EMPTY_EMPHASIS = ["极其重要", "至关重要", "举足轻重", "不可或缺", "显著提升", "全面提升", "深刻影响", "重大突破"]

# 英文行(中英对照文档的英文那半)的 slop 词, 取自 blader/humanizer §12 §13 §16 §22
EN_SLOP = [
    r"\bdelve\b", r"\bpivotal\b", r"\bcrucial\b", r"\brobust(?:ly)?\b", r"\btapestry\b",
    r"\btestament\b", r"\bunderscor(?:e|es|ing)\b", r"\bshowcas(?:e|es|ing)\b",
    r"\bmeticulous(?:ly)?\b", r"\bintricate\b", r"\bvibrant\b", r"\bgarner(?:ed|s)?\b",
    r"\bseamless(?:ly)?\b", r"\bleverag(?:e|es|ing)\b", r"\bdeep dive\b",
    r"\bstands as a\b", r"\bserves as\b", r"\bplays a (?:key|vital|crucial) role\b",
    r"\bmarking a\b", r"\ba (?:pivotal|crucial) moment\b", r"\bnestled\b",
    r"\bin the heart of\b", r"\bgroundbreaking\b", r"\bbreathtaking\b",
    r"\bit'?s not (?:just|only|merely)\b", r"\bnot (?:just|only|merely) .{1,40}? but\b",
    r"\bthat is the real\b", r"\blet'?s dive\b", r"\bhere'?s what you need to know\b",
    r"\bI hope this helps\b", r"\bGreat question\b", r"\bit is worth noting\b",
    r"\bthe future looks bright\b", r"\bexciting times\b",
]


def strip_markup(text: str) -> str:
    text = FEISHU_FILE_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    return text


def is_english_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    cjk = len(CJK_RE.findall(s))
    latin = len(re.findall(r"[A-Za-z]", s))
    return cjk == 0 and latin >= 12


def body_len(text: str, cjk_mode: bool):
    """正文长度。中文文档只数中文行(跳过整行英文翻译), 汉字算 1, 英文单词算 1。

    返回 (总长, 汉字数, 英文词数+数字数)。后者是"必保项"的体量: 术语、人名、
    数字一个都不能删, 它们构成这份稿子能压缩到的地板。
    """
    cjk = en = 0
    for line in strip_markup(text).splitlines():
        if cjk_mode and is_english_line(line):
            continue
        cjk += len(CJK_RE.findall(line))
        en += len(re.findall(r"[A-Za-z]+(?:['\-][A-Za-z]+)*", line))
        en += len(re.findall(r"\d+(?:[.,]\d+)*", line))
    return cjk + en, cjk, en


def norm_num(s: str) -> str:
    s = s.replace(" ", "").replace(",", "").replace("–", "-").replace("~", "-").replace("～", "-")
    return s


def extract_numbers(text: str) -> Counter:
    t = strip_markup(text)
    nums = Counter()
    for m in NUM_RE.finditer(t):
        raw = m.group(0).strip()
        core = re.sub(r"[^\d.]", "", raw)
        if not core or core in {".", ""}:
            continue
        # 跳过列表序号 "1." 这类: 单个 1 到 2 位数字且行首
        start = m.start()
        line_start = t.rfind("\n", 0, start) + 1
        prefix = t[line_start:start]
        if re.fullmatch(r"\s*", prefix) and re.fullmatch(r"\d{1,2}", raw) and t[m.end():m.end() + 1] in ".、)":
            continue
        # 跳过章节/问题编号: Chapter 06, 第3节, Q7, Aim 2, 趋势1
        if re.search(r"(?:Chapter|chapter|Part|Section|Aim|Q|Step|第|趋势|观点|难点|知识点|线)\s*$", prefix) \
                and re.fullmatch(r"\d{1,2}", raw):
            continue
        nums[norm_num(raw)] += 1
    return nums


def extract_terms(text: str) -> set:
    t = strip_markup(text)
    terms = set()
    for line in t.splitlines():
        # 只从中文行取术语, 避免整行英文翻译把普通英文单词都算成术语
        if is_english_line(line) and CJK_RE.search(t):
            continue
        # 斜杠/加号拼起来的组合 (margin/ROIC, Aetna+Caremark) 拆开单独比对,
        # 否则会逼着改稿原样照抄这种 AI 腔写法
        for seg in re.split(r"[/+]", line):
            for m in LATIN_TERM_RE.finditer(seg):
                w = m.group(0).strip(".-/")
                if len(w) < 2 or w.lower() in EN_STOP:
                    continue
                terms.add(w)
    return terms


def extract_urls(text: str) -> set:
    urls = set(u.rstrip(".,;") for u in URL_RE.findall(text))
    return urls


def read_ledger(path):
    allowed = set()
    if not path:
        return allowed
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*-\s*删除\s*[:：]\s*(.+?)\s*\|", line)
            if m:
                allowed.add(m.group(1).strip())
    if not allowed:
        print(f"提示: {path} 里没有一行 '- 删除: X | 理由'。"
              f"--deletions 要的是删除清单 deletions.md, 不是信息账本 ledger.md", file=sys.stderr)
    return allowed


def num_present(n: str, draft_nums: Counter, draft_text: str) -> bool:
    if n in draft_nums:
        return True
    core = re.sub(r"[^\d.\-]", "", n)
    return bool(core) and core in norm_num(strip_markup(draft_text))


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("original")
    ap.add_argument("draft")
    ap.add_argument("--round", type=int, default=1, choices=[1, 2])
    ap.add_argument("--already-tight", action="store_true",
                    help="原文本来就不水(常见于用户自己写的稿), 废话已删干净。比例超标从 FAIL 降为 WARN")
    ap.add_argument("--deletions", "--ledger", dest="deletions", default=None,
                    help="删除清单 deletions.md, 每行 '- 删除: 项目 | 理由'。不是信息账本 ledger.md")
    a = ap.parse_args()

    orig = open(a.original, encoding="utf-8").read()
    draft = open(a.draft, encoding="utf-8").read()
    allowed = read_ledger(a.deletions)

    fails, warns, oks = [], [], []
    cjk_mode = len(CJK_RE.findall(orig)) > 200

    # 1. 信息保留
    o_urls, d_urls = extract_urls(orig), extract_urls(draft)
    lost_urls = sorted(u for u in o_urls - d_urls if u not in allowed)
    if lost_urls:
        fails.append(f"链接丢了 {len(lost_urls)} 个 (链接一律保留): " + "; ".join(lost_urls[:10]))
    else:
        oks.append(f"链接 {len(o_urls)} 个全部保留")

    o_nums, d_nums = extract_numbers(orig), extract_numbers(draft)
    lost_nums = sorted(n for n in o_nums if not num_present(n, d_nums, draft) and n not in allowed)
    if lost_nums:
        fails.append(f"数字丢了 {len(lost_nums)} 个 (要么放回, 要么写进删除清单说明理由): " + ", ".join(lost_nums[:40]))
    else:
        oks.append(f"数字 {len(o_nums)} 种全部保留")

    o_terms, d_low = extract_terms(orig), strip_markup(draft).lower()
    lost_terms = sorted(t for t in o_terms if t.lower() not in d_low and t not in allowed)
    if lost_terms:
        level = fails if len(lost_terms) > max(5, len(o_terms) * 0.15) else warns
        level.append(f"英文术语/人名/机构丢了 {len(lost_terms)} 个 (逐个确认是否关键): " + ", ".join(lost_terms[:60]))
    else:
        oks.append(f"英文术语/人名/机构 {len(o_terms)} 个全部保留")

    # 2. 长度
    lo, _, o_keep = body_len(orig, cjk_mode)
    ld, _, _ = body_len(draft, cjk_mode)
    ratio = ld / lo if lo else 1.0
    # 必保项密度: 术语、人名、数字一个都不能删, 密度越高能压的余地越小。
    # 这里只报告密度, 不假装能算出精确下限(手上没有足够样本标定这条曲线)。
    density = o_keep / lo if lo else 0.0
    msg = (f"正文长度 {lo} -> {ld}, 保留 {ratio:.0%}"
           + (" (只数中文行)" if cjk_mode else "")
           + f"；必保项 {o_keep} 个, 密度 {density:.0%}")
    if ratio > 0.90 and not a.already_tight:
        fails.append(msg + " —— 删得不够。确认废话真的删干净了, 是的话加 --already-tight 重跑")
    elif ratio > 0.85:
        warns.append(msg + " —— 偏高" + ("; 已声明 already-tight, 在交付说明里写明原因" if a.already_tight
                                        else ", 再找一遍铺垫、过渡、重复的总结和二次分析"))
    elif ratio < 0.35:
        fails.append(msg + " —— 删过头了, 很可能丢了信息或上下文")
    elif ratio < 0.45:
        warns.append(msg + " —— 删得比较狠, 逐条过账本确认没丢信息和上下文")
    elif ratio > 0.70 and density <= 0.10:
        warns.append(msg + " —— 偏高, 而且原文必保项不算密, 还有空间。先确认铺垫、过渡、重复的总结、"
                           "教科书式定义、带归属的二次分析都压过了, 再看同一件事是不是在几处各讲了一遍")
    elif ratio > 0.70:
        oks.append(msg + " —— 必保项密(约每 10 字 1 个术语或数字), 停在 70% 到 85% 是这类稿子的正常结果")
    else:
        oks.append(msg)

    # 3. AI 味
    body = TAG_RE.sub(" ", URL_RE.sub(" ", draft))
    # 表格里单独一个 "—" 表示无数据, 不算破折号
    body_nodash = re.sub(r"(?<=[|>])\s*[—–-]\s*(?=[|<])", " ", body)
    # 数字区间的 en dash 单独报, 它改法不同 (换成半角连字符)
    range_dash = re.findall(r"\d\s*–\s*\d", body_nodash)
    body_nodash = re.sub(r"(\d)\s*–\s*(\d)", r"\1-\2", body_nodash)
    if range_dash:
        fails.append(f"数字区间用了 – {len(range_dash)} 处: 换成半角连字符, 如 7-12年")
    d = DASH_RE.findall(body_nodash)
    if d:
        fails.append(f"破折号 {len(d)} 处: 改成逗号、冒号、括号或拆句")
    cq = CORNER_QUOTE_RE.findall(body)
    if cq:
        warns.append(f"直角引号「」{len(cq)} 处: 他不用, 改成普通引号或去掉")
    hits = []
    for p in BANNED_PHRASES:
        for m in re.finditer(p, body):
            hits.append(m.group(0))
    if hits:
        fails.append("套路句/黑话: " + ", ".join(sorted(set(hits))))
    nxy = NOT_X_BUT_Y_RE.findall(body)
    if len(nxy) > 1:
        fails.append(f"\"不是X而是Y\"类句式 {len(nxy)} 处 (最多留 1 处, 且两半都要有信息): " + " / ".join(nxy[:5]))
    elif nxy:
        warns.append("\"不是X而是Y\"类句式 1 处, 确认前半句是读者真会有的误解: " + nxy[0])
    emp = [w for w in EMPTY_EMPHASIS if w in body]
    if emp:
        warns.append("空洞强调词: " + ", ".join(emp))

    # 中英对照文档: 英文那半也要过一遍英文 slop 清单
    en_lines = [l for l in strip_markup(draft).splitlines() if is_english_line(l)]
    if en_lines:
        en_text = "\n".join(en_lines)
        en_hits = []
        for p in EN_SLOP:
            en_hits += [m.group(0) for m in re.finditer(p, en_text, re.I)]
        if en_hits:
            warns.append(f"英文行里的 AI 套话 {len(en_hits)} 处: " + ", ".join(sorted(set(en_hits))[:20]))
        en_dash = len(re.findall(r"—|–|\s--\s", en_text))
        if en_dash:
            warns.append(f"英文行里的破折号 {en_dash} 处")

    # 每节允许一句加粗结论: 小节数按原始 draft 里的 ❓callout 和各级标题算
    sections = len(re.findall(r"emoji=\"?❓", draft)) + len(re.findall(r"^#{1,3}\s", draft, re.M))
    bolds = re.findall(r"\*\*([^*\n]+)\*\*", body)
    long_bold = [b for b in bolds if len(b) > 45]
    if len(long_bold) > max(3, sections):
        warns.append(f"长句整句加粗 {len(long_bold)} 处, 小节 {sections} 个: 他只加粗标签和每节一句结论")
    n_lines = max(1, sum(1 for l in body.splitlines() if l.strip()))
    if len(bolds) / n_lines > 0.35:
        warns.append(f"加粗太密: {len(bolds)} 处 / {n_lines} 行")

    # 句长 (只看中文行)
    sents = []
    for line in strip_markup(draft).splitlines():
        if is_english_line(line):
            continue
        for s in re.split(r"[。！？；\n]", line):
            c = len(CJK_RE.findall(s))
            if c:
                sents.append(c)
    if sents:
        avg = sum(sents) / len(sents)
        longs = sum(1 for c in sents if c > 70)
        if avg > 40:
            warns.append(f"中文平均句长 {avg:.0f} 字, 偏长 (他一般 15 到 35 字)")
        if longs:
            warns.append(f"超过 70 字的长句 {longs} 句, 拆开或删修饰")

    # 结构: 二级标题数量
    h2_o = len(re.findall(r"^##\s", orig, re.M))
    h2_d = len(re.findall(r"^##\s", draft, re.M))
    if h2_d > max(4, h2_o):
        warns.append(f"二级标题 {h2_d} 个, 比原文 {h2_o} 个还多: 同类问题该合并到一个大标题下")

    if a.round == 2 and ratio < 0.45:
        warns.append("第 2 轮后保留不到 45%: 再删就容易丢上下文, 停在这一版")

    print("== Humanizer 2.0 检查 ==")
    for x in fails:
        print("FAIL", x)
    for x in warns:
        print("WARN", x)
    for x in oks:
        print("OK  ", x)
    print("结果:", "不通过" if fails else "通过")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
