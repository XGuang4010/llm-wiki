# llm-wiki Sync 扩展实施计划

> 目标：让 `/wiki sync` 同时收集 `.learning` 和项目下的 `.wiki` 文档，汇总到总 wiki 中。

---

## 一、需求背景

当前 `learning_scanner.py` 只扫描 `.learning` 目录，将自改进学习文件 stage 到总 wiki 的 `raw/articles/` 下。

新需求：同时扫描各项目下的 `.wiki` 目录，把项目本地 wiki 的文档**直接复制**到总 wiki 目录下。

---

## 二、核心设计决策

| 决策项 | 方案 |
|--------|------|
| Index 文件 | `doc_index.json`（替代 `learning_index.json`） |
| 单/多文件 | 一个文件同时记录 `.learning` 和 `.wiki` |
| 复制范围 | 只复制 `.wiki` 下的 `raw/` 和 `wiki/` |
| 复制方式 | 平铺合并到总 wiki 对应目录 |
| 冲突处理 | 目标已存在时，后续文件命名为 `foo_1.md`, `foo_2.md`... |
| `wiki/` 冲突后续 | lint workflow 负责合并 |
| `raw/` 冲突后续 | 不处理，保留多版本 |
| 删除策略 | 不同步删除，lint 处理 |
| 同步模式 | 默认增量，支持全量（`--wiki-full-sync`） |
| 旧 index 处理 | 迁移到 `doc_index.json` 后删除 `learning_index.json` |

---

## 三、Index 结构升级（Phase 1）

### 3.1 新结构 `doc_index.json`

```json
{
  "version": 2,
  "created": "2026-04-17T10:00:00+00:00",
  "last_scan": "2026-04-17T10:00:00+00:00",
  "learning_directories": {
    "D:/Projects/Foo/.learning": {
      "error-handling.md": "abc123..."
    }
  },
  "wiki_directories": {
    "D:/Projects/Foo/.wiki": {
      "raw/articles/2026-04-17-bar.md": "def456...",
      "wiki/concepts/baz.md": "789abc..."
    }
  },
  "wiki_targets": {
    "D:/Projects/Foo/.wiki": {
      "raw/articles/2026-04-17-bar.md": "raw/articles/2026-04-17-bar.md",
      "wiki/concepts/baz.md": "wiki/concepts/baz_1.md"
    }
  }
}
```

### 3.2 向后兼容迁移逻辑

在 `load_index()` 中：
1. 如果 `doc_index.json` 存在，直接读取
2. 如果不存在但 `learning_index.json` 存在：
   - 读取旧文件
   - 将 `directories` 重命名为 `learning_directories`
   - 新增 `wiki_directories: {}` 和 `wiki_targets: {}`
   - version 升级为 2
   - 删除旧的 `learning_index.json`
3. 如果都不存在，初始化新的 v2 结构

`save_index()` 始终保存到 `doc_index.json`。

---

## 四、扫描逻辑扩展（Phase 2）

### 4.1 `find_wiki_dirs(root, max_depth=None, exclude=None)`

- 使用 `os.walk` 递归查找 `.wiki` 目录
- `max_depth` 限制搜索深度
- `exclude` 参数用于排除总 wiki 自身的 `.wiki`（避免扫描自己的元数据目录）
- 不进入 `.wiki` 子目录内部继续查找（避免嵌套）

### 4.2 `scan_wiki_dir(wiki_dir, ignore_patterns)`

- 只扫描 `wiki_dir/raw/` 和 `wiki_dir/wiki/`
- 跳过 `ignore_patterns` 匹配的路径
- 额外排除元数据文件：
  - `learning_index.json`
  - `ingest_manifest.json`
  - `doc_index.json`
- 返回 `Dict[相对路径（相对于 wiki_dir）, MD5]`

---

## 五、Wiki 同步逻辑（Phase 3）

### 5.1 `resolve_wiki_target_path(wiki_root, rel_path, occupied_targets)`

输入：
- `wiki_root`: 总 wiki 根目录
- `rel_path`: 源文件相对于 `.wiki` 的相对路径（如 `wiki/concepts/foo.md`）
- `occupied_targets`: `Dict[str, str]`，记录本次同步已分配的目标路径 → 源 wiki 目录

