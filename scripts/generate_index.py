#!/usr/bin/env python3
"""Generate complete knowledge base website: index, notes, search, tags, ToC, backlinks, dark mode."""
import os
import re
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict

VAULT_DIR = "/opt/data/obsidian-vault/论文笔记"
PODCAST_FEED = "/opt/hermes/podcast-feed/feed.xml"
CDN_BASE = "https://tf9qzrwt0.hn-bkt.clouddn.com"

# ── Podcast matching ──────────────────────────────────────────────
PODCAST_MAP = {
    "d4rt": ["D4RT"],
    "pointforward": ["PointForward"],
    "slam-former": ["SLAM-Former"],
    "splatam": ["SplaTAM"],
    "vggt-omega": ["VGGT-Omega"],
    "3d-vlm": ["3D-VLM"],
    "3d生成": ["3D 生成"],
    "3d评测": ["3D评测"],
    "feed-forward": ["Feed-Forward 3D 全球生态", "Feed-Forward 前馈重建"],
    "gemdepth": ["GemDepth"],
    "多视图3d目标检测": ["多视图3D目标检测"],
    "查询范式崛起": ["查询范式崛起"],
    "可微ba": ["可微BA"],
    "基础方法": ["基础方法与统一框架", "统一3D框架"],
    "registertoken": ["CLS Token与Register"],
    "arxiv briefing": ["arxiv_briefing"],
}

PODCAST_BADGE = '<span class="podcast-badge">🎙️ 有播客</span>'
PLAYER_HTML = '''<div class="podcast-player">
  <div class="player-header">🎙️ 语音播客</div>
  <audio controls style="width:100%">
    <source src="{url}" type="audio/mpeg">
  </audio>
</div>'''

# ── CSS Variables for dark mode ──────────────────────────────────
COMMON_CSS = '''  --bg: #f5f5f5;
  --card-bg: #fff;
  --text: #333;
  --text-secondary: #555;
  --text-muted: #999;
  --border: #eee;
  --code-bg: #f0f0f0;
  --card-shadow: 0 1px 3px rgba(0,0,0,0.08);
  --card-hover-shadow: 0 4px 12px rgba(0,0,0,0.12);
  --link: #667eea;
  --link-hover: #4a57cc;
  --gradient-from: #667eea;
  --gradient-to: #764ba2;
  --badge-bg: #e8eeff;
  --badge-text: #5566aa;
  --player-bg: #f0f4ff;
  --player-border: #d0d8f0;
  --player-text: #5566aa;
  --table-stripe: #fafafa;
  --toc-bg: #f8f9ff;
  --toc-border: #667eea;
  --broken-link: #999;
  --broken-border: #ddd;
  --tag-bg: #667eea;
  --tag-text: #fff;
  --backlink-bg: #f8f9ff;
  --header-text: #fff;
'''

DARK_CSS = '''  --bg: #1a1a2e;
  --card-bg: #252540;
  --text: #ddd;
  --text-secondary: #bbb;
  --text-muted: #888;
  --border: #3a3a55;
  --code-bg: #2a2a40;
  --card-shadow: 0 1px 3px rgba(0,0,0,0.3);
  --card-hover-shadow: 0 4px 12px rgba(0,0,0,0.5);
  --link: #8899ee;
  --link-hover: #aabbff;
  --gradient-from: #4a3a8a;
  --gradient-to: #5a3a7a;
  --badge-bg: #3a3a60;
  --badge-text: #99aadd;
  --player-bg: #2a2a45;
  --player-border: #3a3a60;
  --player-text: #99aadd;
  --table-stripe: #2a2a40;
  --toc-bg: #2a2a45;
  --toc-border: #8899ee;
  --broken-link: #777;
  --broken-border: #555;
  --tag-bg: #4a3a8a;
  --tag-text: #ddd;
  --backlink-bg: #2a2a45;
  --header-text: #fff;
'''

# ── Breadcrumb HTML ──────────────────────────────────────────────
def breadcrumb_html(category, note_title):
    parts = [('<a href="/">首页</a>', False)]
    if category:
        enc = category.replace(' ', '%20')
        parts.append((f'<a href="/{enc}/">{category}</a>', False))
    if note_title:
        parts.append((note_title, True))
    items = ' <span class="bc-sep">›</span> '.join(
        f'<span class="bc-current">{t}</span>' if active else t for t, active in parts
    )
    return f'<div class="breadcrumb">{items}</div>'

# ── ToC generation ───────────────────────────────────────────────
def extract_toc(content):
    """Extract h1 and h2 headings, return HTML for floating ToC."""
    headings = []
    for line in content.split('\n'):
        m = re.match(r'^##\s+(.+)$', line)
        if m:
            text = re.sub(r'[\*_`]', '', m.group(1))
            anchor = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '-', text).strip('-').lower()
            headings.append(('h2', text, anchor))
        m = re.match(r'^#\s+(.+)$', line)
        if m and not line.startswith('##'):
            text = re.sub(r'[\*_`]', '', m.group(1))
            anchor = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '-', text).strip('-').lower()
            headings.append(('h1', text, anchor))
    if len(headings) < 3:
        return ''
    items = ''.join(
        f'<li class="toc-{level}"><a href="#{anchor}">{text}</a></li>\n'
        for level, text, anchor in headings
    )
    return f'''<div class="toc-container">
  <details>
  <summary>📑 目录</summary>
  <ul class="toc-list">
{items}  </ul>
  </details>
</div>\n'''

# ── Utility functions ────────────────────────────────────────────
def sec_to_display(seconds_str):
    try:
        s = int(seconds_str)
        m, s = divmod(s, 60)
        return f"{m}:{s:02d}"
    except:
        return seconds_str

def load_podcasts():
    podcasts = []
    try:
        tree = ET.parse(PODCAST_FEED)
        for item in tree.getroot().findall('.//item'):
            title_el, enc, dur_el = item.find('title'), item.find('enclosure'), item.find('{http://www.itunes.com/dtds/podcast-1.0.dtd}duration')
            if title_el is None or enc is None: continue
            cdn_url = enc.get('url', '')
            if not cdn_url: continue
            filename = cdn_url.rsplit('/', 1)[-1]
            local_url = f'/podcast/audio/{filename}'
            podcasts.append({'title': title_el.text or '', 'url': local_url, 'duration': dur_el.text if dur_el is not None else ''})
    except Exception as e:
        print(f"  ⚠️ 播客加载失败: {e}")
    return podcasts

def find_podcast(note_title, all_podcasts):
    nt = note_title.lower()
    for pod in all_podcasts:
        pt = pod['title'].lower().replace(' ', '').replace('_', '').replace('—', '')
        for map_key, note_keywords in PODCAST_MAP.items():
            if map_key in pt:
                for nk in note_keywords:
                    if nk.lower() in nt or nt in nk.lower():
                        return (pod['url'], pod['title'], pod.get('duration', ''))
    return None

def build_wikilink_map():
    wl_map = {}
    for entry in os.listdir(VAULT_DIR):
        if entry.startswith('.'): continue
        full = os.path.join(VAULT_DIR, entry)
        if os.path.isdir(full):
            for fname in os.listdir(full):
                if not fname.endswith('.md'): continue
                title = fname[:-3]
                enc_entry = entry.replace(' ', '%20')
                enc_file = fname[:-3].replace(' ', '%20') + '.html'
                wl_map[title.lower()] = f'/{enc_entry}/{enc_file}'
        elif entry.endswith('.md'):
            title = entry[:-3]
            enc_file = entry[:-3].replace(' ', '%20') + '.html'
            wl_map[title.lower()] = f'/{enc_file}'
    return wl_map

def build_backlink_map():
    """Scan all .md files for [[wikilinks]] to build reverse reference map."""
    bl_map = defaultdict(list)
    for entry in os.listdir(VAULT_DIR):
        if entry.startswith('.'): continue
        full = os.path.join(VAULT_DIR, entry)
        if os.path.isdir(full):
            for fname in os.listdir(full):
                if not fname.endswith('.md'): continue
                fpath = os.path.join(full, fname)
                content = open(fpath).read()
                source_title = fname[:-3]
                for m in re.finditer(r'\[\[([^\]]+)\]\]', content):
                    target = m.group(1).split('|')[0].strip().lower()
                    bl_map[target].append(source_title)
        elif entry.endswith('.md'):
            fpath = full
            content = open(fpath).read()
            source_title = entry[:-3]
            for m in re.finditer(r'\[\[([^\]]+)\]\]', content):
                target = m.group(1).split('|')[0].strip().lower()
                bl_map[target].append(source_title)
    return bl_map

def build_tag_index():
    """Scan frontmatter for tags, return {tag: [note_title, note_url, category]}"""
    tag_idx = defaultdict(list)
    for entry in os.listdir(VAULT_DIR):
        if entry.startswith('.'): continue
        full = os.path.join(VAULT_DIR, entry)
        if os.path.isdir(full):
            for fname in os.listdir(full):
                if not fname.endswith('.md'): continue
                fpath = os.path.join(full, fname)
                tags = extract_tags(fpath)
                title = fname[:-3]
                enc_entry = entry.replace(' ', '%20')
                enc_file = fname[:-3].replace(' ', '%20') + '.html'
                url = f'/{enc_entry}/{enc_file}'
                for tag in tags:
                    tag = tag.strip()
                    if len(tag) < 2:  # skip empty/single-char tags
                        continue
                    tag_idx[tag].append((title, url, entry))
    return tag_idx

