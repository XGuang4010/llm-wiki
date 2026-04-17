import os
import re
from pathlib import Path

WIKI_DIR = Path(r"D:\VaultRepos\CyberSecurity\wiki")
TEST_FILE = Path(
    r"D:\VaultRepos\CyberSecurity\wiki\comparisons\安卓强壳脱壳工具链对比.md"
)


def process_markdown(content: str) -> str:
    # 匹配 frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not fm_match:
        return content

    fm_text = fm_match.group(1)
    rest = content[fm_match.end() :]

    # 提取 related 列表项
    related_items = []
    new_fm_lines = []
    in_related = False

    for line in fm_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("related:"):
            in_related = True
            new_fm_lines.append(line)
            continue

        if in_related:
            if stripped.startswith("- "):
                item = stripped[2:].strip()
                # 转换 [[name]] -> name
                item = re.sub(r"^\[\[(.*?)\]\]$", r"\1", item)
                related_items.append(item)
                new_fm_lines.append(f"  - {item}")
                continue
            elif (
                stripped and not stripped.startswith("#") and ":" in stripped.split()[0]
            ):
                # 另一个 key 开始了
                in_related = False
            else:
                in_related = False

        new_fm_lines.append(line)

    if not related_items:
        return content

    new_fm = "\n".join(new_fm_lines)
    new_content = f"---\n{new_fm}\n---\n{rest.rstrip()}\n\n## Related\n\n"
    for item in related_items:
        new_content += f"- {item}\n"

    return new_content


def process_file(path: Path):
    content = path.read_text(encoding="utf-8")
    new_content = process_markdown(content)
    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
        print(f"[UPDATED] {path}")
    else:
        print(f"[SKIP]    {path}")


def run_test():
    test_doc = Path(
        r"D:\VaultRepos\CyberSecurity\wiki\comparisons\TEST_安卓强壳脱壳工具链对比.md"
    )
    import shutil

    shutil.copy2(TEST_FILE, test_doc)
    print(f"Test file created: {test_doc}")
    process_file(test_doc)


def run_all():
    for md_file in WIKI_DIR.rglob("*.md"):
        process_file(md_file)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        run_all()
    else:
        run_test()
        print("\nRun with --all to process all files.")