逻辑：
1. `target = wiki_root / rel_path`
2. 如果 `str(target)` 不在 `occupied_targets` 中，且文件不存在于磁盘 → 返回 `target`
3. 否则，从 `_1` 开始递增，尝试 `foo_1.md`, `foo_2.md`... 直到找到未占用的路径
4. 返回最终 `Path`

### 5.2 `sync_wiki_files(items, wiki_root, occupied_targets)`

输入 `items` 是 added/changed 列表，每个 item 格式：
```python
{
    "wiki_dir": "D:/Projects/Foo/.wiki",
    "relative_path": "wiki/concepts/foo.md",
    "md5": "abc123",
    "status": "added"  # or "changed"
}
```

逻辑：
1. 遍历每个 item
2. 调用 `resolve_wiki_target_path()` 获取目标路径
3. `target.parent.mkdir(parents=True, exist_ok=True)`
4. `shutil.copy2(original_file, target_path)`
5. 记录 `occupied_targets[str(target_path)] = item["wiki_dir"]`
6. 收集 manifest 条目返回

返回的 manifest 条目：
```python
{
    "original": "D:/Projects/Foo/.wiki/wiki/concepts/foo.md",
    "wiki_dir": "D:/Projects/Foo/.wiki",
    "relative_path": "wiki/concepts/foo.md",
    "target_path": "wiki/concepts/foo_1.md",
    "status": "added",
    "md5": "abc123"
}
```

### 5.3 全量同步支持

当 `--wiki-full-sync` 启用时：
1. 收集当前扫描到的所有 `.wiki` 文件作为 `wiki_items`
2. 清空 `index_data["wiki_targets"]`
3. `occupied_targets` 初始为空（因为重建映射）
4. 所有文件重新复制

---

## 六、CLI 与主流程重构（Phase 4）

### 6.1 新增 CLI 参数

```python
parser.add_argument(
    "--wiki-full-sync",
    action="store_true",
    default=False,
    help="Force full synchronization of all .wiki files (ignore index)",
)
parser.add_argument(
    "--no-wiki-sync",
    action="store_true",
    default=False,
    help="Skip .wiki directory synchronization",
)
```

### 6.2 默认路径变更

```python
index_path = args.index or wiki_root / ".wiki" / "doc_index.json"
```

### 6.3 `main()` 流程

