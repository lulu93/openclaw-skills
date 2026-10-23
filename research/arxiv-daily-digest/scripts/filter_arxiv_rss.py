#!/usr/bin/env python3
"""
filter_arxiv_rss.py — Download cs.CV RSS, filter by 3D vision keywords,
output ranked candidates with match scores.

Usage:
    python filter_arxiv_rss.py                              # default: cs.CV
    python filter_arxiv_rss.py --category cs.CV --min-score 2 --top 20

Output: tab-separated columns:
    score | arxiv_id | title (truncated) | date | matched_keywords

Author field is NOT extracted from RSS (RSS doesn't contain authors reliably).
Use delegate_task per candidate for full metadata.
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen

RSS_URLS = {
    "cs.CV": "https://rss.arxiv.org/rss/cs.CV",
    "cs.LG": "https://rss.arxiv.org/rss/cs.LG",
    "cs.AI": "https://rss.arxiv.org/rss/cs.AI",
    "cs.RO": "https://rss.arxiv.org/rss/cs.RO",
    "stat.ML": "https://rss.arxiv.org/rss/stat.ML",
}

# Core 3D vision keywords — ordered by specificity (higher-specificity first)
KEYWORDS_3D_VISION = [
    # BA / Geometry optimization
    "bundle adjustment", "implicit ba", "differentiable ba",
    "structure from motion", "visual odometry",
    "epipolar", "trifocal", "fundamental matrix", "essential matrix",
    # 3DGS family
    "3d gaussian splatting", "3dgs", "gaussian splatting",
    # Neural fields
    "neural radiance field", "nerf", "implicit representation",
    "neural field", "signed distance", "neural surface", "sdf",
    # Reconstruction
    "3d reconstruction", "novel view synthesis", "view synthesis",
    "multi-view stereo", "mvs", "stereo matching",
    "mesh reconstruction", "surface reconstruction",
    "volumetric rendering", "differentiable rendering",
    "point cloud", "scene representation",
    # Feed-forward / Learning
    "feed-forward", "feed forward",
    "pose-free", "pose free",
    # 3D generation
    "3d generation",
    # Pose / Depth / SLAM
    "slam", "pose estimation", "camera pose", "depth estimation",
    # Other
    "voxel", "neural implicit",
]

# Proxy URL (optional, for environments behind GFW)
PROXY = os.environ.get("HTTP_PROXY", "")


def fetch_rss(category: str) -> str:
    url = RSS_URLS.get(category)
    if not url:
        # Try direct URL
        url = f"https://rss.arxiv.org/rss/{category}"
    
    print(f"[*] Fetching RSS from {url} ...", file=sys.stderr)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    if PROXY:
        proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
        opener = urllib.request.build_opener(proxy_handler)
        with opener.open(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    else:
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")


def parse_rss(xml_text: str):
    """Parse RSS XML, return list of dicts with title, link, date, description."""
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        
        link_el = item.find("link")
        link = link_el.text.strip() if link_el is not None and link_el.text else ""
        
        date_el = item.find("pubDate")
        date = date_el.text.strip() if date_el is not None and date_el.text else ""
        
        desc_el = item.find("description")
        desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
        
        # content:encoded (often has full abstract)
        content_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        content = content_el.text.strip() if content_el is not None and content_el.text else ""
        
        # Extract arXiv ID from link
        arxiv_id = ""
        if "/abs/" in link:
            arxiv_id = link.split("/abs/")[-1].split("v")[0]
        elif "/pdf/" in link:
            raw = link.split("/pdf/")[-1]
            arxiv_id = raw.split("v")[0].rstrip(".pdf")
        
        items.append({
            "title": title,
            "arxiv_id": arxiv_id,
            "link": link,
            "date": date,
            "description": desc,
            "content": content,
        })
    
    return items


def filter_by_keywords(items):
    """Score each item by keyword match count. Return sorted list with match info."""
    scored = []
    for item in items:
        combined = (item["title"] + " " + item["description"] + " " + item["content"]).lower()
        matched = []
        for kw in KEYWORDS_3D_VISION:
            if kw in combined:
                matched.append(kw)
        if matched:
            scored.append({
                **item,
                "score": len(matched),
                "matched_keywords": matched,
            })
    
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def dedup(candidates, sent_file: str):
    """Remove already-sent IDs (from arxiv_sent_ids.txt)."""
    if not os.path.exists(sent_file):
        return candidates
    
    with open(sent_file) as f:
        sent_raw = [line.strip() for line in f if line.strip()]
    
    def base_id(full_id):
        return full_id.split("v")[0]
    
    sent_bases = {base_id(s) for s in sent_raw}
    
    filtered = []
    skipped = []
    for c in candidates:
        bid = base_id(c["arxiv_id"])
        if bid in sent_bases:
            skipped.append(c["arxiv_id"])
        else:
            filtered.append(c)
    
    if skipped:
        print(f"[*] Skipped {len(skipped)} already-sent IDs: {', '.join(skipped[:5])}{'...' if len(skipped)>5 else ''}", file=sys.stderr)
    
    return filtered


def main():
    parser = argparse.ArgumentParser(description="Filter arXiv RSS by 3D vision keywords")
    parser.add_argument("--category", default="cs.CV", help="RSS category (default: cs.CV)")
    parser.add_argument("--min-score", type=int, default=1, help="Minimum keyword match score")
    parser.add_argument("--top", type=int, default=0, help="Show only top N (0 = all)")
    parser.add_argument("--sent-file", default="/opt/hermes-notes/arxiv_sent_ids.txt",
                        help="Path to sent IDs file for dedup")
    parser.add_argument("--no-dedup", action="store_true", help="Skip dedup")
    parser.add_argument("--output-file", default="", help="Save results to file")
    args = parser.parse_args()
    
    # Fetch
    xml_text = fetch_rss(args.category)
    items = parse_rss(xml_text)
    print(f"[*] Total items in RSS: {len(items)}", file=sys.stderr)
    
    # Filter
    candidates = filter_by_keywords(items)
    print(f"[*] Matched by keywords: {len(candidates)}", file=sys.stderr)
    
    # Dedup
    if not args.no_dedup and os.path.exists(args.sent_file):
        candidates = dedup(candidates, args.sent_file)
        print(f"[*] After dedup: {len(candidates)}", file=sys.stderr)
    
    # Filter by min score
    if args.min_score > 1:
        candidates = [c for c in candidates if c["score"] >= args.min_score]
        print(f"[*] After min-score={args.min_score}: {len(candidates)}", file=sys.stderr)
    
    # Output
    if args.top > 0:
        candidates = candidates[:args.top]
    
    lines = []
    header = f"#score\tarxiv_id\tdate\ttitle\tkeywords"
    lines.append(header)
    for c in candidates:
        title_short = c["title"][:100].replace("\t", " ")
        kws = ", ".join(c["matched_keywords"][:6])
        date_short = c["date"][:25]
        lines.append(f"{c['score']}\t{c['arxiv_id']}\t{date_short}\t{title_short}\t{kws}")
    
    output = "\n".join(lines)
    
    if args.output_file:
        with open(args.output_file, "w") as f:
            f.write(output + "\n")
        print(f"[*] Saved to {args.output_file}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    import urllib.request  # for proxy support
    main()
