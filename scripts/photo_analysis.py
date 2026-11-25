#!/usr/bin/env python3
"""
photo_analysis.py -- Analyse book cover photos using a local VLM via Ollama.

Reads a list of image file paths (one per line) from -i.
Sends each image to a local Ollama VLM model and extracts title, author,
subtitle, and publisher as structured JSON.
Writes results to photo_results.csv in the folder specified by -o.

Progress is written to stderr.

Usage:
    python scripts/photo_analysis.py -i data/input/photos.lst -o data/output/
    python scripts/photo_analysis.py -i data/input/photos.lst -o data/output/ --base-dir data/photos/
    python scripts/photo_analysis.py -i data/input/photos.lst -o data/output/ --model qwen2.5vl:7b
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import ollama

from haddolib.common import write_csv

# --- Constants ---

DEFAULT_MODEL = "qwen2.5vl:7b"
OUTPUT_FILENAME = "photo_results.csv"

CSV_FIELDS = [
    "filename",
    "rack",
    "author",
    "title",
    "subtitle",
    "publisher",
    "confidence",
    "quality",
    "comment",
]

PROMPT = """\
You are a book cataloguing assistant. Examine the book cover in the image and \
extract the following fields. Respond ONLY with a valid JSON object -- no explanation, \
no markdown, no code fences.

Fields:
  "author"     : author(s) or editor(s) as printed on the cover. If multiple authors
                 are listed, separate them with ", " (comma space). Strip courtesy
                 words like "von", "by", "par", "de" from the beginning of the field.
                 Example: "Kurt Bracharz, Tatjana Hauptmann"
  "title"      : main title exactly as printed
  "subtitle"   : subtitle exactly as printed, or "" if not present
  "publisher"  : publisher name exactly as printed, or "" if not visible
  "confidence" : float 0.0-1.0, your estimate of how complete and accurate your
                 extraction is (1.0 = all fields clearly visible and readable,
                 0.0 = you cannot determine anything useful)

Important rules:
- If text appears in all capitals, normalise it to title case.
  Example: "DIE BRIEFE VOM WEIHNACHTSMANN" -> "Die Briefe vom Weihnachtsmann"
- Apply consistent capitalisation -- do not mix cases within a single word.
  Example: "DIogenes" -> "Diogenes"
- Any field may be printed in all capitals on the cover -- apply normalisation to all fields.
- Do not translate, correct spelling, or infer content that is not visible.\
"""


# --- Image loading ---

def load_image_as_base64(path: Path) -> str:
    """Read an image file and return its content as a base64-encoded string."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# --- Prompt ---

def build_prompt() -> str:
    """Return the VLM prompt string."""
    return PROMPT


# --- VLM call ---

def call_vlm(image_b64: str, model: str) -> str:
    """
    Send the image to the local Ollama model.
    Returns the raw response text, or raises on connection error.
    """
    response = ollama.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": build_prompt(),
                "images": [image_b64],
            }
        ],
    )
    return response["message"]["content"]


# --- Response parsing ---

