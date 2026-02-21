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
YT_CHANNEL_ID = "UCgWNM673-Dyy69B1Hx9bb7g"
YT_FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={YT_CHANNEL_ID}"
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


def _extract_location_from_title(title: str) -> str | None:
    """Extract location name from various YouTube video title formats."""
    # Strip hashtags from end
    title = re.sub(r"\s*#\S+", "", title).strip()
    
    patterns = [
        # "Vintage Las Vegas {Location} Bio"
        r"(?:Vintage )?Las Vegas:?\s+(.+?)\s+Bio$",
        # "Vintage Las Vegas: The {Location}" (with colon, may lack "Bio")
        r"(?:Vintage )?Las Vegas:\s+(?:The\s+)?(.+?)$",
        # "Vintage Vegas Bio - {Location}"  /  "Vintage Vegas Bio: {Location}"
        r"Vintage Vegas Bio\s*[-:–]\s*(.+?)$",
        # "Remembering Las Vegas: {Location}"
        r"Remembering Las Vegas:?\s+(.+?)$",
        # "Vintage {Location} – Las Vegas" / "Vintage {Location}, Las Vegas"
        r"Vintage\s+(.+?)\s*[-–,]\s*(?:Las )?Vegas$",
        # "Vintage {Location} Bio" (generic, no Las Vegas)
        r"Vintage\s+(.+?)\s+Bio$",
    ]
    for pattern in patterns:
        m = re.match(pattern, title, re.IGNORECASE)
        if m:
            return m.group(1).strip().lstrip("- ")
    return None


def _parse_shorts_items(items: list) -> dict[str, dict]:
    """Parse video items from YouTube data into our videos dict."""
    videos: dict[str, dict] = {}
    for item in items:
        rm = item.get("richItemRenderer", {}).get("content", {}).get("shortsLockupViewModel", {})
        if not rm:
            continue
        title = rm.get("overlayMetadata", {}).get("primaryText", {}).get("content", "")
        vid_id = rm.get("onTap", {}).get("innertubeCommand", {}).get("reelWatchEndpoint", {}).get("videoId", "")
        if not title or not vid_id:
            continue

        location_name = _extract_location_from_title(title)
        if not location_name:
            print(f"  Skipping video (no location match): {title}")
            continue

        slug = location_name.lower()
        slug = re.sub(r"[''']s\b", "s", slug)
        slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")

        videos[slug] = {
            "title": title,
            "url": f"https://www.youtube.com/shorts/{vid_id}",
            "video_id": vid_id,
            "thumbnail": f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
            "location_name": location_name,
        }
        print(f"  Found video: {location_name} → https://www.youtube.com/shorts/{vid_id}")
    return videos


