#!/usr/bin/env python3
"""
Create Pinterest pins for all Vintage Vegas posts.

Usage:
  # Dry run (preview what would be pinned):
  python pinterest_pins.py --dry-run

  # Pin a batch (default 15 per run):
  python pinterest_pins.py

  # Pin a specific batch size:
  python pinterest_pins.py --batch 10

  # Pin everything at once (not recommended — spread over days):
  python pinterest_pins.py --batch 0

Requirements:
  - PINTEREST_ACCESS_TOKEN env var or .env file
  - PINTEREST_BOARD_ID env var or .env file
  - requests (pip install requests)

Pinterest best practices: 10-15 pins/day, consistent schedule.
Run this daily via cron until all posts are pinned.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import requests

POSTS_DIR = Path("content/posts")
PROGRESS_FILE = Path("data/pinterest_progress.json")
SITE_URL = "https://vintage-vegas.com"
# Use sandbox URL for trial apps, switch to production once approved
# Production: https://api.pinterest.com/v5
# Sandbox:    https://api-sandbox.pinterest.com/v5
API_BASE = os.environ.get("PINTEREST_API_BASE", "https://api-sandbox.pinterest.com/v5")

# Rate limit: Pinterest allows 50 POST requests per minute
# We'll be conservative
DELAY_BETWEEN_PINS = 5  # seconds


def load_env():
    """Load .env file if present."""
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def get_config():
    """Get Pinterest credentials from env."""
    load_env()
    token = os.environ.get("PINTEREST_ACCESS_TOKEN")
    board_id = os.environ.get("PINTEREST_BOARD_ID")
    if not token:
        print("ERROR: Set PINTEREST_ACCESS_TOKEN in env or .env file")
        print("  Get one at: https://developers.pinterest.com/apps/")
        raise SystemExit(1)
    if not board_id:
        print("ERROR: Set PINTEREST_BOARD_ID in env or .env file")
        print("  Find your board ID via: GET https://api.pinterest.com/v5/boards/")
        print("  Or use: python pinterest_pins.py --list-boards")
        raise SystemExit(1)
    return token, board_id


def list_boards(token: str):
    """List all boards for the authenticated user."""
    resp = requests.get(
        f"{API_BASE}/boards",
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": 50},
    )
    resp.raise_for_status()
    data = resp.json()
    print("Your Pinterest boards:\n")
    for board in data.get("items", []):
        print(f"  {board['name']}")
        print(f"    ID: {board['id']}")
        print(f"    URL: https://pinterest.com{board.get('url', '')}")
        print()


def parse_post(path: Path) -> dict | None:
    """Extract pin-relevant data from a Hugo post."""
    text = path.read_text()
    if not text.startswith("---"):
        return None

    end = text.index("---", 3)
    frontmatter = text[3:end]

    data = {}
    for line in frontmatter.splitlines():
        if line.startswith("title:"):
            data["title"] = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("description:"):
            data["description"] = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("image:"):
            data["image"] = line.split(":", 1)[1].strip().strip('"')
            # Fix: image URL might have been split by the `:` in `https:`
            if data["image"].startswith("http") and "://" not in data["image"]:
                data["image"] = "https:" + line.split("https:", 1)[1].strip().strip('"')
        elif line.startswith("location:"):
            data["location"] = line.split(":", 1)[1].strip().strip('"')

    if not data.get("image") or not data.get("title"):
        return None

    # Fix image URL parsing (handle https split)
    img_match = re.search(r'image:\s*"(https?://[^"]+)"', frontmatter)
    if img_match:
        data["image"] = img_match.group(1)

    data["slug"] = path.stem
    data["url"] = f"{SITE_URL}/posts/{path.stem}/"

    return data


def load_progress() -> set:
    """Load set of already-pinned slugs."""
    if PROGRESS_FILE.exists():
        return set(json.loads(PROGRESS_FILE.read_text()))
    return set()


def save_progress(pinned: set):
    """Save pinned slugs."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(sorted(pinned), indent=2))