def parse_response(raw_text: str) -> dict | None:
    """
    Attempt to parse the model's response as JSON.
    Returns the parsed dict, or None if parsing fails.

    Handles the common case where the model wraps JSON in markdown code fences.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove opening fence line (```json or ```)
        inner_lines = lines[1:]
        # Remove closing fence if present
        if inner_lines and inner_lines[-1].strip() == "```":
            inner_lines = inner_lines[:-1]
        text = "\n".join(inner_lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# --- Quality assessment ---

def compute_quality(parsed: dict | None) -> str:
    """
    Compute a deterministic quality flag based on field completeness.

    Returns one of:
      "complete" -- author, title, and publisher are all non-empty
      "partial"  -- at least one of author or title is non-empty
      "failed"   -- parsing failed or both author and title are empty
    """
    if parsed is None:
        return "failed"

    author = str(parsed.get("author", "")).strip()
    title = str(parsed.get("title", "")).strip()
    publisher = str(parsed.get("publisher", "")).strip()

    if not author and not title:
        return "failed"

    if author and title and publisher:
        return "complete"

    return "partial"


# --- Per-image processing ---

def process_image(filepath: Path, model: str) -> dict:
    """
    Run the full pipeline for a single image.
    Returns a dict with all CSV_FIELDS populated.
    """
    filename = filepath.name
    rack = _extract_rack(filename)

    try:
        image_b64 = load_image_as_base64(filepath)
    except OSError as e:
        return _error_row(filename, rack, f"Could not read file: {e}")

    try:
        raw_text = call_vlm(image_b64, model)
    except Exception as e:
        return _error_row(filename, rack, f"VLM call failed: {e}")

    parsed = parse_response(raw_text)
    quality = compute_quality(parsed)

    if parsed is None:
        return _error_row(filename, rack, f"JSON parse failed. Raw: {raw_text[:200]}")

    return {
        "filename": filename,
        "rack": rack,
        "author": parsed.get("author", ""),
        "title": parsed.get("title", ""),
        "subtitle": parsed.get("subtitle", ""),
        "publisher": parsed.get("publisher", ""),
        "confidence": _safe_float(parsed.get("confidence", "")),
        "quality": quality,
        "comment": "",
    }


# --- Helpers ---

def _extract_rack(filename: str) -> str:
    """
    Extract the rack number from a filename like 'rack_03 2026-02-17 21.29.39.jpg'.
    Returns the rack number as a zero-padded string (e.g. '03'), or '' if not parseable.

    The filename format is: rack_<NN> <timestamp>.jpg
    Splitting on '_' gives ['rack', '03 2026-02-17 21.29.39'], so we further
    split parts[1] on space and take the first token.
    """
    name = Path(filename).stem  # strip extension
    parts = name.split("_")
    # Expected: ['rack', '03 2026-02-17 ...']
    if len(parts) >= 2 and parts[0].lower() == "rack":
        return parts[1].split()[0]  # '03 2026-...' -> '03'
    return ""


def _safe_float(value: object) -> str:
    """Convert to float string rounded to 2 decimal places, or '' on failure."""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return ""


def _error_row(filename: str, rack: str, comment: str) -> dict:
    """Return a fully populated error row."""
    return {
        "filename": filename,
        "rack": rack,
        "author": "",
        "title": "",
        "subtitle": "",
        "publisher": "",
        "confidence": "",
        "quality": "failed",
        "comment": comment,
    }


# --- I/O helpers ---

def read_image_paths(source, base_dir: Path | None) -> list[Path]:
    """
    Read image file paths from a file-like object.
    If base_dir is given, prepend it to each path.
    Skips blank lines and comment lines (starting with #).
    Warns about lines that don't resolve to existing files.
    """
    paths = []
    missing = []
    for lineno, raw in enumerate(source, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        p = Path(line) if base_dir is None else base_dir / line
        if not p.exists():
            missing.append((lineno, str(p)))
        else:
            paths.append(p)

    if missing:
        print(f"[WARN] {len(missing)} path(s) not found:", file=sys.stderr)
        for lineno, val in missing:
            print(f"       line {lineno}: {val!r}", file=sys.stderr)

    return paths


# --- Main ---

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse book cover photos via local Ollama VLM. Writes semicolon-delimited CSV."
    )
    parser.add_argument(
        "-i", "--input",
        metavar="FILE",
        required=True,
        help="Input file with one image filename per line",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="DIR",
        required=True,
        help="Output directory for photo_results.csv",
    )
    parser.add_argument(
        "--base-dir",
        metavar="DIR",
        default=None,
        help="Optional directory prepended to each filename in the input file",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        default=DEFAULT_MODEL,
        help=f"Ollama model name (default: {DEFAULT_MODEL})",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir) if args.base_dir else None

    # --- Resolve output directory ---
    output_dir = Path(args.output)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[ERROR] Cannot create output directory {output_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    output_path = output_dir / OUTPUT_FILENAME

    # --- Read image paths ---
    with open(args.input, encoding="utf-8-sig") as f:
        paths = read_image_paths(f, base_dir)

    total = len(paths)
    print(f"[INFO] {total} image(s) to process with model '{args.model}'", file=sys.stderr)

    if total == 0:
        print("[WARN] Nothing to do.", file=sys.stderr)
        sys.exit(0)

    # --- Process images ---
    rows = []
    for idx, filepath in enumerate(paths, start=1):
        print(f"[INFO] {idx}/{total} {filepath.name} ...", file=sys.stderr)
        row = process_image(filepath, args.model)
        rows.append(row)
        status = f"quality={row['quality']}, confidence={row['confidence']}"
        print(f"       -> {status}", file=sys.stderr)

    # --- Summary ---
    complete = sum(1 for r in rows if r["quality"] == "complete")
    partial = sum(1 for r in rows if r["quality"] == "partial")
    failed = sum(1 for r in rows if r["quality"] == "failed")
    print(
        f"[INFO] Done. complete={complete}, partial={partial}, failed={failed} / {total}",
        file=sys.stderr,
    )

    # --- Write CSV ---
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        write_csv(rows, f, CSV_FIELDS)
    print(f"[INFO] Output written to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
