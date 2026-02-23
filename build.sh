#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Step 1: Scraping products ==="
python scrape_products.py

echo ""
echo "=== Step 2: Generating blog posts ==="
python generate_posts.py

echo ""
echo "=== Step 3: Cross-linking posts ==="
python crosslink_posts.py

echo ""
echo "=== Step 4: Building Hugo site ==="
hugo --minify

echo ""
echo "=== Done! Output in public/ ==="
echo "Upload the contents of public/ to your Plesk server."
