"""下载 KaTeX 到 web/vendor/，供离线渲染论文公式。仅需在更新依赖时运行一次。"""
import io
import os
import zipfile

import requests

VERSION = "0.16.11"
BASE = f"https://cdn.jsdelivr.net/npm/katex@{VERSION}/dist"
# 项目根目录（脚本在 scripts/ 下，需上一级）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "vendor")

FILES = {
    "katex.min.js": f"{BASE}/katex.min.js",
    "katex.min.css": f"{BASE}/katex.min.css",
    "contrib/auto-render.min.js": f"{BASE}/contrib/auto-render.min.js",
}


def main() -> None:
    os.makedirs(OUT, exist_ok=True)

    for rel, url in FILES.items():
        dest = os.path.join(OUT, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        with open(dest, "wb") as fh:
            fh.write(r.content)
        print(f"{rel:40s} {len(r.content):>9,} bytes")

    # 字体：CSS 里引用的 woff2
    css = open(os.path.join(OUT, "katex.min.css"), "r", encoding="utf-8").read()
    import re
    fonts = sorted(set(re.findall(r"fonts/([A-Za-z0-9_.-]+\.woff2)", css)))
    print(f"字体文件 {len(fonts)} 个，开始下载…")

    font_dir = os.path.join(OUT, "fonts")
    os.makedirs(font_dir, exist_ok=True)
    for name in fonts:
        r = requests.get(f"{BASE}/fonts/{name}", timeout=60)
        if r.status_code != 200:
            print(f"  跳过 {name} ({r.status_code})")
            continue
        with open(os.path.join(font_dir, name), "wb") as fh:
            fh.write(r.content)

    total = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _dn, fn in os.walk(OUT)
        for f in fn
    )
    print(f"完成，vendor 总计 {total:,} bytes")


if __name__ == "__main__":
    main()