def extract_tags(filepath):
    """Extract tags from frontmatter."""
    try:
        content = open(filepath).read()
        m = re.search(r'^tags:\s*\[([^\]]+)\]', content, re.MULTILINE)
        if m:
            return [t.strip().strip('"\'') for t in m.group(1).split(',')]
        m = re.search(r'^tags:\s*\n(\s*-\s*[^\n]+)+', content, re.MULTILINE)
        if m:
            tags = []
            for t in m.group(0).split('\n')[1:]:
                if t.strip().startswith('---'):  # skip YAML delimiter
                    continue
                tag = re.sub(r'^\s*-\s*', '', t).strip().strip('"\'')
                if tag:
                    tags.append(tag)
            return tags
    except: pass
    return []

# ── Mermaid / diagram helpers ────────────────────────────────────
MERMAID_JS = '''<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
.mermaid-container { cursor: zoom-in; transition: transform 0.2s; }
.mermaid-container:hover { transform: scale(1.01); }
.mermaid-zoom-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 9999; justify-content: center; align-items: center; cursor: zoom-out; }
.mermaid-zoom-overlay.active { display: flex; }
.mermaid-zoom-overlay svg { max-width: 95vw; max-height: 95vh; background: white; border-radius: 8px; padding: 10px; box-shadow: 0 10px 40px rgba(0,0,0,0.5); }
@media (prefers-color-scheme: dark) {
  .mermaid-zoom-overlay svg { background: #252540; }
}
</style>
<script>
document.addEventListener('DOMContentLoaded', function() {
  var isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  mermaid.initialize({
    startOnLoad:true,
    theme:'base',
    fontFamily:'-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif',
    themeVariables: isDark ? {
      primaryColor:'#4a3a8a33', primaryTextColor:'#ddd', primaryBorderColor:'#8899ee',
      lineColor:'#8899ee', secondaryColor:'#2a2a45', tertiaryColor:'#252540',
      mainBkg:'#2a2a45', nodeBorder:'#8899ee', clusterBkg:'#252540', clusterBorder:'#3a3a55',
      titleColor:'#ddd', edgeLabelBackground:'#252540', nodeTextColor:'#ddd'
    } : {
      primaryColor:'#667eea33', primaryTextColor:'#333', primaryBorderColor:'#667eea',
      lineColor:'#667eea', secondaryColor:'#f0f4ff', tertiaryColor:'#fff',
      mainBkg:'#f0f4ff', nodeBorder:'#667eea', clusterBkg:'#fff', clusterBorder:'#d0d8f0',
      titleColor:'#333', edgeLabelBackground:'#fff', nodeTextColor:'#333'
    }
  });
  // Click-to-zoom for mermaid diagrams
  document.querySelectorAll('.mermaid-container').forEach(function(el) {
    el.addEventListener('click', function() {
      var svg = this.querySelector('svg');
      if (!svg) return;
      var clone = svg.cloneNode(true);
      var overlay = document.createElement('div');
      overlay.className = 'mermaid-zoom-overlay active';
      overlay.appendChild(clone);
      overlay.addEventListener('click', function() { this.remove(); });
      document.body.appendChild(overlay);
    });
  });
});
</script>'''

MERMAID_CSS = '''
.mermaid-container { background: var(--card-bg); border-radius: 12px; padding: 20px; margin: 16px 0; box-shadow: var(--card-shadow); overflow-x: auto; text-align: center; }
.mermaid-container svg { max-width: 100%; height: auto; }
.mermaid-label { font-size: 12px; color: var(--text-muted); text-align: center; margin-top: 8px; }
.tree-diagram { background: #1a1a2e; color: #aabbee; border-radius: 12px; padding: 18px 22px; margin: 16px 0; box-shadow: 0 4px 20px rgba(0,0,0,0.3); overflow-x: auto; font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace; font-size: 13px; line-height: 1.7; position: relative; white-space: pre-wrap; word-wrap: normal; }
.tree-diagram::before { content: '📂 演化路线'; display: block; font-family: -apple-system, 'Segoe UI', sans-serif; font-size: 11px; color: #8899cc; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #334; text-transform: uppercase; letter-spacing: 1px; white-space: normal; }
.align-table { background: var(--card-bg); border-radius: 10px; padding: 12px; margin: 12px 0; box-shadow: var(--card-shadow); overflow-x: auto; }
.align-table table { border-collapse: collapse; width: 100%; }
.align-table td { padding: 8px 12px; text-align: center; font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 13px; border: 1px solid var(--border); color: var(--text); }
.align-table td.at-label { font-family: -apple-system, 'Segoe UI', sans-serif; font-weight: 600; color: var(--text-secondary); text-align: left; border-right: 2px solid var(--link); white-space: nowrap; }
.align-table td.at-highlight { background: var(--backlink-bg); font-weight: 600; color: var(--link); }
.align-table td.at-num { color: var(--link); font-weight: 600; }
.align-table td.at-header { font-family: -apple-system, 'Segoe UI', sans-serif; font-weight: 700; padding: 10px 14px; text-align: center; border-bottom: 2px solid var(--link); background: var(--backlink-bg); color: var(--text); }'''

def _sanitize_mermaid_id(label):
    """Create a safe node ID from a label."""
    s = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '_', label[:30]).strip('_')
    if not s or s[0].isdigit():
        s = 'n' + s
    return s[:40]

def _sanitize_mermaid_text(text):
    """Escape special chars in mermaid node labels."""
    return text.replace('"', '\\"').replace('(', '（').replace(')', '）').replace('[', '【').replace(']', '】')

def ascii_tree_to_mermaid(code_text):
    """Convert ASCII tree diagram to mermaid graph TD.
    Returns mermaid HTML string, or None if it can't be parsed.
    """
    lines = code_text.strip().split('\n')
    if not lines:
        return None
    
    has_branch_chars = any('├──' in l or '└──' in l or '├─' in l or '└─' in l for l in lines)
    has_flow_arrows = any('▼' in l for l in lines)
    if not has_branch_chars and not has_flow_arrows:
        return None
    
    # 🚨 Hybrid diagrams with Unicode arrows (↘↙↗↖) are too complex
    # for mermaid conversion — fall back to styled <pre>
    has_unicode_arrows = any(l for l in lines if re.search(r'[\u2198\u2199\u2197\u2196]', l))
    if has_unicode_arrows:
        return None
    
    # 🚨 Box-framed diagrams (┌─┐ style) or multi-column layouts → skip
    # These are typically analytical tables or pipeline diagrams, not trees
    has_box_corners = any('┌─' in l for l in lines) or any('└─' in l for l in lines)
    if has_box_corners:
        return None
    
    # 🚨 Flow diagrams with │ branches/annotations → too complex for linear mermaid
    # These typically have ├─ or └─ (single-hyphen branches) + │ annotations
    has_vertical_bars = any('│' in l for l in lines)
    if has_flow_arrows and has_vertical_bars:
        return None
    
    # 🚨 If no standard ├──└── but has ├─└─ (single hyphen format), skip mermaid
    if not has_branch_chars and has_flow_arrows and not has_vertical_bars:
        # Check if it's really just a simple pipeline, not a complex diagram
        non_empty = [l for l in lines if l.strip()]
        if len(non_empty) == len([l for l in lines if l.strip() and l.strip() not in ('│', '▼')]):
            pass  # Simple linear flow
        else:
            return None
    
    nodes = []      # list of (id, label)
    styles = []     # list of "style id fill:...,stroke:..."
    edges = []      # list of "id1 -->|label| id2" or "id1 --> id2"
    node_idx = [0]
    
    def nid():
        node_idx[0] += 1
        return f'n{node_idx[0]}'
    
    def safe(t):
        return t.replace('"', '\\"').replace('(', '（').replace(')', '）').replace('[', '【').replace(']', '】').replace(',', '，')
    
    # ── Pattern A: Evolution tree (├── └──) ──
    if has_branch_chars:
        # Find root
        root_label = ''
        for line in lines:
            s = line.strip()
            if s and not any(c in s for c in ['├──', '└──', '│']):
                root_label = s
                break
        if not root_label:
            return None
        
        root_id = nid()
        nodes.append((root_id, safe(root_label)))
        styles.append(f'style {root_id} fill:#667eea44,stroke:#667eea,stroke-width:2px')
        
        # Parse children
        current_child = None
        current_annos = []
        
        root_offset = next(i for i, l in enumerate(lines) if root_label in l)
        for line in lines[root_offset:]:
            s = line.strip()
            if not s:
                continue
            if s.startswith('├──') or s.startswith('└──') or s.startswith('├─') or s.startswith('└─'):
                # Save previous child edges before starting new child
                if current_child:
                    if current_annos:
                        first = safe(current_annos[0][:60])
                        edges.append(f'{root_id} -->|"{first}"| {current_child}')
                    else:
                        edges.append(f'{root_id} --> {current_child}')
                
                # Start new child
                label = re.sub(r'^[├└]─*\s*', '', s)
                current_child = nid()
                nodes.append((current_child, safe(label)))
                styles.append(f'style {current_child} fill:#764ba244,stroke:#764ba2')
                current_annos = []
                
            elif s.startswith('│') or s.startswith(' '):
                anno = re.sub(r'^[││]\s*', '', s).strip()
                if anno and current_child:
                    current_annos.append(anno)
        
        # Handle last child
        if current_child:
            if current_annos:
                first = safe(current_annos[0][:60])
                edges.append(f'{root_id} -->|"{first}"| {current_child}')
            else:
                edges.append(f'{root_id} --> {current_child}')
    
    # ── Pattern B: Workflow pipeline (▼) ──
    elif has_flow_arrows:
        prev_id = None
        for line in lines:
            s = line.strip()
            if not s or s == '│' or s == '▼':
                continue
            cid = nid()
            nodes.append((cid, safe(s[:60])))
            if prev_id:
                edges.append(f'{prev_id} --> {cid}')
            prev_id = cid
    
    if not edges:
        return None
    
    mermaid_lines = ['graph TD']
    for nid_, label in nodes:
        mermaid_lines.append(f'  {nid_}["{label}"]')
    mermaid_lines.extend(f'  {s}' for s in styles)
    mermaid_lines.extend(f'  {e}' for e in edges)
    
    return '<div class="mermaid-container"><div class="mermaid">' + '\n'.join(mermaid_lines) + '</div></div>'

