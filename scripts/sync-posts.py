#!/usr/bin/env python3
"""Sync blog notes from an external (Obsidian) vault into content/blog/.

Only notes whose front matter says `status: published` are published.
Everything else (draft, missing status, ...) is left out, and if a note
that was previously synced is no longer published, its post is removed.

Usage:
    python3 scripts/sync-posts.py              # sync
    python3 scripts/sync-posts.py --dry-run    # show what would change
    python3 scripts/sync-posts.py --source "/other/folder"   # override sources

Configuration (edit SOURCES below, or set BLOG_SOURCES to a ':'-separated
list of folders). Each note's first subfolder under the source becomes its
category (e.g. Blogs/AI Engineering/x.md -> category "AI Engineering");
notes directly in the source folder get no category.

Wikilinks between published notes ([[Note]] or [[Note|text]]) become site links.

Optional front matter in a note: title, date (YYYY-MM-DD), slug, description,
tags. Defaults: title = first '# Heading', date = first sync date (then kept),
slug = generated from the title (then kept).
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

# ---- configuration ---------------------------------------------------------
SOURCES = [
    "/home/jetoomasu/Documents/JETVault/Blogs",
]
# ----------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
PUBLISHED = {"published", "publish"}


def parse_front_matter(text):
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n?(.*)", text, re.S)
    if not m:
        return {}, text
    raw, body = m.groups()
    meta, key = {}, None
    for line in raw.splitlines():
        item = re.match(r"\s+-\s+(.*)", line)
        if item and key:
            meta.setdefault(key, [])
            if isinstance(meta[key], list):
                meta[key].append(item.group(1).strip().strip("\"'"))
            continue
        kv = re.match(r"([A-Za-z_][\w-]*)\s*:\s*(.*)", line)
        if not kv:
            continue
        key, val = kv.group(1), kv.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key] = [v.strip().strip("\"'") for v in val[1:-1].split(",") if v.strip()]
        elif val == "":
            meta[key] = []
        else:
            meta[key] = val.strip("\"'")
    return meta, body


def slugify(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return "-".join(s.split("-")[:8])


def build_post(note, category, state_entry, today):
    meta, body = parse_front_matter(note.read_text(encoding="utf-8"))
    if str(meta.get("status", "")).lower() not in PUBLISHED:
        return None
    h1 = re.match(r"\s*#\s+(.+?)\s*\n", body)
    title = meta.get("title") or (h1.group(1) if h1 else note.stem)
    if h1:
        body = body[h1.end():]
    slug = meta.get("slug") or state_entry.get("slug") or slugify(title)
    date = meta.get("date") or state_entry.get("date") or today
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    lines = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"date: {date}",
        "draft: false",
        f"tags: {json.dumps(tags, ensure_ascii=False)}",
    ]
    if category:
        lines.append(f"categories: {json.dumps([category], ensure_ascii=False)}")
    if meta.get("description"):
        lines.append(f"description: {json.dumps(meta['description'], ensure_ascii=False)}")
    lines += ["---", "", body.lstrip("\n").rstrip() + "\n"]
    return slug, date, "\n".join(lines), title, note.stem


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", help="note folder (repeatable); overrides config")
    ap.add_argument("--content-dir", default=str(ROOT / "content" / "blog"))
    ap.add_argument("--state", default=str(ROOT / "scripts" / ".sync-state.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = args.source or (os.environ["BLOG_SOURCES"].split(":") if os.environ.get("BLOG_SOURCES") else SOURCES)
    out_dir, state_path = Path(args.content_dir), Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    today = datetime.date.today().isoformat()
    new_state, actions, seen_slugs = {}, [], {}

    posts = []  # (key, slug, date, content, title, stem)
    for src in map(Path, sources):
        if not src.is_dir():
            sys.exit(f"error: source folder not found: {src}")
        for note in sorted(src.rglob("*.md")):
            rel = note.relative_to(src)
            if any(part.startswith(("_", ".")) for part in rel.parts):
                continue  # _experiments/, .obsidian/, etc. are never published
            key = rel.as_posix()
            category = rel.parts[0] if len(rel.parts) > 1 else None
            result = build_post(note, category, state.get(key, {}), today)
            if result is None:
                continue
            slug, date, content, title, stem = result
            if slug in seen_slugs:
                sys.exit(f"error: slug '{slug}' used by both {seen_slugs[slug]} and {key}")
            seen_slugs[slug] = key
            posts.append((key, slug, date, content, title, stem))

    # Resolve Obsidian [[wikilinks]] between published notes into site links.
    targets = {}
    for key, slug, _d, _c, title, stem in posts:
        targets[stem.lower()] = (slug, title)
        targets[title.lower()] = (slug, title)

    def resolve(m):
        name = m.group(1).strip()
        alias = m.group(2)
        hit = targets.get(name.lower())
        if not hit:
            return m.group(0)
        return f"[{(alias or hit[1]).strip()}](/blog/{hit[0]}/)"

    link_re = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
    for key, slug, date, content, title, stem in posts:
        content = link_re.sub(resolve, content)
        target = out_dir / f"{slug}.md"
        old = target.read_text(encoding="utf-8") if target.exists() else None
        status = "unchanged" if old == content else ("update" if old else "new")
        actions.append((status, f"{key} -> {target.name}"))
        if re.search(r"!?\[\[", content):
            actions.append(("warning", f"{key}: unresolved [[wikilink]]/embed (target not published?); Hugo will show it as plain text"))
        if status != "unchanged" and not args.dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        new_state[key] = {"slug": slug, "date": date}

    # Remove posts we previously synced that are no longer published/present.
    for key, entry in state.items():
        if key not in new_state:
            target = out_dir / f"{entry['slug']}.md"
            actions.append(("REMOVE", f"{key} (no longer published) -> {target.name}"))
            if not args.dry_run and target.exists():
                target.unlink()

    for status, msg in actions:
        print(f"{status:>9}  {msg}")
    if not actions:
        print("nothing to sync (no notes with status: published)")
    if args.dry_run:
        print("\n(dry run: no files were changed)")
    else:
        state_path.write_text(json.dumps(new_state, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
