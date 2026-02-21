#!/usr/bin/env python3
"""Scrape vintagevegasshirts.com product sitemaps and extract location data."""

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://vintagevegasshirts.com"
SITEMAPS = [f"{BASE}/product-sitemap{i}.xml" for i in range(1, 5)]
HEADERS = {"User-Agent": "VintageVegasBlogBot/1.0 (vintage-vegas.com)"}
DELAY = 1  # seconds between fetches

STYLE_PATTERNS = {
    "triblend_tee": r"triblend-tee",
    "ladies_cotton_tee": r"(?:ladies-cotton-tee|district-made-ladies-tee)",
    "bella_vneck": r"bella-ladies-v-neck",
}

VERSION_RE = re.compile(r"-(?:ver(?:sion)?-?\d+)")


def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        print(f"  Error fetching {url}: {e}")
        return None


def get_product_urls() -> list[str]:
    """Fetch all product URLs from sitemaps."""
    urls = []
    for sitemap_url in SITEMAPS:
        print(f"Fetching sitemap: {sitemap_url}")
        xml = fetch(sitemap_url)
        if not xml:
            continue
        soup = BeautifulSoup(xml, "lxml-xml")
        for loc in soup.find_all("loc"):
            url = loc.text.strip()
            if "/product/" in url:
                urls.append(url)
        time.sleep(DELAY)
    print(f"Found {len(urls)} product URLs")
    return urls


def extract_slug_and_style(url: str) -> tuple[str, str] | None:
    """Extract location slug and style from a product URL."""
    path = url.rstrip("/").split("/product/")[-1]
    for style_key, pattern in STYLE_PATTERNS.items():
        m = re.search(pattern, path)
        if m:
            loc_slug = path[: m.start()].rstrip("-")
            # Remove version suffixes
            loc_slug = VERSION_RE.sub("", loc_slug)
            return loc_slug, style_key
    return None


def slug_to_name(slug: str) -> str:
    """Convert slug to title case location name."""
    words = slug.split("-")
    small = {"and", "the", "of", "in", "at", "on", "for"}
    result = []
    for i, w in enumerate(words):
        if i == 0 or w not in small:
            result.append(w.capitalize())
        else:
            result.append(w)
    return " ".join(result)


def scrape_product_page(url: str) -> tuple[str, str]:
    """Get description and image from a product page."""
    html = fetch(url)
    if not html:
        return "", ""
    soup = BeautifulSoup(html, "lxml")
    
    # Description — try multiple sources
    desc = ""
    # 1. WooCommerce short description
    desc_div = soup.select_one(".woocommerce-product-details__short-description")
    if desc_div:
        desc = desc_div.get_text(strip=True)
    # 2. Description tab
    if not desc:
        desc_tab = soup.select_one("#tab-description, .woocommerce-Tabs-panel--description")
        if desc_tab:
            desc = desc_tab.get_text(strip=True)
    # 3. og:description meta tag (always present, truncated but useful)
    if not desc:
        og_desc = soup.select_one('meta[property="og:description"]')
        if og_desc:
            desc = og_desc.get("content", "")
    # Clean up "Description" prefix from tab heading
    if desc.startswith("Description"):
        desc = desc[len("Description"):].strip()
    
    # Image — use og:image meta tag (most reliable, always present)
    img = ""
    og_img = soup.select_one('meta[property="og:image"]')
    if og_img:
        img = og_img.get("content", "")
    # Fallback: try gallery slider image
    if not img:
        img_tag = soup.select_one(".wcgs-slider-image-tag, .woocommerce-product-gallery__image img, .wp-post-image")
        if img_tag:
            img = img_tag.get("data-image") or img_tag.get("src", "")
    
    return desc, img


def main(limit: int | None = None):
    urls = get_product_urls()
    
    # Group by location
    locations: dict[str, dict] = {}
    for url in urls:
        result = extract_slug_and_style(url)
        if not result:
            continue
        slug, style = result
        if slug not in locations:
            locations[slug] = {
                "location": slug_to_name(slug),
                "slug": slug,
                "description": "",
                "image": "",
                "products": {},
            }
        locations[slug]["products"][style] = url

    print(f"Found {len(locations)} unique locations")

    # Scrape individual pages for description + image (use first available product)
    items = list(locations.values())
    if limit:
        items = items[:limit]
        print(f"Limiting to {limit} locations for testing")

    for loc in items:
        # Pick first product URL to scrape
        first_url = next(iter(loc["products"].values()))
        print(f"Scraping: {loc['location']} — {first_url}")
        desc, img = scrape_product_page(first_url)
        loc["description"] = desc
        loc["image"] = img
        time.sleep(DELAY)

    # Save
    out = Path("data/products.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(items, indent=2))
    print(f"Saved {len(items)} locations to {out}")


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit)