```python
def main() -> int:
    # ... parse args ...
    
    wiki_root = args.wiki_root.resolve()
    scan_root = (args.scan_root or wiki_root).resolve()
    index_path = args.index or wiki_root / ".wiki" / "doc_index.json"
    manifest_path = args.manifest or wiki_root / ".wiki" / "ingest_manifest.json"
    ignore_patterns = DEFAULT_IGNORE_PATTERNS | set(args.ignore)
    
    # === 1. Scan .learning ===
    learning_dirs = find_learning_dirs(scan_root, max_depth=args.max_depth)
    learning_results = {}
    for ld in learning_dirs:
        learning_results[ld.as_posix()] = scan_learning_dir(ld, ignore_patterns)
    
    # === 2. Scan .wiki ===
    wiki_dirs = find_wiki_dirs(
        scan_root, 
        max_depth=args.max_depth, 
        exclude=wiki_root / ".wiki"
    )
    wiki_results = {}
    for wd in wiki_dirs:
        wiki_results[wd.as_posix()] = scan_wiki_dir(wd, ignore_patterns)
    
    # === 3. Load / migrate index ===
    index_data = load_index(index_path)
    
    # === 4. Diff .learning ===
    learning_added, learning_changed, learning_removed = diff_against_index(
        learning_results,
        {"directories": index_data.get("learning_directories", {})}
    )
    
    # === 5. Diff .wiki ===
    wiki_added, wiki_changed, wiki_removed = diff_against_index(
        wiki_results,
        {"directories": index_data.get("wiki_directories", {})}
    )
    
    # === 6. Auto-stage .learning ===
    learning_manifest = []
    if args.auto_stage and (learning_added or learning_changed):
        learning_manifest = stage_learning_files(
            learning_added, learning_changed, scan_root, wiki_root
        )
        save_manifest(manifest_path, learning_manifest)
        print(f"Staged {len(learning_manifest)} .learning file(s)")
    
    # === 7. Auto-sync .wiki ===
    wiki_manifest = []
    if args.auto_stage and not args.no_wiki_sync:
        if args.wiki_full_sync:
            # 全量模式：所有当前文件都同步
            wiki_items = []
            for wiki_dir_str, files in wiki_results.items():
                for rel_path, md5 in files.items():
                    wiki_items.append({
                        "wiki_dir": wiki_dir_str,
                        "relative_path": rel_path,
                        "md5": md5,
                        "status": "synced",
                    })
            index_data["wiki_targets"] = {}
        else:
            wiki_items = [
                {**item, "wiki_dir": item["learning_dir"], "status": "added"}
                for item in wiki_added
            ] + [
                {**item, "wiki_dir": item["learning_dir"], "status": "changed"}
                for item in wiki_changed
            ]
        
        # 构建已占用映射
        occupied_targets = {}
        for wiki_dir_str, targets in index_data.get("wiki_targets", {}).items():
            for rel_path, target_path in targets.items():
                occupied_targets[str(wiki_root / target_path)] = wiki_dir_str
        
        if wiki_items:
            wiki_manifest = sync_wiki_files(wiki_items, wiki_root, occupied_targets)
            
            # 更新 wiki_targets
            wiki_targets = index_data.setdefault("wiki_targets", {})
            for entry in wiki_manifest:
                wd = entry["wiki_dir"]
                rel = entry["relative_path"]
                wiki_targets.setdefault(wd, {})[rel] = entry["target_path"]
            
            print(f"Synced {len(wiki_manifest)} .wiki file(s)")
    
    # === 8. Update index ===
    if args.update_index:
        index_data["last_scan"] = datetime.now(timezone.utc).isoformat()
        index_data["learning_directories"] = learning_results
        index_data["wiki_directories"] = wiki_results
        save_index(index_path, index_data)
        print(f"Index updated: {index_path}")
    
    # === 9. Build report ===
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "learning": {
                "dirs_found": len(learning_results),
                "files_scanned": sum(len(v) for v in learning_results.values()),
                "added": len(learning_added),
                "changed": len(learning_changed),
                "removed": len(learning_removed),
            },
            "wiki": {
                "dirs_found": len(wiki_results),
                "files_scanned": sum(len(v) for v in wiki_results.values()),
                "added": len(wiki_added),
                "changed": len(wiki_changed),
                "removed": len(wiki_removed),
            }
        },
        "learning": {
            "added": learning_added,
            "changed": learning_changed,
            "removed": learning_removed,
        },
        "wiki": {
            "added": wiki_added,
            "changed": wiki_changed,
            "removed": wiki_removed,
        },
        "manifest": {
            "learning_staged": len(learning_manifest),
            "wiki_synced": len(wiki_manifest),
        }
    }
    
    print(json.dumps(report, indent=2, ensure_ascii=False))
    
    has_changes = bool(learning_added or learning_changed or wiki_added or wiki_changed)
    return 0 if not has_changes else 1
```

### 6.4 注意事项

- `.wiki` 的同步结果**不写入 `ingest_manifest.json`**
- `ingest_manifest.json` 仍然只记录 `.learning` 的 staged 文件
- `.wiki` 的映射关系只保存在 `doc_index.json` 的 `wiki_targets` 中

---

## 七、文档更新（Phase 5）

### 7.1 `RULES.md` 更新点

1. **Quick Reference** 表格：无需改动（`/wiki sync` 描述已在之前更新）

2. **`learning_scanner.py` 使用示例**：
   ```bash
   python scripts/learning_scanner.py --wiki-root ./wiki --output changed_files.json
   ```
   在附近说明默认 index 改为 `doc_index.json`

