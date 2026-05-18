#!/usr/bin/env python3
"""
notebooklm_podcast.py — 将最新论文笔记提交到NotebookLM生成Deep Dive Audio

用法：
    # 生成最新笔记的播客
    python notebooklm_podcast.py

    # 指定某篇笔记
    python notebooklm_podcast.py --note "/path/to/note.md"
    
    # 读取notes_list.txt（每行一个路径），为每个笔记生成播客（并行的）
    python notebooklm_podcast.py --batch /tmp/new_notes.txt

说明：
    - 只提交生成任务，不等待完成，不下载音频文件
    - 如果某篇笔记已存在同名Notebook，跳过
    - 日志输出到 stderr，最终打印 notebook_id:note_path 映射到 stdout
"""

import asyncio
import argparse
import sys
import os
import glob
import re

from notebooklm import NotebookLMClient, AudioLength
from notebooklm.auth import AuthTokens


def find_latest_note():
    """找到最新修改的论文笔记"""
    notes_dir = "/opt/data/obsidian-vault/论文笔记"
    pattern = os.path.join(notes_dir, "**/*.md")
    files = glob.glob(pattern, recursive=True)
    if not files:
        print("❌ 未找到任何笔记", file=sys.stderr)
        return None
    latest = max(files, key=os.path.getmtime)
    return latest


def read_notes_list(path):
    """读取笔记列表文件，返回路径列表"""
    notes = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and os.path.isfile(line):
                notes.append(line)
    return notes


def note_title_from_path(path):
    """从文件名提取标题，去掉前缀编号和后缀.md"""
    basename = os.path.splitext(os.path.basename(path))[0]
    # 去掉前面的日期/编号前缀如 "2025-05-14 " 或 "01 "
    title = re.sub(r'^[\d\-\.\s]+', '', basename)
    return title


async def generate_podcast_for_note(note_path):
    """为单篇笔记创建Notebook并提交Deep Dive Audio
    
    返回: (notebook_id, note_path) 或 None
    """
    if not os.path.isfile(note_path):
        print(f"❌ 笔记不存在: {note_path}", file=sys.stderr)
        return None

    with open(note_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    title = note_title_from_path(note_path)
    print(f"📄 笔记: {title} ({len(content)} 字符)", file=sys.stderr)

    auth = await AuthTokens.from_storage()
    async with NotebookLMClient(auth) as client:
        # 检查同名Notebook是否已存在
        existing = await client.notebooks.list()
        for nb in existing:
            if nb.title == title:
                print(f"⚠️ Notebook已存在，跳过: {title}", file=sys.stderr)
                # 仍然检查是否有音频在生成或已完成
                audios = await client.artifacts.list_audio(nb.id)
                has_audio = any(a.is_completed or a.is_processing or a.is_pending for a in audios)
                if has_audio:
                    print(f"  已有音频（完成/进行中），跳过", file=sys.stderr)
                    return None
                # 没有音频，复用Notebook，只添加source
                source = await client.sources.add_text(
                    nb.id, title, content, wait=True, wait_timeout=60
                )
                print(f"  Source已添加: {source.title}", file=sys.stderr)
                nb_id = nb.id
                break
        else:
            # 创建新Notebook
            nb = await client.notebooks.create(title)
            nb_id = nb.id
            print(f"✅ Notebook: {title} (ID: {nb_id})", file=sys.stderr)
            
            source = await client.sources.add_text(
                nb_id, title, content, wait=True, wait_timeout=60
            )
            print(f"  Source: {source.title}", file=sys.stderr)

        # 提交Deep Dive Audio生成
        gen_status = await client.artifacts.generate_audio(
            nb_id,
            source_ids=[source.id],
            audio_length=AudioLength.SHORT,
            language='zh-CN',
        )
        print(f"🎯 已提交Deep Dive Audio: {gen_status}", file=sys.stderr)
        return (nb_id, note_path)


async def main():
    parser = argparse.ArgumentParser(description="生成NotebookLM语音播客")
    parser.add_argument("--note", help="指定笔记路径")
    parser.add_argument("--batch", help="从文件读取多个笔记路径（每行一个）")
    args = parser.parse_args()

    if args.batch:
        notes = read_notes_list(args.batch)
        if not notes:
            print("❌ 笔记列表为空", file=sys.stderr)
            sys.exit(1)
        print(f"📚 批量处理 {len(notes)} 篇笔记", file=sys.stderr)
        
        # 并行提交
        tasks = [generate_podcast_for_note(n) for n in notes]
        results = await asyncio.gather(*tasks)
        
        # 只输出已提交的结果
        for r in results:
            if r:
                print(f"{r[0]}:{r[1]}")  # notebook_id:note_path

    elif args.note:
        result = await generate_podcast_for_note(args.note)
        if result:
            print(f"{result[0]}:{result[1]}")
    
    else:
        # 找最新笔记
        note = find_latest_note()
        if note:
            print(f"📌 最新笔记: {note}", file=sys.stderr)
            result = await generate_podcast_for_note(note)
            if result:
                print(f"{result[0]}:{result[1]}")
        else:
            print("❌ 未找到笔记", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
