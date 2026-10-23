#!/usr/bin/env python3
"""
extract_paper_text.py — Download arXiv PDFs and extract key sections for analysis.

Usage:
    python extract_paper_text.py --ids 2605.12399 2605.11354 2605.12494
    python extract_paper_text.py --ids 2605.12399 --output-dir /tmp/papers

Output: one .txt file per paper with extracted text from key sections.
"""

import argparse
import os
import re
import sys
import tempfile
import urllib.request
from urllib.request import urlopen, Request

# Key section markers to search for
SECTION_MARKERS = [
    "abstract", "introduction", "contribution", "propos", "method",
    "approach", "pipeline", "framework", "architecture",
    "experiment", "result", "dataset", "evaluation",
    "ablation", "comparison", "state-of-the-art", "sota",
    "limitation", "conclusion", "future work",
    "appendix",
]

PROXY = os.environ.get("HTTP_PROXY", "")


def download_pdf(arxiv_id: str, output_dir: str) -> str:
    """Download PDF for an arXiv paper. Returns path to downloaded file."""
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    path = os.path.join(output_dir, f"{arxiv_id}.pdf")
    
    if os.path.exists(path):
        print(f"  [✓] Already cached: {path}", file=sys.stderr)
        return path
    
    print(f"  [*] Downloading {url} ...", file=sys.stderr)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    if PROXY:
        proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
        opener = urllib.request.build_opener(proxy_handler)
        data = opener.open(req, timeout=120).read()
    else:
        data = urlopen(req, timeout=120).read()
    
    with open(path, "wb") as f:
        f.write(data)
    
    print(f"  [✓] Downloaded {len(data)//1024} KB", file=sys.stderr)
    return path


def extract_text(pdf_path: str, max_pages: int = 15) -> str:
    """Extract text from PDF using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        print("  [!] pypdf not installed. Run: pip install pypdf", file=sys.stderr)
        return ""
    
    reader = PdfReader(pdf_path)
    text_parts = []
    for i, page in enumerate(reader.pages):
        if i >= max_pages:
            break
        t = page.extract_text()
        if t:
            text_parts.append(f"\n--- Page {i+1} ---\n{t}")
    
    return "\n".join(text_parts)


def find_sections(text: str, markers: list = None) -> dict:
    """Find section positions in extracted text and return key section content."""
    if markers is None:
        markers = SECTION_MARKERS
    
    text_lower = text.lower()
    sections = {}
    
    positions = []
    for marker in markers:
        idx = text_lower.find(marker)
        if idx >= 0:
            positions.append((idx, marker))
    
    positions.sort()
    
    # Extract section content (from marker to next marker or +2000 chars)
    # Group nearby matches
    merged = []
    for idx, marker in positions:
        start = max(0, idx - 10)
        end = min(len(text), idx + 2000)
        content = text[start:end].strip()
        merged.append((idx, marker, content))
    
    return merged


def extract_experiment_tables(text: str) -> list:
    """Try to find numeric tables in extracted text."""
    # Look for patterns like "Table 1:", "PSNR", "SSIM", etc.
    table_sections = []
    
    # Find lines that look like table data (numbers separated by spaces/tabs)
    table_lines = []
    for line in text.split("\n"):
        # Lines with multiple numbers (potential table rows)
        numbers = re.findall(r'\b\d+\.?\d*\b', line)
        if len(numbers) >= 3 and len(line) < 200:
            table_lines.append(line.strip())
    
    if table_lines:
        table_sections = table_lines[:30]  # Cap at 30 lines
    
    return table_sections


def main():
    parser = argparse.ArgumentParser(description="Extract text from arXiv PDFs for analysis")
    parser.add_argument("--ids", nargs="+", required=True, help="arXiv IDs to process")
    parser.add_argument("--output-dir", default="/tmp/arxiv_extracted", help="Output directory")
    parser.add_argument("--max-pages", type=int, default=12, help="Max pages to extract per paper")
    parser.add_argument("--skip-downloads", action="store_true", help="Skip PDF download, use existing")
    parser.add_argument("--find-tables", action="store_true", help="Also search for experimental tables")
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    pdf_dir = os.path.join(args.output_dir, "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    
    for arxiv_id in args.ids:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"Processing: {arxiv_id}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        
        # Download
        if not args.skip_downloads:
            pdf_path = download_pdf(arxiv_id, pdf_dir)
        else:
            pdf_path = os.path.join(pdf_dir, f"{arxiv_id}.pdf")
            if not os.path.exists(pdf_path):
                print(f"  [!] PDF not found: {pdf_path}", file=sys.stderr)
                continue
        
        # Extract text
        text = extract_text(pdf_path, max_pages=args.max_pages)
        
        # Save full text
        txt_path = os.path.join(args.output_dir, f"{arxiv_id}_text.txt")
        with open(txt_path, "w") as f:
            f.write(text)
        print(f"  [✓] Saved text ({len(text)//1024} KB) to {txt_path}", file=sys.stderr)
        
        # Find sections
        sections = find_sections(text)
        
        # Output key findings to stdout
        print(f"\n{'─'*50}")
        print(f"Paper: {arxiv_id}")
        print(f"{'─'*50}")
        
        for idx, marker, content in sections:
            # Clean content
            content_clean = content[:500].replace("\n", " ").strip()
            print(f"\n  [{marker.upper()}] ...{content_clean}...")
        
        # Tables
        if args.find_tables:
            tables = extract_experiment_tables(text)
            if tables:
                print(f"\n  [TABLE CANDIDATES]")
                for line in tables[:10]:
                    print(f"    {line}")


if __name__ == "__main__":
    main()