def create_pin(token: str, board_id: str, post: dict) -> dict:
    """Create a single Pinterest pin via API v5."""
    # Pinterest description max: 500 chars
    description = post.get("description", "")[:500]

    # Add hashtags for discoverability
    hashtags = "\n\n#VintageVegas #LasVegasHistory #VintageLasVegas #RetroVegas #OldVegas"
    if len(description) + len(hashtags) <= 500:
        description += hashtags

    payload = {
        "board_id": board_id,
        "title": post["title"][:100],  # Pinterest title max: 100 chars
        "description": description,
        "link": post["url"],
        "media_source": {
            "source_type": "image_url",
            "url": post["image"],
        },
    }

    resp = requests.post(
        f"{API_BASE}/pins",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )

    if resp.status_code == 429:
        print("  Rate limited — waiting 60s...")
        time.sleep(60)
        return create_pin(token, board_id, post)  # Retry

    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Pin Vintage Vegas posts to Pinterest")
    parser.add_argument("--dry-run", action="store_true", help="Preview without pinning")
    parser.add_argument("--batch", type=int, default=15, help="Pins per run (0=all)")
    parser.add_argument("--list-boards", action="store_true", help="List your Pinterest boards")
    parser.add_argument("--reset", action="store_true", help="Reset progress tracking")
    args = parser.parse_args()

    load_env()

    if args.list_boards:
        token = os.environ.get("PINTEREST_ACCESS_TOKEN")
        if not token:
            print("Set PINTEREST_ACCESS_TOKEN first")
            raise SystemExit(1)
        list_boards(token)
        return

    if args.reset:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            print("Progress reset.")
        return

    # Load all posts
    posts = []
    for p in sorted(POSTS_DIR.glob("*.md")):
        parsed = parse_post(p)
        if parsed:
            posts.append(parsed)

    print(f"Found {len(posts)} posts with images")

    # Filter already pinned
    pinned = load_progress()
    remaining = [p for p in posts if p["slug"] not in pinned]
    print(f"Already pinned: {len(pinned)}")
    print(f"Remaining: {len(remaining)}")

    if not remaining:
        print("\nAll posts have been pinned! 🎉")
        return

    # Determine batch
    batch = remaining if args.batch == 0 else remaining[:args.batch]
    print(f"This run: {len(batch)} pins\n")

    if args.dry_run:
        for i, post in enumerate(batch, 1):
            print(f"  [{i}] {post['title'][:60]}")
            print(f"       {post['url']}")
            print(f"       img: {post['image'][:80]}")
            print()
        print(f"Run without --dry-run to create these pins.")
        days_left = len(remaining) // 15 + 1
        print(f"At 15/day, all {len(remaining)} pins will be done in ~{days_left} days.")
        return

    # Create pins
    token, board_id = get_config()
    success = 0
    errors = 0

    for i, post in enumerate(batch, 1):
        try:
            print(f"[{i}/{len(batch)}] Pinning: {post['title'][:60]}...")
            result = create_pin(token, board_id, post)
            pin_id = result.get("id", "?")
            print(f"  ✅ Pin created: {pin_id}")
            pinned.add(post["slug"])
            save_progress(pinned)
            success += 1

            if i < len(batch):
                time.sleep(DELAY_BETWEEN_PINS)

        except requests.HTTPError as e:
            print(f"  ❌ Failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"     {e.response.text[:200]}")
            errors += 1
            continue

    print(f"\nDone: {success} pinned, {errors} errors")
    print(f"Total pinned: {len(pinned)}/{len(posts)}")
    remaining_count = len(posts) - len(pinned)
    if remaining_count > 0:
        days = remaining_count // 15 + 1
        print(f"Remaining: {remaining_count} (~{days} more daily runs)")


if __name__ == "__main__":
    main()
