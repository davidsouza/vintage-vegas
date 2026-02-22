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

Respond in EXACTLY this JSON format, nothing else:
{{
  "title": "SEO-friendly title targeting keywords like 'vintage las vegas', '{location} history', 'las vegas strip history'",
  "meta_description": "150 character meta description for SEO",
  "body": "300-500 word blog post in markdown about the location's history, significance, era, what made it special, and its legacy. Use ## subheadings. Do not include the title as an H1."
}}"""


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

    # Parse JSON from response
    try:
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            print(f"  ERROR: No JSON found in response")
            return False
        json_str = json_match.group()
        
        # Try parsing as-is first
        data = None
        for attempt in range(3):
            try:
                if attempt == 0:
                    data = json.loads(json_str)
                elif attempt == 1:
                    data = json.loads(json_str, strict=False)
                elif attempt == 2:
                    # Fix common LLM JSON issues:
                    # - Replace curly/smart quotes with straight quotes
                    fixed = json_str.replace("\u201c", "'").replace("\u201d", "'")
                    fixed = fixed.replace("\u2018", "'").replace("\u2019", "'")
                    # - Escape unescaped newlines in strings
                    data = json.loads(fixed, strict=False)
                break
            except json.JSONDecodeError:
                if attempt == 2:
                    raise
                continue
        
        if data is None:
            raise json.JSONDecodeError("All parse attempts failed", json_str, 0)
    except json.JSONDecodeError as e:
        # Last resort: extract fields with regex instead of JSON parsing
        print(f"  WARN: JSON parse failed ({e}), extracting fields with regex...")
        title_m = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        meta_m = re.search(r'"meta_description"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        body_m = re.search(r'"body"\s*:\s*"(.*)', raw, re.DOTALL)
        
        if not body_m:
            print(f"  ERROR: Could not extract any content")
            return False
        
        data = {
            "title": title_m.group(1) if title_m else f"{loc['location']} — Vintage Las Vegas History",
            "meta_description": meta_m.group(1) if meta_m else f"Discover the history of {loc['location']}.",
            "body": body_m.group(1).rstrip('"\n }') if body_m else "",
        }
        # Unescape the body
        data["body"] = data["body"].replace("\\n", "\n").replace('\\"', '"')

    title = data.get("title", f"{loc['location']} — Vintage Las Vegas History")
    meta = data.get("meta_description", f"Discover the history of {loc['location']} in Las Vegas.")
    body = data.get("body", "")

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
