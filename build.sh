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
echo "=== Step 5: Deploying to server ==="
# Load server credentials from .env
set -a
source <(grep -E '^SERVER_' .env)
set +a

if [[ -z "${SERVER_IP:-}" || -z "${SERVER_USERNAME:-}" || -z "${SERVER_PASSWORD:-}" ]]; then
  echo "⚠️  Server credentials not found in .env — skipping deploy."
  echo "   Add SERVER_IP, SERVER_USERNAME, SERVER_PASSWORD to .env"
  exit 0
fi

sshpass -p "$SERVER_PASSWORD" rsync -avz --delete \
  -e "ssh -o StrictHostKeyChecking=no" \
  public/ "$SERVER_USERNAME@$SERVER_IP:httpdocs/"

echo ""
echo "=== ✅ Done! Site deployed to vintage-vegas.com ==="
