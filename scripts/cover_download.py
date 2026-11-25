"""
cover_download.py — Download book cover images from a list of URLs.

Reads URLs (one per line) from a file (-i) or stdin.
Downloads each image to the output directory (-o), using the filename
from the URL (e.g. https://.../26817133484344.jpg → 26817133484344.jpg).

Files already present in the output directory are skipped.
Progress and summary are written to stderr.

Usage:
    python tools/cover_download.py -i data/input/urls.txt -o data/covers/
    cat urls.txt | python tools/cover_download.py -o data/covers/
"""

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


# --- I/O helpers ---

def read_urls(source) -> list[str]:
    """
    Read URLs from a file-like object.
    Skips blank lines and lines starting with '#'.
    """
    urls = []
    for raw in source:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def filename_from_url(url: str) -> str:
    """
    Extract the filename from the last path segment of a URL.
    e.g. 'https://images.isbndb.com/covers/26817133484344.jpg' → '26817133484344.jpg'
    """
    return Path(urlparse(url).path).name


# --- Download ---

def download_one(url: str, output_dir: Path) -> str:
    """
    Download a single URL to output_dir.

    Returns:
        'downloaded' — file was fetched and written successfully
        'skipped'    — file already exists in output_dir
        'error'      — fetch or write failed (warning already printed to stderr)
    """
    filename = filename_from_url(url)
    if not filename:
        print(f"[WARN] Could not determine filename for URL: {url!r}", file=sys.stderr)
        return "error"

    dest = output_dir / filename
    if dest.exists():
        return "skipped"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        dest.write_bytes(response.content)
        print(f"[INFO] Downloaded: {filename}", file=sys.stderr)
        return "downloaded"
    except requests.RequestException as e:
        print(f"[ERROR] Failed to download {url!r}: {e}", file=sys.stderr)
        return "error"


# --- Main ---

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download book cover images from a list of URLs."
    )
    parser.add_argument(
        "-i", "--input",
        metavar="FILE",
        help="Input file with one URL per line (default: stdin)",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="DIR",
        required=True,
        help="Output directory for downloaded images",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.input:
        with open(args.input, encoding="utf-8-sig") as f:
            urls = read_urls(f)
    else:
        urls = read_urls(sys.stdin)

    if not urls:
        print("[WARN] No URLs found in input.", file=sys.stderr)
        sys.exit(0)

    print(f"[INFO] {len(urls)} URL(s) to process.", file=sys.stderr)

    downloaded = 0
    skipped = 0
    errors = 0

    for url in urls:
        result = download_one(url, output_dir)
        if result == "downloaded":
            downloaded += 1
        elif result == "skipped":
            skipped += 1
        else:
            errors += 1

    print(
        f"Done. {downloaded} downloaded, {skipped} skipped, {errors} errors.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