def is_ascii_tree_block(code_text):
    """Detect if a code block is an ASCII tree/flow diagram (has tree connectors)."""
    lines = code_text.split('\n')
    tree_lines = sum(1 for l in lines if '├──' in l or '└──' in l or '│' in l)
    if tree_lines >= 2:
        return True
    # Also detect box-drawing diagrams (┌┐└┘├┤┬┴┼) that aren't simple lines
    box_lines = sum(1 for l in lines
                    if re.search(r'[\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c]', l))
    return box_lines >= 2

def is_ascii_alignment_table(code_text):
    """Detect if a code block is a multi-row alignment table (like attention distribution).
    Pattern: multiple lines have the same number of │ characters, indicating columns.
    """
    lines = [l for l in code_text.split('\n') if l.strip()]
    if len(lines) < 3:
        return False
    # Check if it's NOT a tree (no ├── or └──)
    if any('├──' in l or '└──' in l for l in lines):
        return False
    # Count │ per line (ignore lines that are just separators like "  │  ")
    pipe_counts = [l.count('│') for l in lines]
    non_zero = [c for c in pipe_counts if c > 0]
    if len(non_zero) < 3:
        return False
    # Check if majority of non-zero lines have similar │ count (within 1)
    # Use the most common count as reference
    from collections import Counter
    most_common_count = Counter(non_zero).most_common(1)[0][0]
    matching = sum(1 for c in non_zero if abs(c - most_common_count) <= 1)
    # At least 60% of non-zero lines should have similar count
    return matching >= len(non_zero) * 0.6

def alignment_table_to_html(code_text):
    """Convert alignment table diagram (multi-row │ chart) to styled HTML table."""
    lines = [l.rstrip() for l in code_text.split('\n') if l.strip()]
    if len(lines) < 3:
        return None
    
    # Parse rows: split each line by │, clean cells
    raw_rows = []
    for line in lines:
        if all(c in ' │─═' for c in line):
            continue
        parts = [p.strip() for p in line.split('│')]
        while parts and not parts[-1]:
            parts.pop()
        if parts:
            raw_rows.append(parts)
    
    if len(raw_rows) < 3:
        return None
    
    # Detect if first row is header (no │ in original, so raw_rows[0] has 1 part)
    is_header = len(raw_rows[0]) <= 2
    
    # Determine max columns from data rows
    data_start = 1 if is_header else 0
    max_cols = max(len(r) for r in raw_rows[data_start:])
    
    # Normalize all rows
    rows = []
    for r in raw_rows:
        while len(r) < max_cols:
            r.append('')
        rows.append(r)
    
    # Build HTML
    html = '<div class="align-table"><table>\n'
    for ri, row in enumerate(rows):
        if is_header and ri == 0:
            text = row[0]
            text = re.sub(r'[─═]+', '', text)
            text = re.sub(r'---', ' → ', text)
            text = re.sub(r'\s+', ' ', text).strip().rstrip(':').strip()
            html += f'  <tr><td colspan="{max_cols}" class="at-header">{text}</td></tr>\n'
            continue
        html += '  <tr>\n'
        for ci, cell in enumerate(row[:max_cols]):
            clean = re.sub(r'[─═]+', '', cell)
            clean = re.sub(r'---', ' ', clean)
            clean = re.sub(r'\s+', ' ', clean).strip()
            cls = ''
            if ci == 0:
                cls = ' class="at-label"'
            elif clean in ('稀释', '尖峰', '再次稀释'):
                cls = ' class="at-highlight"'
            elif re.match(r'^[\d/]+$', clean.replace('(','').replace(')','')):
                cls = ' class="at-num"'
            html += f'    <td{cls}>{clean}</td>\n'
        html += '  </tr>\n'
    html += '</table></div>\n'
    return html

def is_evolution_path(text):
    """Detect if a text line is an evolution/flow path (3+ → arrows).
    Heuristics to avoid false positives:
    - Items should be relatively short (< 60 chars each)
    - Should not contain colons before arrows (descriptions, not paths)
    - Should not start with bold markers (headings/emphasis)
    - Items should be mostly consecutive (no numbers mixed in)
    """
    count = text.count('→') + text.count('->')
    if count < 3:
        return False
    # Skip if line has colon with arrows (likely a description)
    colon_pos = text.find('：') if '：' in text else text.find(':')
    arrow_pos = text.find('→') if '→' in text else text.find('->')
    if colon_pos >= 0 and colon_pos < arrow_pos:
        return False
    # Skip if line is very long (> 300 chars) – likely a paragraph
    if len(text) > 300:
        return False
    # Parse items and check each is reasonably short
    items = re.split(r'\s*(?:→|->)\s*', text.strip())
    items = [i.strip() for i in items if i.strip()]
    if len(items) < 3:
        return False
    # Each item should be < 40 chars (paper names, method names, years)
    # Allow first item to be longer (may have a short prefix)
    for i, item in enumerate(items):
        if len(item) > 40:
            return False
    return True

def evolution_path_to_mermaid(text, idx):
    """Convert an evolution path like 'A → B → C → D' to mermaid HTML."""
    # Parse items separated by → or ->
    items = re.split(r'\s*(?:→|->)\s*', text.strip())
    if len(items) < 3:
        return None
    # Filter out empty items
    items = [i.strip() for i in items if i.strip()]
    if len(items) < 3:
        return None
    
    lines = []
    for i, item in enumerate(items):
        node_id = f'n{i}'
        # Clean display text: wrap in quotes, escape special chars
        display = item.strip().rstrip('.')
        lines.append(f'  {node_id}["{display}"]')
    for i in range(len(items) - 1):
        lines.append(f'  n{i} --> n{i+1}')
    
    mermaid_code = 'graph LR\n' + '\n'.join(lines)
    return f'<div class="mermaid-container"><div class="mermaid">{mermaid_code}</div></div>'

def is_multi_line_workflow(lines, line_idx):
    """Check if current line is start of a multi-line workflow (indented arrow chains)."""
    if line_idx >= len(lines) - 1:
        return False
    line = lines[line_idx].strip()
    if '→' not in line and '->' not in line:
        return False
    # Check if the line has arrows and next line is indented with arrows
    if line_idx + 1 < len(lines):
        next_line = lines[line_idx + 1]
        if next_line.startswith(('    ', '  ', '\t')) and ('→' in next_line or '->' in next_line):
            return True
    return False
