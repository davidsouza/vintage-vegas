#!/usr/bin/env python3
"""Generate Hugo blog posts from scraped product data using Ollama."""

import json
import re
from pathlib import Path

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:12b"
CONTENT_DIR = Path("content/posts")


def generate_with_ollama(prompt: str) -> str:
    """Call Ollama API and return generated text."""
    r = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": prompt, "stream": False},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["response"]


def build_prompt(location: str, description: str) -> str:
    return f"""You are a Las Vegas history writer. Write a blog post about "{location}" for a vintage Las Vegas blog.

Product description for context: {description}

Respond using EXACTLY this format with the delimiters shown:

---TITLE---
SEO-friendly title targeting keywords like 'vintage las vegas', '{location} history', 'las vegas strip history'
---META---
150 character meta description for SEO
---BODY---
300-500 word blog post in markdown about the location's history, significance, era, what made it special, and its legacy. Use ## subheadings. Do not include the title as an H1.
---END---"""


def generate_post(loc: dict) -> bool:
    """Generate a Hugo markdown post for a location."""
    slug = loc["slug"]
    out_path = CONTENT_DIR / f"{slug}.md"

    # Skip if already generated
    if out_path.exists():
        print(f"  Skipping (already exists): {out_path}")
        return True

    print(f"Generating post for: {loc['location']}")
    if out_path.exists():
        print(f"  Skipping (already exists): {out_path}")
        return True
    
    raw = generate_with_ollama(build_prompt(loc["location"], loc["description"]))

    # Parse delimited response
    def extract_section(text, start_tag, end_tag):
        s = text.find(start_tag)
        if s < 0:
            return ""
        s += len(start_tag)
        e = text.find(end_tag, s)
        return text[s:e].strip() if e > s else text[s:].strip()

    title = extract_section(raw, "---TITLE---", "---META---")
    meta = extract_section(raw, "---META---", "---BODY---")
    body = extract_section(raw, "---BODY---", "---END---")

    # Fallback: try JSON parsing if delimited format not found (backward compat)
    if not body:
        print(f"  WARN: Delimited format not found, trying JSON fallback...")
        try:
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(), strict=False)
                title = data.get("title", "")
                meta = data.get("meta_description", "")
                body = data.get("body", "")
        except (json.JSONDecodeError, AttributeError):
            # Last resort: regex extraction
            title_m = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            meta_m = re.search(r'"meta_description"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            body_m = re.search(r'"body"\s*:\s*"(.*)', raw, re.DOTALL)
            if body_m:
                title = title_m.group(1) if title_m else ""
                meta = meta_m.group(1) if meta_m else ""
                body = body_m.group(1).replace("\\n", "\n").replace('\\"', '"')
            else:
                print(f"  ERROR: Could not extract any content")
                return False

    # Clean up
    title = title.strip('"').strip() or f"{loc['location']} — Vintage Las Vegas History"
    meta = meta.strip('"').strip() or f"Discover the history of {loc['location']}."
    body = re.sub(r'\s*```\s*$', '', body).rstrip('"\n }').strip()

    # Build shop section
    shop_lines = [
        "",
        '<div class="shop-collection">',
        f'<h2>🎰 Shop the {loc["location"]} Collection</h2>',
        '<div class="shop-links">',
    ]
    style_labels = {
        "triblend_tee": "Triblend Tee",
        "ladies_cotton_tee": "Ladies Cotton Tee",
        "bella_vneck": "Bella V-Neck",
    }
    for key, label in style_labels.items():
        url = loc["products"].get(key)
        if url:
            shop_lines.append(f'<a href="{url}" class="shop-link" target="_blank" rel="noopener">{label}</a>')
    shop_lines.extend(["</div>", "</div>"])
    shop_html = "\n".join(shop_lines)

    # Build front matter
    tags = json.dumps(["las vegas history", "vintage vegas", loc["location"].lower()])
    yt = loc.get("youtube")
    youtube_lines = ""
    if yt:
        youtube_lines = f"""youtube_url: "{yt['url']}"
youtube_id: "{yt['video_id']}"
youtube_title: "{yt['title']}"
youtube_thumbnail: "{yt['thumbnail']}"
"""
    # Sanitize quotes for YAML frontmatter (inner double quotes → single quotes)
    title = re.sub(r'"([^"]+)"', r"'\1'", title)
    meta = re.sub(r'"([^"]+)"', r"'\1'", meta)

    frontmatter = f"""---
title: "{title}"
date: 2026-02-21
description: "{meta}"
image: "{loc.get('image', '')}"
location: "{loc['location']}"
tags: {tags}
{youtube_lines}---"""

    content = f"{frontmatter}\n\n{body}\n\n{shop_html}\n"
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)
    print(f"  Wrote: {out_path}")
    return True


def main():
    data_file = Path("data/products.json")
    if not data_file.exists():
        print("Error: data/products.json not found. Run scrape_products.py first.")
        return

    locations = json.loads(data_file.read_text())
    print(f"Generating posts for {len(locations)} locations...")

    success = 0
    for loc in locations:
        if generate_post(loc):
            success += 1

    print(f"\nDone: {success}/{len(locations)} posts generated")


if __name__ == "__main__":
    main()