def scrape_youtube_videos() -> dict[str, dict]:
    """Scrape YouTube channel page to get all Shorts with titles (with pagination)."""
    print("Fetching YouTube channel videos...")
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    try:
        r = requests.get(
            "https://www.youtube.com/@VintageVegasShirts/shorts",
            headers={"User-Agent": ua},
            timeout=30,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  Failed to fetch YouTube channel: {e}")
        return _scrape_youtube_rss()

    # Extract ytInitialData JSON from page
    m = re.search(r"var ytInitialData = ({.*?});</script>", r.text)
    if not m:
        print("  Could not find ytInitialData, falling back to RSS")
        return _scrape_youtube_rss()

    import json as _json
    data = _json.loads(m.group(1))
    videos: dict[str, dict] = {}

    # Also extract API key for continuation requests
    api_key_match = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', r.text)
    api_key = api_key_match.group(1) if api_key_match else None

    try:
        tabs = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
        for tab in tabs:
            renderer = tab.get("tabRenderer", {})
            if not renderer.get("selected"):
                continue
            contents = renderer["content"]["richGridRenderer"]["contents"]

            # Parse initial batch
            videos.update(_parse_shorts_items(contents))

            # Check for continuation token (last item)
            last_item = contents[-1] if contents else {}
            cont_renderer = last_item.get("continuationItemRenderer", {})
            cont_token = (
                cont_renderer
                .get("continuationEndpoint", {})
                .get("continuationCommand", {})
                .get("token")
            )

            # Fetch additional pages
            while cont_token and api_key:
                print(f"  Fetching more videos (have {len(videos)} so far)...")
                try:
                    resp = requests.post(
                        f"https://www.youtube.com/youtubei/v1/browse?key={api_key}",
                        json={
                            "context": {"client": {"clientName": "WEB", "clientVersion": "2.20260221"}},
                            "continuation": cont_token,
                        },
                        headers={"User-Agent": ua},
                        timeout=15,
                    )
                    resp.raise_for_status()
                    cont_data = resp.json()

                    actions = cont_data.get("onResponseReceivedActions", [])
                    if not actions:
                        break

                    cont_items = actions[0].get("appendContinuationItemsAction", {}).get("continuationItems", [])
                    if not cont_items:
                        break

                    videos.update(_parse_shorts_items(cont_items))

                    # Check for another continuation
                    last_cont = cont_items[-1] if cont_items else {}
                    cont_token = (
                        last_cont.get("continuationItemRenderer", {})
                        .get("continuationEndpoint", {})
                        .get("continuationCommand", {})
                        .get("token")
                    )
                except requests.RequestException:
                    break

    except (KeyError, IndexError) as e:
        print(f"  Error parsing YouTube data: {e}, falling back to RSS")
        return _scrape_youtube_rss()

    print(f"Found {len(videos)} location videos")
    return videos


def _scrape_youtube_rss() -> dict[str, dict]:
    """Fallback: fetch YouTube RSS feed (limited to 15 most recent)."""
    print("  Using RSS feed fallback...")
    xml = fetch(YT_FEED_URL)
    if not xml:
        return {}

    soup = BeautifulSoup(xml, "lxml-xml")
    videos: dict[str, dict] = {}

    for entry in soup.find_all("entry"):
        title = entry.find("title").text.strip()
        video_id = entry.find("yt:videoId").text.strip()
        link = entry.find("link", {"rel": "alternate"})
        url = link["href"] if link else f"https://www.youtube.com/shorts/{video_id}"
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        location_name = _extract_location_from_title(title)
        if not location_name:
            continue

        slug = location_name.lower()
        slug = re.sub(r"[''']s\b", "s", slug)
        slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")

        videos[slug] = {
            "title": title,
            "url": url,
            "video_id": video_id,
            "thumbnail": thumbnail,
            "location_name": location_name,
        }

    print(f"  RSS fallback: found {len(videos)} videos")
    return videos


def match_video_to_location(loc_slug: str, loc_name: str, videos: dict[str, dict]) -> dict | None:
    """Fuzzy-match a location to a YouTube video."""
    # Direct slug match
    if loc_slug in videos:
        return videos[loc_slug]

    # Try matching without common suffixes like "las-vegas", "hotel-and-casino"
    loc_clean = loc_slug.replace("-las-vegas", "").replace("-las-legas", "")
    for vid_slug, vid_data in videos.items():
        vid_clean = vid_slug.replace("-hotel-and-casino", "").replace("-casino", "").replace("-hotel", "")
        if loc_clean == vid_slug or loc_clean.startswith(vid_clean) or vid_clean.startswith(loc_clean):
            return vid_data
        # Also try the other way: strip loc suffixes too
        loc_stripped = loc_clean.replace("-hotel-and-casino", "").replace("-casino", "").replace("-hotel", "")
        if loc_stripped == vid_clean:
            return vid_data

    return None


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

    # Fetch YouTube videos
    videos = scrape_youtube_videos()

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

        # Match YouTube video
        video = match_video_to_location(loc["slug"], loc["location"], videos)
        if video:
            loc["youtube"] = video
            print(f"  ✓ Matched video: {video['url']}")
        else:
            loc["youtube"] = None

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