def md_to_html(content, wikilink_map=None):
    html = ""
    in_code, in_list, in_mermaid, in_table = False, False, False, False
    in_display_math = False
    mermaid_buf, code_buf, display_math_buf = [], [], []
    for line in content.split('\n'):
        if line.strip().startswith('```'):
            if in_mermaid:
                # Close mermaid block
                mermaid_code = '\n'.join(mermaid_buf)
                html += f'<div class="mermaid-container"><div class="mermaid">{mermaid_code}</div></div>\n'
                mermaid_buf = []
                in_mermaid = False
                in_code = False
                continue
            if in_code:
                # Close regular code block, check if ASCII tree diagram
                raw_code = '\n'.join(code_buf)
                code_buf = []
                # Priority: mermaid tree > alignment table > styled pre > plain code
                mermaid_converted = ascii_tree_to_mermaid(raw_code)
                if mermaid_converted:
                    html += mermaid_converted + '\n'
                elif is_ascii_alignment_table(raw_code):
                    table_html = alignment_table_to_html(raw_code)
                    html += (table_html if table_html else f'<pre class="align-code">{raw_code}</pre>\n')
                elif is_ascii_tree_block(raw_code):
                    html += f'<pre class="tree-diagram">{raw_code}</pre>\n'
                else:
                    html += f'<pre><code>{raw_code}</code></pre>\n'
                in_code = False
            else:
                lang = line.strip()[3:].strip()
                if lang == 'mermaid':
                    in_mermaid = True
                    in_code = True  # prevent other processing
                    continue
                # Start buffering regular code block
                in_code = True
                code_buf = []
            continue
        if in_mermaid:
            mermaid_buf.append(line)
            continue
        if in_code:
            code_buf.append(line)
            continue
        if line.strip() == '---' and html == '': continue
        if html == '' and line.startswith(('title:', 'arxiv_id:', 'created:', 'tags:')): continue
        if line.strip() in ('---', '***', '___'):
            html += '<hr>\n'; continue
        m = re.match(r'^(#{1,6})\s+(.+)$', line)
        if m:
            level = len(m.group(1))
            text = m.group(2)
            anchor = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '-', re.sub(r'[\*_`]', '', text)).strip('-').lower()
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
            html += f'<h{level} id="{anchor}">{text}</h{level}>\n'
            continue
        if line.strip().startswith(('- ', '* ')):
            if not in_list:
                html += '<ul>\n'
                in_list = True
            text = line.strip()[2:]
            # Check if bullet point is an evolution path
            if is_evolution_path(text):
                mermaid_html = evolution_path_to_mermaid(text, 0)
                if mermaid_html:
                    html += f'  <li>{mermaid_html}</li>\n'
                    continue
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
            text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
            text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
            html += f'  <li>{text}</li>\n'
            continue
        else:
            if in_list:
                html += '</ul>\n'
                in_list = False
        if '|' in line and line.strip().startswith('|'):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if all(re.match(r'^[-:]+\s*$', c) for c in cells): continue
            # Skip lines that aren't real tables (e.g. "||5. item" — first cell empty)
            if not cells or (len(cells) >= 1 and not cells[0]): continue
            if not in_table:
                html += '<table>\n<tbody>\n'
                in_table = True
            html += '<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>\n'
            continue
        else:
            if in_table:
                html += '</tbody>\n</table>\n'
                in_table = False
        if line.strip() == '':
            if in_display_math:
                display_math_buf.append('')
                continue
            html += '</p>\n<p>\n' if html.endswith('</p>\n') else ''
            continue
        if line.strip() == '$$':
            if in_display_math:
                # Close display math block
                content_str = '\n'.join(display_math_buf)
                html += '<div class="math">\n$$\n' + content_str + '\n$$\n</div>\n'
                display_math_buf = []
                in_display_math = False
            else:
                # Open display math block — close any open <p>
                if html.endswith('</p>\n'):
                    pass  # will be appended after
                elif html.endswith('<p>\n'):
                    html = html[:-4]  # remove unclosed <p>
                elif html.rstrip().endswith('</p>'):
                    pass
                in_display_math = True
            continue
        if in_display_math:
            display_math_buf.append(line.rstrip())
            continue
        text = line
        # Check if standalone line is an evolution path
        stripped = text.strip()
        if is_evolution_path(stripped) and len(stripped) < 300:
            # Check it's not inside a table
            if not stripped.startswith('|'):
                mermaid_html = evolution_path_to_mermaid(stripped, 0)
                if mermaid_html:
                    html += mermaid_html + '\n'
                    continue
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        text = re.sub(r'!\[\[(.+?)\]\]', r'<a href="\1" target="_blank" class="img-link"><img src="\1" alt="image" style="max-width:100%" loading="lazy"></a>', text)
        text = re.sub(r'!\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" class="img-link"><img src="\2" alt="\1" style="max-width:100%" loading="lazy"></a>', text)
        if wikilink_map:
            def replace_wikilink(m):
                inner = m.group(1)
                target, display = (inner.split('|', 1) + [inner])[:2]
                url = wikilink_map.get(target.lower())
                return f'<a href="{url}">{display}</a>' if url else f'<span class="wikilink-broken">{display}</span>'
            text = re.sub(r'\[\[([^\]]+)\]\]', replace_wikilink, text)
        if not html.endswith('</p>\n'):
            html += f'<p>{text}\n'
        else:
            html = html[:-5] + text + '\n</p>\n'
    if in_mermaid:
        mermaid_code = '\n'.join(mermaid_buf)
        html += f'<div class="mermaid-container"><div class="mermaid">{mermaid_code}</div></div>\n'
    if in_code:
        raw_code = '\n'.join(code_buf)
        mermaid_converted = ascii_tree_to_mermaid(raw_code)
        if mermaid_converted:
            html += mermaid_converted + '\n'
        elif is_ascii_alignment_table(raw_code):
            table_html = alignment_table_to_html(raw_code)
            html += (table_html if table_html else f'<pre class="align-code">{raw_code}</pre>\n')
        elif is_ascii_tree_block(raw_code):
            html += f'<pre class="tree-diagram">{raw_code}</pre>\n'
        else:
            html += f'<pre><code>{raw_code}</code></pre>\n'
    if in_display_math:
        content_str = '\n'.join(display_math_buf)
        html += '<div class="math">\n$$\n' + content_str + '\n$$\n</div>\n'
    if in_list: html += '</ul>\n'
    if in_table: html += '</tbody>\n</table>\n'
    return html.strip()

