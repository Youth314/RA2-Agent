#!/usr/bin/env python3
"""由 B 站《红警2单位对照》抽出「注册名 → 中文名」，写 `corpus/derived/names.json`。

那页两种写法都有：建筑段是 `ID 中文名`，单位段是 `中文名----ID`，而且单位段会把
武器名跟在后面（`GAPILL 机枪碉堡---Vulcan2`）。故不靠正则猜边界，而是**拿已知的
注册名去切**——先把候选串的已知前缀切出来，再按「单位/建筑优先于武器」定归属。

    python3 tools/fetch_names.py            # 下载并抽取
    python3 tools/fetch_names.py --check    # 只报覆盖率，不写
"""
import argparse
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RULES = REPO / "corpus" / "derived" / "rules.json"
TARGET = REPO / "corpus" / "derived" / "names.json"

#: 来源页。知乎那份是手抄的，见 corpus/sources/。
SOURCE = "https://www.bilibili.com/opus/853295721256845345"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

#: 中文名：一串汉字，后面可以跟汉字、数字、间隔号、括号。
_CN = r"[\u4e00-\u9fff][\u4e00-\u9fff\w·、（）()]*"


def knowledge():
    """已解析的表：可动单位、建筑、武器。"""
    data = json.loads(RULES.read_text(encoding="utf-8"))
    return (data["units"], data["buildings"], data["weapons"])


def trim(candidate, known):
    """从 `APOC120mmx` 这类里切出已知的注册名；切不出返回 `None`。"""
    for size in range(len(candidate), 1, -1):
        if candidate[:size] in known:
            return candidate[:size]
    return None


def extract(markup, units, buildings, weapons):
    """抽 `注册名 → 中文名`。

    同一个中文名可能既挂到单位又挂到武器（页面写成 `建筑 --- 武器`），
    此时单位与建筑优先——武器只是顺带列出的。
    """
    unit_ids = {u["id"] for u in units}
    building_ids = {b["id"] for b in buildings}
    known = unit_ids | building_ids | set(weapons)
    strong = unit_ids | building_ids

    found = {}
    for block in re.findall(r"<p[^>]*>(.*?)</p>", markup, re.S):
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", block))).strip()
        if not text:
            continue
        pairs = []
        for match in re.finditer(r"(" + _CN + r")\s*-{2,}\s*([A-Za-z0-9_]{2,20})", text):
            ident = trim(match.group(2), known)
            if ident:
                pairs.append((ident, match.group(1).strip()))
        for match in re.finditer(r"(?<![A-Za-z0-9_])([A-Za-z0-9_]{2,20})\s*[=\s]?\s*(" + _CN + r")", text):
            ident = trim(match.group(1), known)
            if ident:
                pairs.append((ident, match.group(2).strip()))
        for ident, name in pairs:
            rank = 0 if ident in strong else 1
            if ident not in found or rank < found[ident][0]:
                found[ident] = (rank, name)
    return {ident: name for ident, (_, name) in sorted(found.items())}


def fetch(url=SOURCE):
    """取来源页。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def main(argv=None):
    parser = argparse.ArgumentParser(description="抽中文名")
    parser.add_argument("--check", action="store_true", help="只报覆盖率")
    args = parser.parse_args(argv)
    if not RULES.exists():
        print(f"缺少 {RULES}。先跑 python3 tools/build_codex.py", file=sys.stderr)
        return 1

    units, buildings, weapons = knowledge()
    names = extract(fetch(), units, buildings, weapons)
    covered = sum(1 for u in units if u["id"] in names)
    print(f"抽出 {len(names)} 条；可动单位 {len(units)} 个里命中 {covered}")

    if args.check:
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps({"source": SOURCE, "names": names},
                                 ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(f"→ {TARGET.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
