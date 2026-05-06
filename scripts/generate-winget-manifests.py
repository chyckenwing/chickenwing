from __future__ import annotations

import json
import urllib.request
from pathlib import Path


REPO = "chyckenwing/chickenwing"
PACKAGE_IDENTIFIER = "Chyckenwing.Chickenwing"
PUBLISHER = "Chyckenwing"
PACKAGE_NAME = "Chickenwing"
PACKAGE_MONIKER = "chickenwing"
PACKAGE_SHORT_DESCRIPTION = "Terminal-first YouTube downloader powered by yt-dlp."
PACKAGE_DESCRIPTION = (
    "Chickenwing is a fast terminal downloader for YouTube links and search-driven downloads. "
    "It supports direct video downloads, audio mode, a dedicated download folder, and a self-contained "
    "console-style launch experience."
)
MANIFEST_VERSION = "1.6.0"
PACKAGE_ROOT = Path("packaging/winget/manifests/c/Chyckenwing/Chickenwing")


def fetch_latest_release() -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "chickenwing-winget-manifest-generator",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def main() -> int:
    release = fetch_latest_release()
    version = str(release["tag_name"]).removeprefix("v")
    assets = release.get("assets") or []
    asset = next((item for item in assets if item["name"].endswith(".zip")), None)
    if not asset:
        raise SystemExit("No ZIP release asset found for latest release.")

    asset_name = asset["name"]
    asset_url = asset["browser_download_url"]
    asset_sha256 = str(asset["digest"]).split("sha256:", 1)[-1].upper()
    asset_root = asset_name.removesuffix(".zip")
    relative_exe = f"{asset_root}\\chickenwing.exe"
    release_date = str(release["published_at"]).split("T", 1)[0]

    target_dir = PACKAGE_ROOT / version
    target_dir.mkdir(parents=True, exist_ok=True)

    version_manifest = f"""# yaml-language-server: $schema=https://aka.ms/winget-manifest.version.{MANIFEST_VERSION}.schema.json

PackageIdentifier: {PACKAGE_IDENTIFIER}
PackageVersion: {version}
DefaultLocale: en-US
ManifestType: version
ManifestVersion: {MANIFEST_VERSION}
"""

    installer_manifest = f"""# yaml-language-server: $schema=https://aka.ms/winget-manifest.installer.{MANIFEST_VERSION}.schema.json

PackageIdentifier: {PACKAGE_IDENTIFIER}
PackageVersion: {version}
InstallerType: zip
ReleaseDate: {release_date}
NestedInstallerType: portable
NestedInstallerFiles:
- RelativeFilePath: {relative_exe}
  PortableCommandAlias: chickenwing
Installers:
- Architecture: x64
  InstallerUrl: {asset_url}
  InstallerSha256: {asset_sha256}
  Dependencies:
    PackageDependencies:
    - PackageIdentifier: Gyan.FFmpeg
ManifestType: installer
ManifestVersion: {MANIFEST_VERSION}
"""

    locale_manifest = f"""# yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.{MANIFEST_VERSION}.schema.json

PackageIdentifier: {PACKAGE_IDENTIFIER}
PackageVersion: {version}
PackageLocale: en-US
Publisher: {PUBLISHER}
PublisherUrl: https://github.com/chyckenwing
PublisherSupportUrl: https://github.com/chyckenwing/chickenwing/issues
Author: Chyckenwing
PackageName: {PACKAGE_NAME}
PackageUrl: https://github.com/chyckenwing/chickenwing
License: Proprietary
ShortDescription: {PACKAGE_SHORT_DESCRIPTION}
Description: >-
  {PACKAGE_DESCRIPTION}
Moniker: {PACKAGE_MONIKER}
Tags:
- youtube
- downloader
- yt-dlp
- audio
- video
- cli
ReleaseNotes: First public Windows release of Chickenwing.
ReleaseNotesUrl: https://github.com/chyckenwing/chickenwing/releases/tag/v{version}
ManifestType: defaultLocale
ManifestVersion: {MANIFEST_VERSION}
"""

    (target_dir / f"{PACKAGE_IDENTIFIER}.yaml").write_text(version_manifest, encoding="utf-8")
    (target_dir / f"{PACKAGE_IDENTIFIER}.installer.yaml").write_text(installer_manifest, encoding="utf-8")
    (target_dir / f"{PACKAGE_IDENTIFIER}.locale.en-US.yaml").write_text(locale_manifest, encoding="utf-8")

    print(target_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