# ── HTML wrappers ────────────────────────────────────────────────
def common_head(title, extra_head=''):
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - 论文知识库</title>
<script>
MathJax = {{
  tex: {{
    inlineMath: [['$', '$']],
    processEscapes: true
  }},
  options: {{ skipHtmlTypes: 'script|noscript|style' }}
}};
window.MathJax = MathJax;
</script>
<script src="/assets/mathjax/tex-chtml.min.js"></script>
<style>
:root {{ {COMMON_CSS} }}
@media (prefers-color-scheme: dark) {{ :root {{ {DARK_CSS} }} }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.8; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, var(--gradient-from) 0%, var(--gradient-to) 100%); color: var(--header-text); padding: 20px 30px; border-radius: 12px; margin-bottom: 20px; }}
.header h1 {{ font-size: 20px; }}
.header .back {{ float: right; color: rgba(255,255,255,0.8); text-decoration: none; font-size: 14px; }}
.header .back:hover {{ color: white; }}
.breadcrumb {{ font-size: 12px; color: rgba(255,255,255,0.7); margin-bottom: 8px; }}
.breadcrumb a {{ color: rgba(255,255,255,0.8); text-decoration: none; }}
.breadcrumb a:hover {{ color: white; text-decoration: underline; }}
.bc-sep {{ margin: 0 6px; opacity: 0.5; }}
.bc-current {{ color: white; }}
.podcast-player {{ background: var(--player-bg); border: 1px solid var(--player-border); border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }}
.podcast-player .player-header {{ font-size: 13px; color: var(--player-text); margin-bottom: 8px; font-weight: 600; }}
.podcast-player audio {{ width: 100%; height: 40px; }}
.content {{ background: var(--card-bg); border-radius: 12px; padding: 30px 35px; box-shadow: var(--card-shadow); }}
.content h1 {{ font-size: 22px; color: var(--text); margin: 24px 0 12px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
.content h2 {{ font-size: 18px; color: var(--text-secondary); margin: 20px 0 10px; }}
.content h3 {{ font-size: 16px; color: var(--text-muted); margin: 16px 0 8px; }}
.content p {{ margin: 8px 0; }}
.content a {{ color: var(--link); text-decoration: none; }}
.content a:hover {{ text-decoration: underline; }}
.content code {{ background: var(--code-bg); padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
.content pre {{ background: var(--code-bg); padding: 14px; border-radius: 8px; overflow-x: auto; font-size: 13px; line-height: 1.5; margin: 12px 0; }}
.content pre code {{ background: none; padding: 0; }}
.content hr {{ border: none; border-top: 1px solid var(--border); margin: 20px 0; }}
.content ul {{ padding-left: 20px; margin: 8px 0; }}
.content li {{ margin: 4px 0; }}
.content img {{ max-width: 100%; border-radius: 8px; margin: 12px 0; }}
.img-link {{ display: inline-block; max-width: 100%; cursor: zoom-in; }}
.img-link:hover {{ opacity: 0.9; }}\n{MERMAID_CSS}\n.content table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }}
.content td {{ border: 1px solid var(--border); padding: 8px; }}
.content tr:nth-child(even) {{ background: var(--table-stripe); }}
.content blockquote {{ border-left: 4px solid var(--toc-border); padding: 8px 16px; background: var(--backlink-bg); margin: 12px 0; border-radius: 4px; }}
.wikilink-broken {{ color: var(--broken-link); border-bottom: 1px dashed var(--broken-border); cursor: default; }}
.tags {{ margin: 8px 0; }}
.tag {{ display: inline-block; background: var(--tag-bg); color: var(--tag-text); padding: 2px 10px; border-radius: 12px; font-size: 11px; margin: 2px; text-decoration: none; }}
.tag:hover {{ opacity: 0.85; }}
.toc-container {{ background: var(--toc-bg); border-radius: 10px; margin-bottom: 16px; border-left: 3px solid var(--toc-border); overflow: hidden; }}
.toc-container details {{ padding: 0; }}
.toc-container summary {{ list-style: none; cursor: pointer; padding: 10px 14px; user-select: none; -webkit-user-select: none; display: flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 600; color: var(--text-secondary); }}
.toc-container summary::-webkit-details-marker {{ display: none; }}
.toc-container summary::before {{ content: '▶'; font-size: 10px; transition: transform 0.2s; color: var(--link); }}
.toc-container details[open] summary::before {{ content: '▼'; }}
.toc-list {{ list-style: none; font-size: 13px; padding: 0 14px 10px; max-height: 60vh; overflow-y: auto; }}
.toc-list li {{ margin: 4px 0; }}
.toc-list a {{ color: var(--link); text-decoration: none; }}
.toc-list a:hover {{ text-decoration: underline; }}
.toc-h2 {{ padding-left: 16px; }}
@media (min-width: 768px) {{ .toc-container details {{ display: block; }}
  .toc-container summary::before {{ content: ''; }}
  .toc-container summary {{ cursor: default; }} }}
.backlinks {{ margin-top: 24px; padding: 16px 20px; background: var(--backlink-bg); border-radius: 10px; }}
.backlinks h3 {{ font-size: 14px; color: var(--text-secondary); margin-bottom: 8px; }}
.backlinks ul {{ list-style: none; padding: 0; }}
.backlinks li {{ margin: 3px 0; font-size: 13px; }}
.backlinks a {{ color: var(--link); text-decoration: none; }}
.backlinks a:hover {{ text-decoration: underline; }}
.footer {{ text-align: center; color: var(--text-muted); font-size: 12px; padding: 20px; }}
.footer a {{ color: var(--link); text-decoration: none; }}
{extra_head}
</style>
{MERMAID_JS}
</head>'''

def make_backlinks_html(note_title, backlink_map, wikilink_map):
    sources = backlink_map.get(note_title.lower(), [])
    if not sources: return ''
    items = []
    seen = set()
    for src in sources:
        if src.lower() in seen: continue
        seen.add(src.lower())
        url = wikilink_map.get(src.lower(), '#')
        items.append(f'<li><a href="{url}">{src}</a></li>')
    if not items: return ''
    return f'''<div class="backlinks">
  <h3>🔗 被以下笔记引用 ({len(items)})</h3>
  <ul>{''.join(items)}</ul>
</div>\n'''

def make_tags_html(filepath):
    tags = extract_tags(filepath)
    if not tags: return ''
    links = ''.join(f'<a href="/标签/{t}.html" class="tag">{t}</a> ' for t in tags)
    return f'<div class="tags">{links}</div>\n'

# ── Note page ────────────────────────────────────────────────────

DISCUSS_DIR = os.path.join(VAULT_DIR, "讨论记录")
# ── Side-panel discussion assistant ──
_DISCUSS_INLINE_STYLES = '''
.page-layout { display: flex; gap: 24px; align-items: flex-start; }
.page-content { flex: 1; min-width: 0; }
.discuss-panel { width: 340px; flex-shrink: 0; position: sticky; top: 20px; align-self: flex-start; max-height: calc(100vh - 40px); overflow-y: auto; }
@media (max-width: 900px) {
  .page-layout { flex-direction: column; }
  .discuss-panel { width: 100%; position: static; max-height: none; }
}
.discuss-section { padding: 16px; background: var(--card-bg); border-radius: 12px; box-shadow: var(--card-shadow); }
.discuss-section h2 { font-size: 16px; margin: 0 0 12px; color: var(--text); }
.discuss-container { }
.qa-history { margin-bottom: 10px; }
.qa-summary { font-size: 13px; cursor: pointer; color: var(--link); padding: 6px 10px; background: var(--backlink-bg); border-radius: 8px; user-select: none; }
.qa-list { padding: 8px 0; }
.qa-item { padding: 10px 12px; margin-bottom: 8px; background: var(--backlink-bg); border-radius: 8px; border-left: 3px solid var(--link); }
.qa-item-new { animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.qa-q { font-weight: 600; font-size: 13px; color: var(--text); margin-bottom: 4px; }
.qa-a { font-size: 13px; color: var(--text-secondary); line-height: 1.7; white-space: pre-wrap; }
.discuss-input-area { display: flex; gap: 8px; margin-top: 10px; }
.discuss-input-area input { flex: 1; padding: 10px 14px; border: 2px solid var(--border); border-radius: 8px; font-size: 14px; outline: none; background: var(--card-bg); color: var(--text); }
.discuss-input-area input:focus { border-color: var(--link); }
.discuss-input-area button { padding: 10px 20px; background: var(--link); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }
.discuss-input-area button:hover { opacity: 0.9; }
.discuss-input-area button:disabled { opacity: 0.5; cursor: not-allowed; }
.discuss-status { margin-top: 8px; font-size: 12px; color: var(--text-muted); text-align: center; }
.discuss-spinner { display: inline-block; animation: spin 1s linear infinite; }
.qa-btns { float: right; display: flex; gap: 4px; align-items: center; }
.qa-btns button { background: none; border: none; cursor: pointer; font-size: 12px; padding: 2px 4px; opacity: 0.4; transition: opacity 0.2s; color: var(--text-muted); }
.qa-btns button:hover { opacity: 1; }
.qa-btns .del-btn:hover { color: #e74c3c; }
.qa-a.collapsed { display: none; }
.qa-q { position: relative; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
'''

def _extract_arxiv_id_from_file(filepath):
    """Extract arxiv_id from YAML frontmatter of a markdown note."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        m = re.search(r'^---\s*\n.*?^arxiv_id:\s*(\S+)', content, re.MULTILINE | re.DOTALL)
        if m:
            return m.group(1)
        m = re.search(r'^---\s*\n.*?^arxiv:\s*(\S+)', content, re.MULTILINE | re.DOTALL)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def _load_discuss_record(stem):
    """Load discussion record JSON for a paper by its filename stem."""
    path = os.path.join(DISCUSS_DIR, f'{stem}.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _make_discuss_html(title, file_rel, arxiv_id, stem):
    """Generate the discussion assistant HTML block + JS."""
    record = _load_discuss_record(stem)

    # Build Q&A history HTML
    qa_html = ''
    qa_count = 0
    if record and isinstance(record, dict):
        qa_list = record.get('qa', [])
        qa_count = len(qa_list)
        if qa_count:
            items = ''
            for qa in qa_list:
                qid = qa.get('id', 0)
                q = str(qa.get('question', ''))
                a = str(qa.get('answer', ''))
                items += f'''<div class="qa-item" data-qa-id="{qid}">
                <div class="qa-q"><span class="qa-btns"><button class="del-btn" onclick="deleteQA({qid},'{stem}')" title="删除">🗑</button><button onclick="toggleQA(this)" title="收起">▲</button></span>Q: {q}</div>
                <div class="qa-a">{a}</div>
              </div>'''
            shown = 'open' if qa_count <= 3 else ''
            qa_html = f'''<details class="qa-history" {shown}>
        <summary class="qa-summary">📝 已有{qa_count}条讨论 (点击展开)</summary>
        <div class="qa-list">{items}</div>
      </details>'''

    js_title = title.replace("'", "\\'")
    js_rel = file_rel.replace("'", "\\'")

    return f'''<div class="discuss-section">
  <h2>💬 论文讨论助手</h2>
  <div class="discuss-container">
    {qa_html}
    <div class="discuss-input-area">
      <input type="text" id="discuss-input" placeholder="输入你的问题..." onkeydown="if(event.key==='Enter') sendQuestion()" />
      <button id="discuss-send" onclick="sendQuestion()">发送</button>
    </div>
    <div id="discuss-status" class="discuss-status"></div>
  </div>
</div>
<script>
const NTITLE = '{js_title}';
const FPATH = '{js_rel}';
const AID = '{arxiv_id}';
const STEM = '{stem}';

const discInput = document.getElementById('discuss-input');
const discSend = document.getElementById('discuss-send');
const discStatus = document.getElementById('discuss-status');

// Load discussion history from JSON on page load
async function loadHistory() {{
  try {{
    const r = await fetch('/讨论记录/' + STEM + '.json');
    if (!r.ok) return;
    const data = await r.json();
    if (!data || !data.qa) return;
    for (const qa of data.qa) {{
      appendMessage('user', qa.question, qa.id);
      appendMessage('assistant', qa.answer, qa.id);
    }}
  }} catch(e) {{
    // History file might not exist yet
  }}
}}
loadHistory();

function appendMessage(role, content, qaId) {{
  const container = document.querySelector('.discuss-container');
  if (!container) return;
  const div = document.createElement('div');
  div.className = 'qa-item qa-item-new';
  if (qaId) div.dataset.qaId = qaId;
  if (role === 'user') {{
    div.innerHTML = '<div class=\"qa-q\">Q: ' + escapeHtml(content) + '</div>';
  }} else {{
    div.innerHTML = '<div class=\"qa-q\"><span class=\"qa-btns\"><button class=\"del-btn\" onclick=\"deleteQA(' + qaId + ',STEM)\" title=\"删除\">🗑</button><button onclick=\"toggleQA(this)\" title=\"收起\">▲</button></span>A: ' + escapeHtml(content) + '</div>';
  }}
  const inputArea = document.querySelector('.discuss-input-area');
  if (inputArea) {{
    container.insertBefore(div, inputArea);
  }} else {{
    container.appendChild(div);
  }}
}}

function toggleQA(btn) {{
  const item = btn.closest('.qa-item');
  const answer = item ? item.querySelector('.qa-q, .qa-a') : null;
  if (!answer) return;
  if (answer.classList.contains('qa-a')) {{
    answer.classList.toggle('collapsed');
    btn.textContent = answer.classList.contains('collapsed') ? '▼' : '▲';
  }} else {{
    const allText = item.querySelector('.qa-q');
    if (allText) allText.classList.toggle('collapsed');
    btn.textContent = allText && allText.classList.contains('collapsed') ? '▼' : '▲';
  }}
}}

async function deleteQA(qaId, stem) {{
  if (!confirm('确定删除这条讨论？')) return;
  document.querySelectorAll('.qa-item').forEach(el => {{
    if (el.dataset.qaId == qaId) el.remove();
  }});
  try {{
    await fetch('/api/discuss/delete', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{paper_path: FPATH, qa_id: qaId}})
    }});
  }} catch(e) {{
    console.log('Delete API error (non-critical):', e);
  }}
}}

function escapeHtml(text) {{
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}}

function setLoading(loading) {{
  discInput.disabled = loading;
  discSend.disabled = loading;
  discSend.textContent = loading ? '思考中...' : '发送';
  discStatus.innerHTML = loading ? '<span class="discuss-spinner">⏳</span> AI 正在思考...' : '';
}}

async function sendQuestion() {{
  const q = discInput.value.trim();
  if (!q) return;
  discInput.value = '';
  appendMessage('user', q);
  setLoading(true);
  try {{
    const r = await fetch('/api/discuss', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        paper_path: FPATH,
        paper_title: NTITLE,
        arxiv_id: AID,
        question: q
      }})
    }});
    const d = await r.json();
    if (d.success) {{
      appendMessage('assistant', d.answer);
    }} else {{
      discStatus.innerHTML = '<span style="color:#e74c3c">❌ 错误: ' + escapeHtml(d.error || '未知错误') + '</span>';
    }}
  }} catch(e) {{
    discStatus.innerHTML = '<span style="color:#e74c3c">❌ 网络错误: ' + escapeHtml(e.message) + '</span>';
  }} finally {{
    setLoading(false);
  }}
}}
</script>'''


def generate_note_page(filepath, title, category, wikilink_map, backlink_map, all_podcasts):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    body = md_to_html(content, wikilink_map)
    toc = extract_toc(content)
    podcast_info = find_podcast(title, all_podcasts)
    player = ''
    if podcast_info:
        player = PLAYER_HTML.format(url=podcast_info[0])
    back_link = f'<a class="back" href="./">\u2190 {category}</a>' if category else ''
    bc = breadcrumb_html(category, title)
    tags = make_tags_html(filepath)
    backlinks = make_backlinks_html(title, backlink_map, wikilink_map)
    file_rel = os.path.relpath(filepath, VAULT_DIR)
    js_title = title.replace("'", "\\'")
    delete_btn = '<span style="float:right"><button onclick="deleteNote()" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:12px;padding:0">\U0001f5d1\ufe0f \u5220\u9664</button></span>'
    # Paper discussion assistant
    arxiv_id = _extract_arxiv_id_from_file(filepath)
    stem = os.path.splitext(os.path.basename(filepath))[0]
    discuss_html = _make_discuss_html(title, file_rel, arxiv_id, stem)
    del_script = (
        '<script>\n'
        + "const TOKEN='hermes-delete-token-2026';\n"
        + 'async function deleteNote() {\n'
        + "  if(!confirm('\\u786e\\u8ba4\\u5220\\u9664\\u300c'+NTITLE+'\\u300d\\uff1f')) return;\n"
        + "  if(!confirm('\\u26a0\\ufe0f \\u4e0d\\u53ef\\u6062\\u590d\\uff01\\u518d\\u6b21\\u786e\\u8ba4\\uff1f')) return;\n"
        + '  try {\n'
        + "    const r = await fetch('/api/delete', {\n"
        + "      method:'POST',\n"
        + "      headers:{'Content-Type':'application/x-www-form-urlencoded'},\n"
        + "      body:'path='+encodeURIComponent(FPATH)+'&token='+TOKEN\n"
        + '    });\n'
        + '    const d = await r.json();\n'
        + "    if(d.success) { alert('\\u2705 \\u5df2\\u5220\\u9664'); location.href='/'; }\n"
        + "    else alert('\\u274c \\u5220\\u9664\\u5931\\u8d25: '+d.message);\n"
        + '  } catch(e) { alert("\\u274c \\u7f51\\u7edc\\u9519\\u8bef: "+e.message); }\n'
        + '}\n'
        + '</script>'
    )
    page = common_head(title, _DISCUSS_INLINE_STYLES) + f'''</head>
