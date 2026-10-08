"""检查可提交 Markdown 的本地链接、代码围栏，以及工作区/提交差异空白。"""

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from scripts.repository_files import versionable_files

ROOT = Path(__file__).resolve().parents[1]


def document_errors(path: Path, root: Path) -> list[str]:
    text = path.read_text()
    errors = []
    fence: tuple[str, int] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if not match:
            continue
        marker, tail = match.groups()
        if fence is None:
            fence = (marker, number)
        elif marker[0] == fence[0][0] and len(marker) >= len(fence[0]) and not tail.strip():
            fence = None
    if fence:
        errors.append(f"{path.relative_to(root)}:{fence[1]} 未关闭代码围栏")
    for block in MarkdownIt("commonmark").parse(text):
        for token in block.children or []:
            if token.type not in {"link_open", "image"}:
                continue
            href = str(token.attrGet("href" if token.type == "link_open" else "src") or "")
            url = urlsplit(href)
            if url.scheme or url.netloc or not url.path:
                continue
            target = (path.parent / unquote(url.path)).resolve()
            if not target.is_relative_to(root) or not target.exists():
                errors.append(f"{path.relative_to(root)} 链接不存在或越出仓库: {href}")
    return errors


def main() -> None:
    errors = []
    docs = [p for p in versionable_files(ROOT) if p.suffix == ".md" and (ROOT / p).exists()]
    for path in docs:
        errors += document_errors(ROOT / path, ROOT)
    commands = [
        ["git", "diff", "--check"],
        ["git", "diff", "--cached", "--check"],
        ["git", "show", "--format=", "--check", "HEAD"],
    ]
    main_ref = subprocess.run(
        ["git", "rev-parse", "--verify", "origin/main"], cwd=ROOT, capture_output=True
    )
    if main_ref.returncode == 0:
        commands.append(["git", "diff", "--check", "origin/main...HEAD"])
    for command in commands:
        check = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        if check.returncode:
            errors.append("Git 差异空白检查失败")
    for error in errors:
        print(error)
    print(f"Markdown: {len(docs)} files, errors={len(errors)}")
    raise SystemExit(int(bool(errors)))


if __name__ == "__main__":
    main()
