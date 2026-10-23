#!/opt/hermes/.venv/bin/python3
"""
播客发布工具 — 上传音频 → 生成RSS Feed → 可选同步NAS存档

用法:
  # 发布新集数
  ./publish_podcast.py --title "第X期：xxx" --audio /tmp/episode.mp3

  # 发布并指定描述/时长
  ./publish_podcast.py --title "..." --audio ... \\
    --desc "本期我们聊了..." --duration 1800

  # 仅重建RSS（已有音频文件）
  ./publish_podcast.py --rebuild


选项:
  --title      单集标题
  --audio      音频文件路径 (mp3/wav)
  --desc       单集描述 (可选)
  --duration   音频时长(秒) (可选, 自动从文件读取)
  --rebuild    仅根据已有音频重建 feed.xml
  --sync-nas   同步音频到 NAS 存档
  --base-url   站点基础URL (默认: https://obsidian.wenwen.homes:16666)
  --podcast-dir 播客目录 (默认: /opt/hermes/quartz-site/public/podcast)
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.dom.minidom
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

# ── 配置 ────────────────────────────────────────────────
BASE_URL = "https://raw.githubusercontent.com/lulu93/hermes-podcast/main"
# 注意: 文件在GitHub仓库的根目录，所以 audio/ 就是 {BASE_URL}/audio/ 而不是 {BASE_URL}/podcast/audio/
PODCAST_DIR = Path("/opt/hermes/podcast-feed")
AUDIO_DIR = PODCAST_DIR / "audio"
FEED_PATH = PODCAST_DIR / "feed.xml"
FEED_STATE = PODCAST_DIR / ".feed_state.json"  # 追踪已发布的文件

# 播客元信息
PODCAST_TITLE = "Hermes 3D论文播客"
PODCAST_DESC = (
    "Hermes Agent 自动生成的 AI 与 3D 视觉论文播客。"
    "深入解读最新 3D 重建、NeRF、3DGS 等前沿论文。"
)
PODCAST_AUTHOR = "Hermes AI"
PODCAST_EMAIL = ""
PODCAST_IMAGE_URL = f"{BASE_URL}/cover.jpg"
PODCAST_LANG = "zh-CN"
PODCAST_CATEGORY = "Technology"

# ════════════════════════════════════════════════════════


def get_audio_duration(path: str) -> int:
    """用 ffprobe 读取音频时长(秒)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(float(result.stdout.strip()))
    except Exception:
        pass
    return 0


def get_file_size(path: str) -> int:
    return os.path.getsize(path)