<body>
<div class="container">
  <div class="header">
    {back_link}
    {bc}
    <h1>{title}</h1>
  </div>
  <div class="page-layout">
    <div class="page-content">
      {player}
      {toc}
      <div class="content">
{body}
      </div>
      {tags}
      {backlinks}
      <div class="footer">
        <a href="/">\u2190 \u8fd4\u56de\u9996\u9875</a>
        {delete_btn}
      </div>
    </div>
    <div class="discuss-panel">
      {discuss_html}
    </div>
  </div>
</div>
{del_script}
</body>
</html>'''
    return page

def generate_search_page(wikilink_map, all_podcasts):
    # Build search index
    search_index = []
    for entry in os.listdir(VAULT_DIR):
        if entry.startswith('.'): continue
        full = os.path.join(VAULT_DIR, entry)
        if os.path.isdir(full):
            for fname in os.listdir(full):
                if not fname.endswith('.md'): continue
                fpath = os.path.join(full, fname)
                content = open(fpath).read()
                title = fname[:-3]
                enc_entry = entry.replace(' ', '%20')
                enc_file = fname[:-3].replace(' ', '%20') + '.html'
                url = f'/{enc_entry}/{enc_file}'
                # Extract meaningful text (skip frontmatter, keep first 200 chars)
                body = re.sub(r'^---.*?---', '', content, flags=re.DOTALL).strip()[:200]
                tags = extract_tags(fpath)
                search_index.append({'title': title, 'url': url, 'cat': entry, 'tags': tags, 'snippet': body})
    index_json = json.dumps(search_index, ensure_ascii=False)
    extra_head = '''.search-box { margin-bottom: 20px; }
