import os
import re
from pathlib import Path

WIKI_DIR = Path(r"D:\VaultRepos\CyberSecurity\wiki")


def process_related_section(content: str) -> str:
    # 查找 ## Related 章节
    match = re.search(
        r"^(## Related\s*\n)(.*?)(?=\n## |\Z)", content, re.MULTILINE | re.DOTALL
    )
    if not match:
        return content

    header = match.group(1)
    section = match.group(2)

    new_lines = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            # 如果已经是 [[...]] 则跳过，否则加上
            if not (item.startswith("[[") and item.endswith("]]")):
                item = f"[[{item}]]"
            new_lines.append(f"- {item}")
        else:
            new_lines.append(line)

    new_section = header + "\n".join(new_lines) + "\n"
    return content[: match.start()] + new_section + content[match.end() :]


def process_file(path: Path):
    content = path.read_text(encoding="utf-8")
    new_content = process_related_section(content)
    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
        print(f"[UPDATED] {path}")
    else:
        print(f"[SKIP]    {path}")


def run_all():
    for md_file in WIKI_DIR.rglob("*.md"):
        process_file(md_file)


if __name__ == "__main__":
    run_all()
