from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any


DEFAULT_REPO = "chyckenwing/chickenwing"


def fetch_releases(repo: str) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/releases"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "chickenwing-download-stats",
            **({"Authorization": f"Bearer {os.environ['GH_TOKEN']}"} if os.environ.get("GH_TOKEN") else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPO
    releases = fetch_releases(repo)

    if not releases:
        print(f"No releases found for {repo}.")
        return 0

    grand_total = 0
    print(f"Download stats for {repo}")
    print("=" * 72)

    for release in releases:
        tag = release.get("tag_name") or "(untagged)"
        name = release.get("name") or tag
        assets = release.get("assets") or []
        release_total = sum(int(asset.get("download_count", 0)) for asset in assets)
        grand_total += release_total

        print(f"{name} [{tag}]")
        if not assets:
            print("  No release assets uploaded.")
            print()
            continue

        for asset in assets:
            asset_name = asset.get("name", "unknown")
            count = int(asset.get("download_count", 0))
            print(f"  {asset_name}: {count}")
        print(f"  Release total: {release_total}")
        print()

    print("=" * 72)
    print(f"Grand total asset downloads: {grand_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