3. **`/wiki sync` Workflow** 步骤重写：
   ```markdown
   ### `/wiki sync` Workflow
   
   **Trigger:** user says `/wiki sync`, "sync learnings", "ingest from .learning", or the agent runs its startup hook.
   
   This workflow bridges both `.learning` directories and project `.wiki` directories into the total wiki automatically.
   
   **Steps:**
   1. **Run the scanner with auto-stage:**
      ```bash
      python scripts/learning_scanner.py --wiki-root <path> --auto-stage
      ```
      - Scans all `.learning` directories and `.wiki` directories under `--scan-root`.
      - `.learning` files are staged into `raw/articles/YYYY-MM-DD-{safe_slug}.md` with `raw-source` frontmatter.
      - `.wiki` files are directly copied into the corresponding directories under the total wiki (`raw/` → `raw/`, `wiki/` → `wiki/`).
      - If a target filename already exists, the scanner auto-renames it to `foo_1.md`, `foo_2.md`, etc.
      - Generates `.wiki/ingest_manifest.json` for `.learning` staged sources.
      - Updates `.wiki/doc_index.json` so unchanged files are not re-processed.
   
   2. **Read the manifest.** If no `.learning` sources were staged, skip to step 4.
   
   3. **For each staged `.learning` source, execute the standard Ingest Workflow starting at Step 2.**
      - `.wiki` files do NOT need ingestion; they are already in place.
   
   4. **After syncing, append a batch log entry to `wiki/log.md`:**
      ```markdown
      ## [YYYY-MM-DD] sync | batch ingest
      - .learning staged: N
      - .wiki synced: N
      - Ingested: `raw/articles/...`
      - Pages created: `wiki/sources/...`, `wiki/concepts/...`
      - Pages updated: `wiki/entities/...`, `wiki/index.md`
      ```
   
   5. Offer to run `git add . && git commit -m "sync: ingest batch"`.
   ```

4. **Lint Workflow 补充**：
   ```markdown
   - **Wiki conflict merging:** The linter detects filename groups in `wiki/` such as `foo.md`, `foo_1.md`, `foo_2.md` (created by `.wiki` sync collisions) and flags them for manual or AI-assisted merging.
   - **Raw multi-version retention:** Conflicts in `raw/` (e.g., `bar.md`, `bar_1.md`) are considered intentional multi-version retention and are not flagged for merging.
   ```

5. **Multi-Agent Product Adaptation Notes** 表格新增行：
   | `.wiki` aggregation | Project-level `.wiki` directories are synced directly into the total wiki. Conflicting filenames are auto-renamed. |

### 7.2 `SKILL.md` 更新点

1. Quick Reference 中 `/wiki sync` 描述更新为：
   `Scan .learning dirs and project .wiki dirs → stage/sync → auto-ingest into wiki`

---

## 八、测试场景（Phase 6）

| 场景 | 预期结果 |
|------|---------|
| 空 `.wiki` 同步 | 无变更，index 正常更新 |
| 单项目 `.wiki` 首次同步 | 文件复制到总 wiki 对应目录，index 记录 MD5 和 target 映射 |
| 多项目 `.wiki` 同名文件 | 第二个项目文件重命名为 `foo_1.md`，index 正确记录 |
| 增量同步（文件修改） | 只复制变更的文件，覆盖原 target |
| 全量同步 `--wiki-full-sync` | 所有 `.wiki` 文件重新复制，index 的 `wiki_targets` 重建 |
| `.learning` + `.wiki` 同时存在 | 分别处理，互不影响 |
| 旧 `learning_index.json` 迁移 | 自动迁移到 `doc_index.json`，旧文件删除 |
| 删除源文件 | 总 wiki 中文件保留，index 中该文件记录消失（下次 diff 时出现在 removed 中） |

---

## 九、文件变更清单

| 文件 | 操作 |
|------|------|
| `scripts/learning_scanner.py` | 大幅重构：新增 wiki 扫描、同步逻辑，升级 index |
| `RULES.md` | 更新 `/wiki sync` workflow、lint 说明、适配表格 |
| `SKILL.md` | 更新 `/wiki sync` 命令描述 |

---

计划完毕。下一步：按 Phase 1-6 逐步实施代码修改。
