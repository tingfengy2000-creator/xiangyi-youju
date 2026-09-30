"""Check maintained file names, relative links and portable script paths."""

import ast
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", "node_modules", ".venv", "venv", "__pycache__", "artifacts"}
CONVENTIONAL = {
    "README.md", "AGENTS.md", "CONTRIBUTING.md", "CHANGELOG.md",
    "ISSUE_TEMPLATE", "pull_request_template.md",
}


class ResourceLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for key, value in attrs if key in {"src", "href"} and value)


def maintained_files(directory):
    for item in sorted(directory.iterdir()):
        if item.name in EXCLUDED:
            continue
        if item.is_dir():
            yield from maintained_files(item)
        else:
            yield item


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    errors = []
    files = list(maintained_files(ROOT))
    links_checked = 0
    for file in files:
        relative = file.relative_to(ROOT)
        for part in relative.parts:
            if part in CONVENTIONAL:
                continue
            if not part.isascii() or not re.fullmatch(r"[a-z0-9._-]+", part):
                errors.append(f"不规范的文件或目录名称：{relative}")
            if "_" in part and not (part == file.name and file.suffix == ".py"):
                errors.append(f"下划线仅用于 Python 文件名：{relative}")
        if file.suffix not in {".md", ".html", ".py", ".cjs", ".js"}:
            continue
        text = file.read_text(encoding="utf-8")
        if file.suffix in {".py", ".cjs", ".js"} and re.search(r"[A-Za-z]:[\\/]Users[\\/]", text):
            errors.append(f"脚本包含个人电脑绝对路径：{relative}")
        if file.suffix == ".py":
            try:
                ast.parse(text, filename=str(relative))
            except SyntaxError as error:
                errors.append(f"Python 语法错误：{relative}: {error}")
        links = []
        if file.suffix == ".md":
            content = re.sub(r"```.*?```", "", text, flags=re.S)
            links = re.findall(r"!?\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", content)
        elif file.suffix == ".html":
            parser = ResourceLinks()
            parser.feed(text)
            links = parser.links
        for link in links:
            parsed = urlsplit(link.strip("<>"))
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (file.parent / unquote(parsed.path)).resolve()
            links_checked += 1
            if not target.is_relative_to(ROOT) or not target.exists():
                errors.append(f"本地链接无效或越出仓库：{relative} -> {link}")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"检查通过：{len(files)} 个维护文件，{links_checked} 个本地链接；命名、脚本路径与 Python 语法有效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