def get_file_hash(path: str) -> str:
    """快速计算文件哈希（前1MB+后1MB）用于去重."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        data = f.read(1024 * 1024)
        h.update(data)
        f.seek(-min(os.path.getsize(path), 1024 * 1024), 2)
        data = f.read(1024 * 1024)
        h.update(data)
    return h.hexdigest()


def load_state() -> dict:
    if FEED_STATE.exists():
        with open(FEED_STATE) as f:
            return json.load(f)
    return {"episodes": []}


def save_state(state: dict):
    FEED_STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(FEED_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def cst_now() -> datetime:
    """返回当前北京时间 (CST, UTC+8)"""
    return datetime.now(timezone(timedelta(hours=8)))


def rfc2822_date(dt: datetime = None) -> str:
    """格式化为 RFC 2822 时间字符串 (RSS标准)"""
    if dt is None:
        dt = cst_now()
    # RSS要求星期几缩写
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{weekdays[dt.weekday()]}, {dt.day:02d} {months[dt.month-1]} {dt.year:04d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} +0800"


def scan_existing_audio() -> list[dict]:
    """扫描 audio 目录中已有的音频文件，返回元信息列表."""
    state = load_state()
    state_episodes = {ep["filename"]: ep for ep in state.get("episodes", [])}

    episodes = []
    for f in sorted(AUDIO_DIR.iterdir()):
        if f.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
            size = f.stat().st_size
            url = f"{BASE_URL}/audio/{f.name}"
            mime = "audio/mpeg" if f.suffix.lower() == ".mp3" else "audio/wav"

            # 如果 state 中有这个文件的元信息，优先使用
            if f.name in state_episodes:
                ep = dict(state_episodes[f.name])
                ep["url"] = url
                ep["size"] = size
                episodes.append(ep)
            else:
                # 无 state 时，生成合理的默认值
                duration = get_audio_duration(str(f))
                title_hint = f.stem.replace(f.stem.split("_")[0], "").lstrip("_-").replace("-", " ") if "_" in f.stem else f.stem
                episodes.append({
                    "filename": f.name,
                    "title": title_hint if title_hint else f.stem,
                    "desc": "",
                    "url": url,
                    "size": size,
                    "mime": mime,
                    "duration": duration,
                    "pubDate": rfc2822_date(),
                    "guid": f.stem,
                })
    return episodes


def build_feed(episodes: list[dict]) -> str:
    """构建完整播客 RSS Feed XML."""
    now_str = rfc2822_date()

    rss = ET.Element("rss", version="2.0",
                     attrib={"xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
                             "xmlns:content": "http://purl.org/rss/1.0/modules/content/"})
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = PODCAST_TITLE
    ET.SubElement(channel, "link").text = BASE_URL
    ET.SubElement(channel, "description").text = PODCAST_DESC
    ET.SubElement(channel, "language").text = PODCAST_LANG
    ET.SubElement(channel, "lastBuildDate").text = now_str
    ET.SubElement(channel, "pubDate").text = now_str

    itunes = ET.SubElement(channel, "itunes:author")
    itunes.text = PODCAST_AUTHOR

    itunes_summary = ET.SubElement(channel, "itunes:summary")
    itunes_summary.text = PODCAST_DESC

    cat = ET.SubElement(channel, "itunes:category",
                        attrib={"text": PODCAST_CATEGORY})

    explicit = ET.SubElement(channel, "itunes:explicit")
    explicit.text = "false"

    if PODCAST_IMAGE_URL:
        image = ET.SubElement(channel, "itunes:image",
                              attrib={"href": PODCAST_IMAGE_URL})

    # 标准 RSS image (必须)
    std_image = ET.SubElement(channel, "image")
    url_el = ET.SubElement(std_image, "url")
    url_el.text = PODCAST_IMAGE_URL
    title_el2 = ET.SubElement(std_image, "title")
    title_el2.text = PODCAST_TITLE
    link_el = ET.SubElement(std_image, "link")
    link_el.text = BASE_URL

    # 逐一添加 episodes
    for ep in episodes:
        item = ET.SubElement(channel, "item")

        title_el = ET.SubElement(item, "title")
        title_el.text = ep.get("title", ep["filename"])

        desc_el = ET.SubElement(item, "description")
        desc_el.text = escape(ep.get("desc", ""))

        pub_el = ET.SubElement(item, "pubDate")
        pub_el.text = ep.get("pubDate", now_str)

        guid = ET.SubElement(item, "guid",
                             attrib={"isPermaLink": "false"})
        guid.text = ep.get("guid", ep["filename"])

        enclosure = ET.SubElement(item, "enclosure",
                                  attrib={
                                      "url": ep["url"],
                                      "length": str(ep.get("size", 0)),
                                      "type": ep.get("mime", "audio/mpeg"),
                                  })

        ep_explicit = ET.SubElement(item, "itunes:explicit")
        ep_explicit.text = "false"

        if ep.get("duration"):
            dur = ET.SubElement(item, "itunes:duration")
            dur.text = str(ep["duration"])

    # 格式化输出
    rough = ET.tostring(rss, encoding="unicode")
    dom = xml.dom.minidom.parseString(rough)
    return dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def publish_episode(title: str, audio_path: str, desc: str = "",
                    duration: int = 0):
    """完整发布流程：复制音频 → 更新RSS → 可选同步NAS."""
    audio_path = os.path.abspath(audio_path)
    if not os.path.exists(audio_path):
        print(f"❌ 音频文件不存在: {audio_path}")
        return False

    # 1. 获取文件元信息
    ext = Path(audio_path).suffix
    file_hash = get_file_hash(audio_path)

    # 生成文件名: 日期-标题.wav/mp3
    today = cst_now().strftime("%Y%m%d")
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()[:50]
    safe_title = safe_title.replace(" ", "-").replace("_", "-")
    safe_title = "-".join(filter(None, safe_title.split("-")))  # 去重连续的-
    filename = f"{today}_{safe_title}{ext}"
    dest = AUDIO_DIR / filename

    # 2. 检查是否已发布（去重）
    state = load_state()
    for ep in state.get("episodes", []):
        if ep.get("hash") == file_hash:
            # 可能只是文件名变了，检查
            existing_dest = AUDIO_DIR / ep["filename"]
            if existing_dest.exists():
                print(f"⏭️  该音频已发布 (标题: {ep.get('title')})，跳过")
                return True

    # 3. 复制音频文件
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio_path, dest)
    file_size = get_file_size(dest)
    print(f"✅ 音频已复制: {dest.name} ({file_size/1024/1024:.1f}MB)")

    # 4. 获取时长
    if duration <= 0:
        duration = get_audio_duration(dest)
    dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else ""

    # 5. 更新 RSS
    mime = "audio/mpeg" if ext.lower() in (".mp3",) else "audio/wav"
    episode_url = f"{BASE_URL}/audio/{filename}"
    now_str = rfc2822_date()
    guid = f"{today}-{file_hash[:8]}"

    new_ep = {
        "filename": filename,
        "title": title,
        "desc": desc,
        "url": episode_url,
        "size": file_size,
        "mime": mime,
        "duration": duration,
        "pubDate": now_str,
        "guid": guid,
        "hash": file_hash,
    }

    state["episodes"].insert(0, new_ep)  # 最新在最前
    save_state(state)

    # 从 state + audio 目录扫描重建 feed
    all_episodes = []
    for ep in state["episodes"]:
        audio_file = AUDIO_DIR / ep["filename"]
        if audio_file.exists():
            # 更新文件大小（可能压缩过）
            current_size = audio_file.stat().st_size
            ep["size"] = current_size
            ep["url"] = f"{BASE_URL}/audio/{ep['filename']}"
            all_episodes.append(ep)

    feed_xml = build_feed(all_episodes)
    with open(FEED_PATH, "w", encoding="utf-8") as f:
        f.write(feed_xml)

    print(f"✅ RSS Feed 已更新: {FEED_PATH}")
    print(f"   📡 Feed URL: https://raw.githubusercontent.com/lulu93/hermes-podcast/main/feed.xml")
    if dur_str:
        print(f"   ⏱  时长: {dur_str}")


    # 7. 同步 GitHub
    git_push(f"Add: {title}")
    print(f"   📡 Feed URL: https://raw.githubusercontent.com/lulu93/hermes-podcast/main/feed.xml")

    return True


def git_push(commit_msg: str = ""):
    """将 podcast-feed 目录的变更提交并推送到 GitHub."""
    repo_dir = "/opt/hermes/podcast-feed"
    try:
        # 检查是否 git 仓库
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            # 初始化 git
            subprocess.run(["git", "init"], cwd=repo_dir,
                           capture_output=True, timeout=15)
            subprocess.run(["git", "branch", "-M", "main"], cwd=repo_dir,
                           capture_output=True, timeout=15)
            # 添加 remote（从 .env 读 token）
            token = os.environ.get("GITHUB_TOKEN", "")
            if not token:
                env_path = "/opt/data/profiles/wechat-2/.env"
                if os.path.exists(env_path):
                    with open(env_path) as f:
                        for line in f:
                            if line.startswith("GITHUB_TOKEN="):
                                token = line.strip().split("=", 1)[1]
                                break
            if token:
                remote_url = f"https://lulu93:{token}@github.com/lulu93/hermes-podcast.git"
                subprocess.run(["git", "remote", "add", "origin", remote_url],
                               cwd=repo_dir, capture_output=True, timeout=15)

        # 检查 remote 是否存在
        result = subprocess.run(["git", "remote", "-v"], cwd=repo_dir,
                                capture_output=True, text=True, timeout=10)
        if "origin" not in result.stdout:
            print("⚠️  未配置 GitHub remote，跳过 push")
            return

        # 添加所有变更
        subprocess.run(["git", "add", "-A"], cwd=repo_dir,
                       capture_output=True, timeout=15)

        # 检查是否有变更
        status = subprocess.run(["git", "status", "--porcelain"], cwd=repo_dir,
                                capture_output=True, text=True, timeout=10)
        if not status.stdout.strip():
            print("   ℹ️  无变更，跳过 push")
            return

        if not commit_msg:
            commit_msg = f"Update podcast feed ({cst_now().strftime('%Y-%m-%d %H:%M')})"

        subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_dir,
                       capture_output=True, timeout=15)
        push = subprocess.run(["git", "push", "-u", "origin", "main"],
                              cwd=repo_dir, capture_output=True, text=True, timeout=60)
        if push.returncode == 0:
            print(f"✅ GitHub 同步完成")
        else:
            print(f"⚠️  GitHub push 失败: {push.stderr[:200]}")
    except Exception as e:
        print(f"⚠️  Git push 异常: {e}")


def rebuild_feed():
    """仅根据 audio 目录和 state 重建 feed.xml."""
    state = load_state()
    episodes = []
    for ep in state.get("episodes", []):
        audio_file = AUDIO_DIR / ep["filename"]
        if audio_file.exists():
            current_size = audio_file.stat().st_size
            ep["size"] = current_size
            ep["url"] = f"{BASE_URL}/audio/{ep['filename']}"
            episodes.append(ep)
        else:
            print(f"⚠️  音频文件已丢失: {ep['filename']}")

    if not episodes:
        # 如果 state 为空，扫描 audio 目录
        scanned = scan_existing_audio()
        for s in scanned:
            episodes.append({
                "filename": s["filename"],
                "title": s["filename"],
                "desc": "",
                "url": s["url"],
                "size": s["size"],
                "mime": s["mime"],
                "duration": 0,
                "pubDate": rfc2822_date(),
                "guid": s["filename"],
            })

    feed_xml = build_feed(episodes)
    with open(FEED_PATH, "w", encoding="utf-8") as f:
        f.write(feed_xml)
    print(f"✅ RSS Feed 已重建: {FEED_PATH}")
    print(f"   📡 Feed URL: https://raw.githubusercontent.com/lulu93/hermes-podcast/main/feed.xml")
    if episodes:
        print(f"   📊 共 {len(episodes)} 集")

    # 同步 GitHub
    git_push("Rebuild feed")


def main():
    parser = argparse.ArgumentParser(description="播客发布工具")
    parser.add_argument("--title", help="单集标题")
    parser.add_argument("--audio", help="音频文件路径")
    parser.add_argument("--desc", default="", help="单集描述")
    parser.add_argument("--duration", type=int, default=0, help="音频时长(秒)")
    parser.add_argument("--rebuild", action="store_true", help="仅重建 feed.xml")

    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--podcast-dir", default=str(PODCAST_DIR))

    args = parser.parse_args()

    # 覆盖全局配置（如有指定）
    effective_base_url = args.base_url or BASE_URL
    effective_podcast_dir = Path(args.podcast_dir) if args.podcast_dir else PODCAST_DIR
    effective_audio_dir = effective_podcast_dir / "audio"
    effective_feed_path = effective_podcast_dir / "feed.xml"
    effective_feed_state = effective_podcast_dir / ".feed_state.json"

    if args.rebuild:
        rebuild_feed()
        return

    if not args.title or not args.audio:
        parser.print_help()
        print("\n❌ 必须指定 --title 和 --audio")
        sys.exit(1)

    success = publish_episode(
        title=args.title,
        audio_path=args.audio,
        desc=args.desc,
        duration=args.duration,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
