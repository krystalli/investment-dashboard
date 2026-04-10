#!/usr/bin/env python3
"""
豬探長推理故事集 - 下載、合併上下集、去除廣告
用法: python3 podcast_download.py
"""

import os
import re
import json
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict

RSS_URL = "https://feed.firstory.me/rss/user/cklw2tvilfnda0804tdm3oxho"
OUTPUT_DIR = Path("豬探長")
TEMP_DIR = OUTPUT_DIR / "temp"

def fetch_rss():
    """取得 RSS feed"""
    print("📡 取得 RSS feed...")
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        return resp.read()

def parse_episodes(rss_data):
    """解析所有 EP 集數，回傳 {ep_num: [(title, url, part), ...]}"""
    root = ET.fromstring(rss_data)
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    
    episodes = defaultdict(list)
    
    for item in root.findall(".//item"):
        title_el = item.find("title")
        enclosure = item.find("enclosure")
        
        if title_el is None or enclosure is None:
            continue
        
        title = title_el.text.strip()
        url = enclosure.get("url", "")
        
        # 只處理 EP.XXX 格式，跳過 SP
        ep_match = re.match(r"EP\.(\.d+)\s+(.+?)\((上集|下集)\)", title)
        if ep_match:
            ep_num = int(ep_match.group(1))
            story_name = ep_match.group(2).strip()
            part = ep_match.group(3)
            episodes[ep_num].append({
                "title": title,
                "story": story_name,
                "url": url,
                "part": part
            })
        else:
            # 單集 EP（沒有上下集）
            single_match = re.match(r"EP\.(\d+)\s+(.+)", title)
            if single_match:
                ep_num = int(single_match.group(1))
                story_name = single_match.group(2).strip()
                episodes[ep_num].append({
                    "title": title,
                    "story": story_name,
                    "url": url,
                    "part": "單集"
                })
    
    return episodes