.search-box input { width: 100%; padding: 14px 20px; font-size: 16px; border: 2px solid var(--border); border-radius: 12px; background: var(--card-bg); color: var(--text); outline: none; }
.search-box input:focus { border-color: var(--link); }
.search-result { background: var(--card-bg); border-radius: 10px; padding: 16px 20px; margin-bottom: 10px; box-shadow: var(--card-shadow); }
.search-result h3 { font-size: 15px; margin-bottom: 4px; }
.search-result h3 a { color: var(--link); text-decoration: none; }
.search-result h3 a:hover { text-decoration: underline; }
.search-result .sr-cat { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
.search-result .sr-snippet { font-size: 13px; color: var(--text-secondary); }
.search-result .sr-tags { margin-top: 4px; }
.no-results { text-align: center; color: var(--text-muted); padding: 40px; }'''
    page = common_head('🔍 搜索', extra_head) + f'''</head>
<body>
<div class="container">
  <div class="header">
    <h1>🔍 搜索论文</h1>
  </div>
  <div class="search-box">
    <input type="text" id="q" placeholder="搜索论文标题、标签..." autofocus oninput="search()">
  </div>
  <div id="results" class="no-results">输入关键词开始搜索...</div>
</div>
<script>
const INDEX = {index_json};
function search() {{
  const q = document.getElementById('q').value.toLowerCase().trim();
  const results = document.getElementById('results');
  if (!q) {{ results.innerHTML = '<div class="no-results">输入关键词开始搜索...</div>'; return; }}
  const words = q.split(/\\s+/);
  const filtered = INDEX.filter(item => {{
    const text = (item.title + ' ' + item.cat + ' ' + item.tags.join(' ') + ' ' + item.snippet).toLowerCase();
    return words.every(w => text.includes(w));
  }}).slice(0, 30);
  if (!filtered.length) {{ results.innerHTML = '<div class="no-results">没有找到匹配的结果</div>'; return; }}
  results.innerHTML = filtered.map(item => `
    <div class="search-result">
      <div class="sr-cat">${{item.cat}}</div>
      <h3><a href="${{item.url}}">${{item.title}}</a></h3>
      <div class="sr-snippet">${{item.snippet}}</div>
      ${{item.tags.length ? '<div class="sr-tags">' + item.tags.map(t => `<span style="font-size:11px;color:var(--text-muted)">#${{t}}</span>`).join(' ') + '</div>' : ''}}
    </div>`).join('');
  document.getElementById('result-count').textContent = filtered.length + ' 个结果';
}}
</script>
<div class="footer">
  <a href="/">← 返回首页</a> · <a href="/搜索.html">搜索</a> · <a href="/图谱/">🕸️ 知识图谱</a>
</div>
</body>
</html>'''
    return page

# ── Tag pages ────────────────────────────────────────────────────
def generate_tag_pages(tag_index, wikilink_map):
    # Compact alphabetical tag grid
    tag_items = []
    for tag, notes in sorted(tag_index.items(), key=lambda x: x[0].lower()):
        count = len(notes)
        tag_items.append(f'<a class="tag-pill" href="/标签/{tag}.html">{tag} <span class="tag-count">{count}</span></a>\n')
    
    tag_cloud_html = '<div class="tag-grid">\n' + ''.join(tag_items) + '</div>\n'
    
    total = sum(len(v) for v in tag_index.values())
    tag_cloud_html += f'<div style="text-align:center;color:var(--text-muted);padding:10px;font-size:13px">{len(tag_index)} 个标签 · {total} 条关联</div>'
    
    tag_dir = os.path.join(os.path.dirname(VAULT_DIR), '标签')
    os.makedirs(tag_dir, exist_ok=True)
    
    tag_css = '''.tag-grid { display: flex; flex-wrap: wrap; gap: 6px; padding: 10px; justify-content: center; }
.tag-pill { display: inline-flex; align-items: center; gap: 4px; background: var(--tag-bg); color: var(--tag-text); padding: 5px 12px; border-radius: 20px; font-size: 12px; text-decoration: none; transition: transform 0.1s, opacity 0.1s; }
.tag-pill:hover { transform: scale(1.05); opacity: 0.9; }
.tag-count { display: inline-flex; align-items: center; justify-content: center; min-width: 18px; height: 18px; background: rgba(255,255,255,0.2); border-radius: 9px; font-size: 10px; padding: 0 5px; }'''
    
    tag_index_page = common_head('🏷️ 标签云', tag_css) + f'''</head>
<body>
<div class="container">
  <div class="header">
    <h1>🏷️ 标签检索</h1>
  </div>
  <div style="background:var(--card-bg);border-radius:12px;padding:20px;box-shadow:var(--card-shadow)">
{tag_cloud_html}
  </div>
  <div class="footer"><a href="/">← 返回首页</a></div>
</div>
</body>
</html>'''
    with open(os.path.join(tag_dir, 'index.html'), 'w') as f:
        f.write(tag_index_page)
    print(f"✅ 标签页: {len(tag_index)} 标签")
    
    for tag, notes in tag_index.items():
        items = ''
        for title, url, cat in notes:
            items += f'<li><a href="{url}">{title}</a> <span class="sr-cat" style="margin-left:8px;color:var(--text-muted);font-size:12px">{cat}</span></li>\n'
        page = common_head(f'#{tag}') + f'''</head>
<body>
<div class="container">
  <div class="header">
    <h1>🏷️ #{tag} <span style="font-size:14px;opacity:0.8">({len(notes)}篇)</span></h1>
  </div>
  <div style="background:var(--card-bg);border-radius:12px;padding:20px;box-shadow:var(--card-shadow)">
    <ul style="list-style:none;padding:0">{items}</ul>
  </div>
  <div class="footer"><a href="/标签/">← 所有标签</a> · <a href="/">← 首页</a></div>
</div>
</body>
</html>'''
        with open(os.path.join(tag_dir, f'{tag}.html'), 'w') as f:
            f.write(page)

# ── Main generator ───────────────────────────────────────────────
def generate():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    wikilink_map = build_wikilink_map()
    backlink_map = build_backlink_map()
    tag_index = build_tag_index()
    all_podcasts = load_podcasts()
    print(f"📋 索引: {len(wikilink_map)} 笔记 · {len(tag_index)} 标签 · {len(backlink_map)} 反向链接 · {len(all_podcasts)} 播客")
    
    # ── Scan vault ──
    categories = []
    standalone_files = []
    for entry in sorted(os.listdir(VAULT_DIR)):
        if entry.startswith('.') or entry == 'index.html' or entry == '图谱': continue
        full = os.path.join(VAULT_DIR, entry)
        mtime = os.path.getmtime(full)
        if os.path.isdir(full):
            count = len([f for f in os.listdir(full) if f.endswith('.md')])
            categories.append((entry, mtime, count))
        elif entry.endswith('.md'):
            standalone_files.append((entry, mtime, os.path.getsize(full)))
    categories.sort(key=lambda x: -x[1])
    standalone_files.sort(key=lambda x: -x[1])
    
    # ── Homepage ──
    analysis_cards = ''
    paper_cards = ''
    for name, mtime, count in categories:
        dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        encoded = name.replace(' ', '%20')
        card = f'''<div class="card"><a href="{encoded}/">
      <div class="name">{name} <span class="count">{count}篇</span></div>
      <div class="meta">{dt}</div>
    </a></div>\n'''
        if name == '分析笔记':
            analysis_cards += card
        else:
            paper_cards += card
    
    latest_items = []
    # Scan all individual .md files across all subdirectories, sorted by mtime
    all_notes = []
    for entry in sorted(os.listdir(VAULT_DIR)):
        if entry.startswith('.') or entry == 'index.html': continue
        full = os.path.join(VAULT_DIR, entry)
        if os.path.isdir(full):
            for fname in os.listdir(full):
                if not fname.endswith('.md'): continue
                fpath = os.path.join(full, fname)
                mtime = os.path.getmtime(fpath)
                title = fname[:-3]
                enc_entry = entry.replace(' ', '%20')
                enc_file = fname[:-3].replace(' ', '%20')
                url = f'/{enc_entry}/{enc_file}.html'
                all_notes.append((mtime, title, entry, url))
        elif entry.endswith('.md'):
            fpath = full
            mtime = os.path.getmtime(fpath)
            title = entry[:-3]
            url = f'/{title.replace(" ", "%20")}.html'
            all_notes.append((mtime, title, '', url))
    
    # Sort by mtime descending, take top 10
    all_notes.sort(key=lambda x: -x[0])
    for mtime, title, cat, url in all_notes[:10]:
        dt = datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M")
        cat_badge = f'<span class="cat-badge">{cat}</span>' if cat else ''
        latest_items.append(f'<li><a href="{url}">{title}</a> {cat_badge}<span class="meta">{dt}</span></li>')
    
    # Podcast section
    pod_items = ''
    for p in all_podcasts[:6]:
        dur = sec_to_display(p.get('duration', ''))
        pod_items += f'<li><a href="/podcast/">🎙️ {p["title"]}</a> <span class="meta">{dur}</span></li>\n'
    
    podcast_section = f'''<div class="latest">
  <h2>🎙️ 最新播客</h2>
  <ul>{pod_items}</ul>
</div>\n''' if pod_items else ''
    
    homepage_css_extra = '''.container { max-width: 960px; margin: 0 auto; padding: 20px; }
.header h1 { font-size: 24px; margin-bottom: 6px; }
.header p { opacity: 0.85; font-size: 14px; }
.latest { background: var(--card-bg); border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; box-shadow: var(--card-shadow); }
.latest h2 { font-size: 15px; color: var(--text-secondary); margin-bottom: 10px; }
.latest ul { list-style: none; }
.latest li { padding: 4px 0; }
.latest a { color: var(--link); text-decoration: none; font-size: 14px; }
.latest a:hover { text-decoration: underline; }
.latest .meta { color: var(--text-muted); font-size: 12px; margin-left: 8px; }
.latest .cat-badge { display: inline-block; background: var(--tag-bg); color: var(--tag-text); padding: 1px 8px; border-radius: 8px; font-size: 10px; margin: 0 6px; }
.section-title { font-size: 15px; font-weight: 600; color: var(--text-secondary); margin: 20px 0 10px; padding-bottom: 6px; border-bottom: 2px solid var(--link); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.card { background: var(--card-bg); border-radius: 10px; padding: 16px; box-shadow: var(--card-shadow); transition: transform 0.15s; }
.card:hover { transform: translateY(-2px); box-shadow: var(--card-hover-shadow); }
.card a { text-decoration: none; color: inherit; display: block; }
.card .name { font-size: 14px; font-weight: 600; color: var(--text); }
.card .count { display: inline-block; background: var(--tag-bg); color: var(--tag-text); padding: 1px 8px; border-radius: 10px; font-size: 11px; }
.card .meta { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.nav-links { text-align: center; padding: 10px; }
.nav-links a { color: var(--link); margin: 0 10px; }'''
    
    index_body = f'''<div class="latest">
  <h2>📌 最近更新</h2>
  <ul>{''.join(latest_items)}</ul>
</div>
{podcast_section}
<div class="section-title">📂 全部分类</div>
<div class="grid">{paper_cards}</div>
<div class="section-title" style="margin-top:30px">📝 分析笔记</div>
<div class="grid">{analysis_cards}</div>'''
    
    index_html = common_head('📚 论文知识库', homepage_css_extra) + f'''</head>
<body>
<div class="container">
  <div class="header">
    <h1>📚 论文知识库</h1>
    <p>更新于 {now} · 共 {len(categories)} 个分类 · {len(all_podcasts)} 期播客 · {len(tag_index)} 标签</p>
  </div>
  <div class="nav-links">
    <a href="/搜索.html">🔍 搜索</a>
    <a href="/标签/">🏷️ 标签</a>
    <a href="/podcast/">🎙️ 播客</a>
    <a href="/图谱/">🕸️ 知识图谱</a>
  </div>
  {index_body}
  <div class="footer">
    <a href="/旧站/">旧版 Quartz</a>
  </div>
</div>
</body>
</html>'''
    with open(os.path.join(VAULT_DIR, 'index.html'), 'w') as f:
        f.write(index_html)
    print(f"✅ 首页: {len(index_html)} bytes")
    
    # ── Podcast page ──
    # Build podcast→note map: for each podcast, find the best matching note
    podcast_note_map = {}
    # Collect all notes with their paths
    all_note_paths = []  # (title, category, url)
    for entry in sorted(os.listdir(VAULT_DIR)):
        if entry.startswith('.') or entry == 'index.html': continue
        full = os.path.join(VAULT_DIR, entry)
        if os.path.isdir(full):
            for fname in os.listdir(full):
                if not fname.endswith('.md'): continue
                title = fname[:-3]
                enc_entry = entry.replace(' ', '%20')
                enc_file = fname[:-3].replace(' ', '%20')
                url = f'/{enc_entry}/{enc_file}.html'
                all_note_paths.append((title, entry, url))
        elif entry.endswith('.md'):
            title = entry[:-3]
            url = f'/{title.replace(" ", "%20")}.html'
            all_note_paths.append((title, '', url))
    
    # For each podcast, find the note that best matches (by keyword overlapping)
    for pod in all_podcasts:
        pt_lower = pod['title'].lower().replace(' ', '').replace('—', '').replace(':', '')
        best_url = ''
        best_score = 0
        for note_title, cat, url in all_note_paths:
            nt_lower = note_title.lower().replace(' ', '').replace('—', '').replace(':', '')
            # Score: shared keyword overlap
            score = 0
            for map_key, note_keywords in PODCAST_MAP.items():
                if map_key in pt_lower:
                    for nk in note_keywords:
                        nk_l = nk.lower().replace(' ', '')
                        if nk_l in nt_lower or nt_lower in nk_l:
                            score += 1
            # Also check direct title overlap
            common = len(set(nt_lower.split()) & set(pt_lower.split()))
            score += common
            if score > best_score:
                best_score = score
                best_url = url
        if best_url:
            podcast_note_map[pod['title']] = best_url
        else:
            # No matching note found, link to homepage
            podcast_note_map[pod['title']] = '/'
    
    ep_html = ''
    for p in all_podcasts:
        dur = sec_to_display(p.get('duration', ''))
        note_url = podcast_note_map.get(p['title'], '')
        if note_url:
            ep_title = f'<a href="{note_url}" class="ep-link">🎙️ {p["title"]}</a>'
        else:
            ep_title = f'🎙️ {p["title"]}'
        ep_html += f'''  <div class="episode">
    <div class="ep-title">{ep_title}</div>
    <div class="ep-meta">⏱ {dur}</div>
    <audio controls style="width:100%">
      <source src="{p['url']}" type="audio/mpeg">
    </audio>
  </div>\n'''
    
    podcast_css = '''.container {{ max-width: 700px; }}
.episode {{ background: var(--card-bg); border-radius: 10px; padding: 16px 20px; margin-bottom: 12px; box-shadow: var(--card-shadow); }}
.ep-title {{ font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 4px; }}
.ep-link {{ color: var(--link); text-decoration: none; }}
.ep-link:hover {{ text-decoration: underline; }}
.ep-meta {{ font-size: 12px; color: var(--text-muted); margin-bottom: 8px; }}
.episode audio {{ width: 100%; height: 40px; }}'''
    
    podcast_html = common_head('🎙️ 播客', podcast_css) + f'''</head>
<body>
<div class="container">
  <div class="header">
    <a href="/" style="color:rgba(255,255,255,0.8);float:right;text-decoration:none;font-size:14px">← 知识库</a>
    <h1>🎙️ 论文播客</h1>
    <p style="opacity:0.85;font-size:14px">共 {len(all_podcasts)} 期</p>
  </div>
{ep_html}
  <div class="footer"><a href="/">← 返回首页</a></div>
</div>
</body>
</html>'''
    with open(os.path.join(os.path.dirname(PODCAST_FEED), 'index.html'), 'w') as f:
        f.write(podcast_html)
    print(f"✅ 播客页: {len(podcast_html)} bytes")
    
    # ── Search page ──
    search_html = generate_search_page(wikilink_map, all_podcasts)
    search_path = os.path.join(VAULT_DIR, '搜索.html')
    with open(search_path, 'w') as f:
        f.write(search_html)
    print(f"✅ 搜索页: {len(search_html)} bytes")
    
    # ── Tag pages ──
    generate_tag_pages(tag_index, wikilink_map)
    
    # ── Note pages (standalone files) ──
    for entry in sorted(os.listdir(VAULT_DIR)):
        if os.path.isdir(entry) or not entry.endswith('.md') or entry.startswith('.'): continue
        filepath = os.path.join(VAULT_DIR, entry)
        title = entry[:-3]
        html = generate_note_page(filepath, title, '', wikilink_map, backlink_map, all_podcasts)
        html_path = filepath.replace('.md', '.html')
        with open(html_path, 'w') as f:
            f.write(html)
        pi = find_podcast(title, all_podcasts)
        badge = " 🎙️" if pi else ""
        print(f"  {entry} → .html{badge}")
    
    # ── Subdirectories ──
    for entry in sorted(os.listdir(VAULT_DIR)):
        subdir = os.path.join(VAULT_DIR, entry)
        if not os.path.isdir(subdir) or entry.startswith('.'): continue
        
        subfiles = [f for f in sorted(os.listdir(subdir)) if f.endswith('.md')]
        
        # Subdir index
        sub_list, pod_count = '', 0
        for fname in subfiles:
            fpath = os.path.join(subdir, fname)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
            size = os.path.getsize(fpath)
            size_s = f"{size/1024:.0f}KB" if size > 1024 else f"{size}B"
            stem = fname[:-3]
            pi = find_podcast(stem, all_podcasts)
            badge = PODCAST_BADGE if pi else ''
            if pi: pod_count += 1
            sub_list += f'''<li><a href="{stem.replace(" ", "%20")}.html">
      <span class="name">{stem}{badge}</span>
      <span class="meta">{mtime} · {size_s}</span>
    </a></li>\n'''
        
        sub_css = '''.container {{ max-width: 800px; }}
.podcast-badge {{ display: inline-block; background: var(--badge-bg); color: var(--badge-text); padding: 1px 8px; border-radius: 8px; font-size: 11px; margin-left: 6px; }}
.file-list {{ background: var(--card-bg); border-radius: 12px; padding: 10px 0; box-shadow: var(--card-shadow); }}
.file-list li {{ list-style: none; }}
.file-list a {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 20px; text-decoration: none; border-bottom: 1px solid var(--border); }}
.file-list li:last-child a {{ border-bottom: none; }}
.file-list a:hover {{ background: var(--backlink-bg); }}
.file-list .name {{ color: var(--text); font-size: 14px; }}
.file-list .meta {{ color: var(--text-muted); font-size: 12px; white-space: nowrap; }}
.pod-count {{ font-size: 13px; opacity: 0.85; margin-top: 4px; }}'''
        
        sub_html = common_head(f'📁 {entry}', sub_css) + f'''</head>
<body>
<div class="container">
  <div class="header">
    <a class="back" href="/">← 返回首页</a>
    {breadcrumb_html(entry, '')}
    <h1>📁 {entry}</h1>
    <div class="pod-count">{f'🎙️ {pod_count} 篇有播客' if pod_count else ''}</div>
  </div>
  <ul class="file-list">{sub_list}</ul>
  <div class="footer"><a href="/">← 返回首页</a></div>
</div>
</body>
</html>'''
        with open(os.path.join(subdir, 'index.html'), 'w') as f:
            f.write(sub_html)
        print(f"  {entry}/index.html (🎙️{pod_count})")
        
        # Individual notes in subdirectory
        for fname in subfiles:
            fpath = os.path.join(subdir, fname)
            title = fname[:-3]
            html = generate_note_page(fpath, title, entry, wikilink_map, backlink_map, all_podcasts)
            html_path = fpath.replace('.md', '.html')
            with open(html_path, 'w') as f:
                f.write(html)
        # Just count
        print(f"  {entry}/ {len(subfiles)} notes generated")

if __name__ == '__main__':
    generate()
