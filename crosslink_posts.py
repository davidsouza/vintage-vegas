#!/usr/bin/env python3
"""Cross-link vintage vegas posts by finding mentions of other locations in post bodies."""
from __future__ import annotations

import re
from pathlib import Path

POSTS_DIR = Path("content/posts")

# Terms too generic to safely auto-link
BLOCKLIST = {"Splash", "Oasis", "Landmark", "Silver"}


def parse_post(path: Path) -> dict | None:
    text = path.read_text()
    if not text.startswith("---"):
        return None
    end = text.index("---", 3)
    frontmatter = text[3:end]
    body = text[end + 3:].lstrip("\n")
    location = None
    for line in frontmatter.splitlines():
        if line.startswith("location:"):
            location = line.split(":", 1)[1].strip().strip('"')
            break
    if not location:
        return None
    return {
        "path": path,
        "location": location,
        "slug": path.stem,
        "frontmatter_raw": text[:end + 3],
        "body": body,
    }


def build_name_variants(location: str) -> list[str]:
    variants = []
    base = location
    for suffix in [" Las Vegas", " Las Legas"]:
        if base.endswith(suffix):
            variants.append(base)  # Full name with city
            base = base[:-len(suffix)]
            break
    variants.append(base)  # Name without city
    # Short name: strip venue type
    for pat in [
        r"\s+Hotel\s+and\s+Casino$", r"\s+Hotel\s+&\s+Casino$",
        r"\s+Hotel\s+Casino$", r"\s+Casino$", r"\s+Hotel$",
        r"\s+Motel$", r"\s+Inn$", r"\s+Bar$",
        r"\s+Restaurant\s+and\s+(?:Inn|Lounge)$", r"\s+Gaming\s+Guide$",
        r"\s+Country\s+Club$", r"\s+Drive-In$",
    ]:
        m = re.search(pat, base, re.IGNORECASE)
        if m:
            short = base[:m.start()]
            if len(short) >= 5 and short not in BLOCKLIST:
                variants.append(short)
            break
    return variants


def linkify_body(body: str, slug: str, link_map: list[tuple[re.Pattern, str, str]]) -> tuple[str, list[str]]:
    """Replace first mention of each location with a markdown link.
    
    Strategy: split text into segments that are inside markdown links/HTML tags
    vs plain text. Only do replacements in plain text segments.
    """
    # Split off shop section
    shop_marker = '<div class="shop-collection">'
    shop_idx = body.find(shop_marker)
    if shop_idx >= 0:
        content = body[:shop_idx]
        shop_part = body[shop_idx:]
    else:
        content = body
        shop_part = ""

    linked = []
    already_linked_slugs = set()

    for pattern, target_slug, display_name in link_map:
        if target_slug == slug or target_slug in already_linked_slugs:
            continue

        # Split content into: (plain_text, link_or_tag, plain_text, ...)
        # Tokens inside [...](...)  or <...> are protected
        parts = re.split(r'(\[[^\]]*\]\([^\)]*\)|<[^>]+>)', content)

        found = False
        new_parts = []
        for i, part in enumerate(parts):
            if found or i % 2 == 1:
                # Already found match or this is a protected segment
                new_parts.append(part)
                continue
            # Plain text segment — try to match
            m = pattern.search(part)
            if m:
                original = m.group(0)
                link = f"[{original}](/posts/{target_slug}/)"
                new_parts.append(part[:m.start()] + link + part[m.end():])
                found = True
            else:
                new_parts.append(part)

        if found:
            content = "".join(new_parts)
            linked.append(display_name)
            already_linked_slugs.add(target_slug)

    return content + shop_part, linked


def main():
    posts = []
    for p in sorted(POSTS_DIR.glob("*.md")):
        parsed = parse_post(p)
        if parsed:
            posts.append(parsed)

    print(f"Loaded {len(posts)} posts")

    # Deduplicate: if multiple posts share same short name, prefer the one 
    # without "las-legas" typo in slug
    slug_by_variant: dict[str, tuple[str, str]] = {}
    for post in posts:
        variants = build_name_variants(post["location"])
        for v in variants:
            key = v.lower()
            existing = slug_by_variant.get(key)
            if existing is None:
                slug_by_variant[key] = (post["slug"], post["location"])
            elif "las-legas" in existing[0] and "las-legas" not in post["slug"]:
                slug_by_variant[key] = (post["slug"], post["location"])
            # else keep existing

    # Build link map as compiled patterns, sorted by term length desc
    entries: list[tuple[str, str, str]] = []
    seen = set()
    for term_lower, (target_slug, loc) in slug_by_variant.items():
        if (term_lower, target_slug) not in seen:
            entries.append((term_lower, target_slug, loc))
            seen.add((term_lower, target_slug))

    entries.sort(key=lambda x: len(x[0]), reverse=True)

    link_map: list[tuple[re.Pattern, str, str]] = []
    for term, target_slug, loc in entries:
        if len(term) < 5:
            continue
        # Build case-insensitive word-boundary pattern
        pat = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
        link_map.append((pat, target_slug, loc))

    print(f"Built {len(link_map)} link patterns")

    total_links = 0
    modified_files = 0

    for post in posts:
        new_body, linked = linkify_body(post["body"], post["slug"], link_map)
        if linked:
            post["path"].write_text(post["frontmatter_raw"] + "\n\n" + new_body)
            total_links += len(linked)
            modified_files += 1
            if len(linked) >= 5:
                print(f"  {post['slug']}: {len(linked)} links")

    print(f"\nDone: {total_links} cross-links added across {modified_files} posts")


if __name__ == "__main__":
    main()