def download_episode(url, filepath):
    """下載單集音檔"""
    if filepath.exists():
        print(f"  ⏭️  已存在，跳過: {filepath.name}")
        return True
    
    print(f"  ⬇️  下載中: {filepath.name}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
        filepath.write_bytes(data)
        print(f"  ✅ 下載完成: {filepath.name} ({len(data)/1024/1024:.1f} MB)")
        return True
    except Exception as e:
        print(f"  ❌ 下載失敗: {e}")
        return False

def remove_ads(input_path, output_path):
    """用 ffmpeg 偵測並去除廣告（靜音段分割 + 去頭去尾廣告）"""
    # 策略：去除開頭30秒後的第一段靜音前（片頭廣告）和結尾廣告
    # 用 silencedetect 找出靜音點
    cmd = [
        "ffmpeg", "-i", str(input_path),
        "-af", "silencedetect=noise=-35dB:d=1.5",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr
    
    # 解析靜音時間點
    silence_starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", stderr)]
    silence_ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", stderr)]
    
    if not silence_starts:
        # 找不到靜音段，直接複製
        subprocess.run(["ffmpeg", "-i", str(input_path), "-c", "copy", str(output_path), "-y"],
                      capture_output=True)
        return
    
    # 取得總時長
    duration_match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", stderr)
    if duration_match:
        h, m, s = duration_match.groups()
        total_duration = int(h)*3600 + int(m)*60 + float(s)
    else:
        total_duration = None
    
    # 找故事開始點（跳過片頭廣告）
    # 通常片頭廣告在前60秒內，找第一個靜音結束點
    story_start = 0
    for i, end in enumerate(silence_ends):
        if end > 10:  # 至少10秒後的靜音結束
            story_start = end
            break
    
    # 找故事結束點（去除片尾廣告）
    story_end = total_duration
    if total_duration and silence_starts:
        # 找最後一段靜音前的時間（去掉最後的廣告）
        for start in reversed(silence_starts):
            if total_duration - start > 30:  # 片尾廣告通常超過30秒
                story_end = start
                break
    
    # 用 ffmpeg 截取故事段落
    cmd = ["ffmpeg", "-i", str(input_path),
           "-ss", str(story_start)]
    
    if story_end and story_end < (total_duration or float('inf')):
        cmd += ["-to", str(story_end)]
    
    cmd += ["-c", "copy", str(output_path), "-y"]
    subprocess.run(cmd, capture_output=True)

def merge_episodes(upper_path, lower_path, output_path):
    """合併上下集"""
    # 建立 concat 清單
    concat_file = TEMP_DIR / "concat.txt"
    concat_file.write_text(
        f"file '{upper_path.absolute()}'\nfile '{lower_path.absolute()}'\n"
    )
    
    cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output_path),
        "-y"
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0

def process_all():
    """主流程"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(exist_ok=True)
    
    # 取得 RSS
    try:
        rss_data = fetch_rss()
    except Exception as e:
        print(f"❌ 無法取得 RSS: {e}")
        print("嘗試備用 RSS URL...")
        # 備用：從 Apple Podcast ID 取得
        backup_url = "https://feeds.firstory.me/rss/user/detectivepig"
        try:
            req = urllib.request.Request(backup_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                rss_data = resp.read()
        except:
            print("❌ 備用 RSS 也失敗，請確認網路連線")
            return
    
    # 解析集數
    episodes = parse_episodes(rss_data)
    
    if not episodes:
        print("❌ 找不到任何 EP.XXX(上集/下集) 格式的集數")
        print("請檢查 RSS 格式是否符合預期")
        return
    
    print(f"✅ 找到 {len(episodes)} 個故事（{sum(len(v) for v in episodes.values())} 集）\n")
    
    # 依 EP 編號排序處理
    for ep_num in sorted(episodes.keys()):
        parts = episodes[ep_num]
        
        # 找上下集
        upper = next((p for p in parts if p["part"] == "上集"), None)
        lower = next((p for p in parts if p["part"] == "下集"), None)
        single = next((p for p in parts if p["part"] == "單集"), None)

        story_name = (upper or single or lower)["story"]  # fix: include lower as fallback
        output_filename = f"EP{ep_num:03d}_{story_name}.mp3"
        output_path = OUTPUT_DIR / output_filename

        if output_path.exists():
            print(f"⏭️  EP.{ep_num} 已完成，跳過: {output_filename}")
            continue

        print(f"\n🎙️  處理 EP.{ep_num} - {story_name}")

        if single:
            # 單集處理
            raw = TEMP_DIR / f"EP{ep_num:03d}_raw.mp3"
            if not download_episode(single["url"], raw):
                continue
            print(f"  ✂️  去除廣告...")
            remove_ads(raw, output_path)
            print(f"  ✅ 完成: {output_filename}")
            raw.unlink(missing_ok=True)

        elif upper and lower:
            # 上下集處理
            upper_raw = TEMP_DIR / f"EP{ep_num:03d}_upper_raw.mp3"
            lower_raw = TEMP_DIR / f"EP{ep_num:03d}_lower_raw.mp3"

            if not download_episode(upper["url"], upper_raw):
                continue
            if not download_episode(lower["url"], lower_raw):
                continue

            print(f"  ✂️  去除廣告...")
            upper_clean = TEMP_DIR / f"EP{ep_num:03d}_upper_clean.mp3"
            lower_clean = TEMP_DIR / f"EP{ep_num:03d}_lower_clean.mp3"
            remove_ads(upper_raw, upper_clean)
            remove_ads(lower_raw, lower_clean)

            print(f"  🔗 合併上下集...")
            if merge_episodes(upper_clean, lower_clean, output_path):
                print(f"  ✅ 完成: {output_filename}")
                for f in [upper_raw, lower_raw, upper_clean, lower_clean]:
                    f.unlink(missing_ok=True)
            else:
                print(f"  ❌ 合併失敗: EP.{ep_num}")

        else:
            print(f"⚠️  EP.{ep_num} 缺少上集或下集，跳過")
    
    print(f"\n🎉 全部完成！檔案儲存在: {OUTPUT_DIR.absolute()}")

if __name__ == "__main__":
    process_all()
