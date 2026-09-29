#!/usr/bin/env python3
"""拉取原始语料：原版 INI + ModEnc + C&C Fandom 的 RA2/YR 部分。

只用标准库。产物落 `corpus/raw/`（已 gitignore；来源与指纹见 `corpus/README.md`）。

**这是原始语料，不是给人看的文档。** 加工产物另行处理。

可重复运行：每页带 pageid，已取到的跳过。

    python3 tools/fetch_corpus.py                 # 三样都取
    python3 tools/fetch_corpus.py --only modenc   # 只取一样
    python3 tools/fetch_corpus.py --only modenc --max 60   # 冒烟
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "corpus" / "raw"

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MODENC = "https://modenc.renegadeprojects.com/api.php"
FANDOM = "https://cnc.fandom.com/api.php"

#: YR 1.001 的原版 INI，上游镜像。
INI_BASE = "https://raw.githubusercontent.com/DeathFishAtEase/yr-original-ini/1.001"
INI_FILES = ("rulesmd.ini", "artmd.ini", "aimd.ini")

#: Fandom 上与本项目有关的分类前缀。
FANDOM_CATEGORIES = ("Red Alert 2", "Yuri's Revenge")
#: 纯素材分类，对决策没用，跳过。
FANDOM_SKIP = ("images", "cameos", "videos", "sounds", "icons", "art", "beta")

#: 请求之间的间隔。对公共 wiki 客气一点。
DELAY = 0.3
#: 单次请求的重试次数。
RETRIES = 4


def api(base, params):
    """调一次 MediaWiki API，失败按指数退避重试。"""
    url = base + "?" + urllib.parse.urlencode(params)
    for attempt in range(RETRIES):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError) as error:
            if attempt == RETRIES - 1:
                raise
            wait = 2 ** attempt
            print(f"  重试 {attempt + 1}/{RETRIES}（{error}），等 {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise AssertionError("unreachable")


def page_record(page, wiki):
    """把一页压成一条记录；正文取不到就跳过。"""
    revisions = page.get("revisions") or []
    if not revisions:
        return None
    content = revisions[0].get("slots", {}).get("main", {}).get("content")
    if not content:
        return None
    return {
        "wiki": wiki,
        "pageid": page["pageid"],
        "title": page["title"],
        "url": f"https://{wiki}/wiki/" + urllib.parse.quote(page["title"].replace(" ", "_")),
        "content": content,
    }


def load_done(path):
    """已落盘的 pageid，用于断点续跑。"""
    if not path.exists():
        return set()
    done = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                done.add(json.loads(line)["pageid"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def append_records(path, records):
    """追加若干条记录。"""
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def want_category(name):
    """这个分类要不要跟进：属于 RA2/YR，且不是纯素材。"""
    if not any(name.startswith(prefix) for prefix in FANDOM_CATEGORIES):
        return False
    lowered = name.lower()
    return not any(skip in lowered for skip in FANDOM_SKIP)


def fetch_ini():
    """取三份原版 INI。"""
    RAW.mkdir(parents=True, exist_ok=True)
    for name in INI_FILES:
        target = RAW / name
        request = urllib.request.Request(f"{INI_BASE}/{name}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=120) as response:
            target.write_bytes(response.read())
        print(f"  {name}  {target.stat().st_size} B")


def fetch_modenc(max_pages, out):
    """ModEnc 主命名空间全量。"""
    done = load_done(out)
    print(f"ModEnc：已取 {len(done)} 页")
    params = {"action": "query", "generator": "allpages", "gaplimit": 50,
              "gapnamespace": 0, "prop": "revisions", "rvslots": "main",
              "rvprop": "content|timestamp", "format": "json", "formatversion": 2}
    fetched = 0
    while True:
        data = api(MODENC, params)
        records = [r for r in (page_record(p, "modenc.renegadeprojects.com")
                               for p in data.get("query", {}).get("pages", []))
                   if r is not None and r["pageid"] not in done]
        append_records(out, records)
        done.update(r["pageid"] for r in records)
        fetched += len(records)
        print(f"  {fetched} 页", flush=True)
        if max_pages and fetched >= max_pages:
            return
        params.update(data.get("continue") or {})
        if "continue" not in data:
            return
        time.sleep(DELAY)


def fetch_fandom(max_pages, out):
    """C&C Fandom：只走 RA2/YR 那几个分类，含子分类。"""
    done = load_done(out)
    print(f"Fandom：已取 {len(done)} 页")
    pending = [f"Category:{name}" for name in FANDOM_CATEGORIES]
    visited = set()
    fetched = 0
    while pending:
        category = pending.pop(0)
        if category in visited:
            continue
        visited.add(category)
        params = {"action": "query", "generator": "categorymembers",
                  "gcmtitle": category, "gcmlimit": 500, "gcmtype": "page|subcat",
                  "prop": "revisions", "rvslots": "main",
                  "rvprop": "content|timestamp", "format": "json", "formatversion": 2}
        while True:
            data = api(FANDOM, params)
            pages = data.get("query", {}).get("pages", [])
            records = [r for r in (page_record(p, "cnc.fandom.com") for p in pages)
                       if r is not None and r["pageid"] not in done]
            append_records(out, records)
            done.update(r["pageid"] for r in records)
            fetched += len(records)
            for page in pages:
                title = page["title"]
                if title.startswith("Category:") and want_category(title[len("Category:"):]):
                    if title not in visited:
                        pending.append(title)
            print(f"  {category} → 累计 {fetched} 页，待走 {len(pending)} 个分类", flush=True)
            if max_pages and fetched >= max_pages:
                return
            params.update(data.get("continue") or {})
            if "continue" not in data:
                break
            time.sleep(DELAY)
        time.sleep(DELAY)


def main(argv=None):
    parser = argparse.ArgumentParser(description="拉取 ra2 原始语料")
    parser.add_argument("--only", choices=("ini", "modenc", "fandom"),
                        action="append", help="只取指定部分，可重复")
    parser.add_argument("--max", type=int, default=0, help="每部分最多取多少页（冒烟用）")
    args = parser.parse_args(argv)
    stages = args.only or ["ini", "modenc", "fandom"]
    for stage in stages:
        print(f"[{stage}]")
        if stage == "ini":
            fetch_ini()
        elif stage == "modenc":
            fetch_modenc(args.max, RAW / "modenc" / "pages.jsonl")
        else:
            fetch_fandom(args.max, RAW / "fandom" / "pages.jsonl")
    print("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
