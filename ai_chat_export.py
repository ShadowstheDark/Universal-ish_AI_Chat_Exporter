#!/usr/bin/env python3
"""
================================================================================
Universal AI Chat Exporter & Formatter
Supports: Microsoft Copilot, ChatGPT, and Claude
================================================================================
Converts raw, messy JSON exports into clean, human-readable .txt and .md files.

Supported Inputs:
  - Microsoft Copilot JSON exports (via Substrate API or browser dump)
  - ChatGPT 'conversations.json' (Official OpenAI export or browser dump)
  - Claude 'conversations.json' (Official Anthropic export or browser dump)
  - VS Code GitHub Copilot local chat session files

Features:
  - Zero External Dependencies: Runs on pure standard Python 3.8+
  - Auto-detection of file format (Copilot vs ChatGPT vs Claude)
  - Reconstructs branched conversation trees (ChatGPT mapping -> linear thread)
  - Clean formatting with timestamps, clear speaker tags, code blocks & sources
  - Option to output a single consolidated archive or split into individual chat files
  - Includes browser 1-click console scripts to bypass corporate/rate restrictions

Usage:
  python ai_chat_export.py <path_to_json_file>
  python ai_chat_export.py file1.json file2.json (Merges multiple parts)
  python ai_chat_export.py --split <path_to_json_file>
  python ai_chat_export.py --chatgpt
  python ai_chat_export.py --claude
  python ai_chat_export.py --copilot
================================================================================
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
import subprocess

# Ensure UTF-8 output on Windows consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def copy_to_clipboard(text: str) -> bool:
    """Copies text to the system clipboard on Windows, macOS, or Linux."""
    try:
        if sys.platform == "win32":
            p = subprocess.Popen("clip", stdin=subprocess.PIPE, shell=True)
            p.communicate(text.encode("utf-8"))
            return True
        elif sys.platform == "darwin":
            p = subprocess.Popen("pbcopy", stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            return True
        else:
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            return True
    except Exception:
        return False


def load_browser_script(script_filename: str) -> str:
    """Finds and reads a browser script from current directory or subfolders."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, script_filename),
        os.path.join(base_dir, "browser_scripts", script_filename),
        os.path.join(base_dir, "scripts", script_filename),
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c, "r", encoding="utf-8") as f:
                return f.read()
    return ""


def parse_timestamp(val) -> str:
    """Formats various timestamp representations into clean UTC strings."""
    if not val:
        return ""
    if isinstance(val, (int, float)):
        # Normalize milliseconds to seconds
        if val > 1e11:
            val = val / 1000.0
        try:
            return datetime.fromtimestamp(val, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return str(val)
    if isinstance(val, str):
        # Attempt to parse ISO string if possible
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return val
    return str(val)


def sanitize_filename(name: str) -> str:
    """Creates a filesystem-safe filename."""
    clean = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_", ".")).strip()
    clean = clean.replace(" ", "_")
    return clean[:80] or "conversation"


# ------------------------------------------------------------------------------
# Parsers for Different Platforms
# ------------------------------------------------------------------------------

def parse_chatgpt(conversations_raw: list) -> list:
    """
    Parses ChatGPT's branched tree structure ('mapping' with 'current_node').
    Reconstructs the active branch in chronological order.
    """
    normalized = []
    for conv in conversations_raw:
        title = conv.get("title") or "Untitled Conversation"
        conv_id = conv.get("id") or conv.get("conversation_id") or "N/A"
        create_time = conv.get("create_time")
        mapping = conv.get("mapping") or {}
        current_node = conv.get("current_node")

        # Walk backward from current_node to root
        node_chain = []
        curr = current_node
        visited = set()
        while curr and curr in mapping and curr not in visited:
            visited.add(curr)
            node_chain.append(curr)
            curr = mapping[curr].get("parent")

        node_chain.reverse()

        messages = []
        for nid in node_chain:
            node = mapping.get(nid, {})
            msg = node.get("message")
            if not msg:
                continue

            author = msg.get("author", {}).get("role", "unknown")
            if author == "system":
                continue  # skip internal system prompts

            speaker = "USER" if author == "user" else "ASSISTANT"
            content = msg.get("content", {})
            parts = content.get("parts", [])

            text_parts = []
            for p in parts:
                if isinstance(p, str):
                    text_parts.append(p)
                elif isinstance(p, dict) and "text" in p:
                    text_parts.append(p["text"])

            body = "\n".join(text_parts).strip()
            if body:
                messages.append({
                    "author": speaker,
                    "text": body,
                    "timestamp": msg.get("create_time")
                })

        if messages:
            normalized.append({
                "platform": "ChatGPT",
                "title": title,
                "id": conv_id,
                "create_time": create_time,
                "messages": messages
            })

    return normalized


def parse_claude(conversations_raw: list) -> list:
    """
    Parses Claude's export structure ('chat_messages' with content blocks).
    """
    normalized = []
    for conv in conversations_raw:
        title = conv.get("name") or conv.get("title") or "Untitled Conversation"
        conv_id = conv.get("uuid") or conv.get("id") or "N/A"
        create_time = conv.get("created_at") or conv.get("create_time")
        raw_msgs = conv.get("chat_messages") or conv.get("messages") or []

        messages = []
        for m in raw_msgs:
            sender = (m.get("sender") or m.get("author") or "unknown").lower()
            speaker = "USER" if sender in ("human", "user") else "ASSISTANT"

            body = m.get("text") or ""
            content = m.get("content")
            if isinstance(content, list):
                c_texts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            c_texts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            c_texts.append(f"[Tool: {block.get('name')}]")
                    elif isinstance(block, str):
                        c_texts.append(block)
                if c_texts:
                    body = "\n".join(c_texts)
            elif isinstance(content, str):
                body = content

            if body.strip():
                messages.append({
                    "author": speaker,
                    "text": body.strip(),
                    "timestamp": m.get("created_at") or m.get("timestamp")
                })

        if messages:
            normalized.append({
                "platform": "Claude",
                "title": title,
                "id": conv_id,
                "create_time": create_time,
                "messages": messages
            })

    return normalized


def parse_copilot(conversations_raw: list) -> list:
    """
    Parses Microsoft Copilot Substrate JSON export.
    Resolves adaptive cards and citation references.
    """
    normalized = []
    for conv in conversations_raw:
        title = conv.get("chatName") or conv.get("title") or "Untitled Conversation"
        conv_id = conv.get("conversationId") or conv.get("id") or "N/A"
        create_time = conv.get("createTimeUtc") or conv.get("createdAt") or conv.get("timestamp")

        messages = []
        for m in conv.get("messages", []):
            author = (m.get("author") or "unknown").lower()
            speaker = "USER" if author == "user" else "COPILOT"

            body = m.get("text") or ""
            cards = m.get("adaptiveCards") or []
            if cards and isinstance(cards, list):
                try:
                    card_text = cards[0].get("body", [])[0].get("text", "")
                    if card_text:
                        body = card_text
                except Exception:
                    pass

            # Parse citations
            refs_list = []
            refs = m.get("references") or {}
            if refs and isinstance(refs, dict):
                for k, ref in refs.items():
                    link = ref.get("targetLink", "")
                    disp = ref.get("displayData", {})
                    ref_title = ""
                    if isinstance(disp, dict) and "content" in disp:
                        try:
                            parsed_c = json.loads(disp["content"])
                            ref_title = parsed_c.get("Title") or parsed_c.get("title") or ""
                        except Exception:
                            pass
                    refs_list.append({
                        "key": k,
                        "title": ref_title,
                        "url": link
                    })

            if body.strip():
                messages.append({
                    "author": speaker,
                    "text": body.strip(),
                    "timestamp": m.get("createdAt") or m.get("timestamp"),
                    "references": refs_list
                })

        if messages:
            normalized.append({
                "platform": "Copilot",
                "title": title,
                "id": conv_id,
                "create_time": create_time,
                "messages": messages
            })

    return normalized


def detect_and_normalize(data) -> list:
    """Auto-detects whether the JSON is Copilot, ChatGPT, or Claude."""
    if not isinstance(data, list):
        data = [data]
    if not data:
        return []

    sample = data[0]

    # Check for ChatGPT
    if "mapping" in sample:
        print("[*] Format Detected: ChatGPT (Export / Tree Mapping)")
        return parse_chatgpt(data)

    # Check for Claude
    if "chat_messages" in sample or ("uuid" in sample and "name" in sample):
        print("[*] Format Detected: Claude (Export Data)")
        return parse_claude(data)

    # Check for Copilot
    if "chatName" in sample or "conversationId" in sample or "adaptiveCards" in str(sample):
        print("[*] Format Detected: Microsoft Copilot (Substrate API)")
        return parse_copilot(data)

    # Check if already normalized
    if "messages" in sample and "title" in sample:
        print("[*] Format Detected: Standard Normalized Conversation")
        return data

    print("[-] Warning: Unrecognized schema, attempting best-effort extraction...")
    return parse_copilot(data)


# ------------------------------------------------------------------------------
# Formatters: TXT and Markdown
# ------------------------------------------------------------------------------

def format_conversation_txt(conv: dict, index: int = None) -> str:
    """Formats a single normalized conversation into plain text."""
    lines = []
    idx_str = f" {index}" if index else ""
    platform = conv.get("platform", "AI")
    title = conv.get("title", "Untitled Conversation")
    date_str = parse_timestamp(conv.get("create_time")) or "Unknown Date"
    conv_id = conv.get("id", "N/A")

    lines.append("#" * 80)
    lines.append(f"CONVERSATION{idx_str} [{platform}]: {title}")
    lines.append(f"Date: {date_str}")
    lines.append(f"ID:   {conv_id}")
    lines.append("#" * 80)
    lines.append("")

    for msg in conv.get("messages", []):
        author = msg.get("author", "UNKNOWN")
        msg_time = parse_timestamp(msg.get("timestamp"))
        time_part = f" ({msg_time})" if msg_time else ""

        lines.append(f"[{author}]{time_part}:")
        lines.append(msg.get("text", "").strip())

        refs = msg.get("references") or []
        if refs:
            lines.append("\nSources / Citations:")
            for r in refs:
                label = f"[{r['key']}] {r['title']} - {r['url']}" if r.get("title") else f"[{r['key']}] {r['url']}"
                lines.append(f"  {label}")

        lines.append("\n" + "-" * 80 + "\n")

    return "\n".join(lines)


def format_conversation_md(conv: dict, index: int = None) -> str:
    """Formats a single normalized conversation into clean Markdown."""
    lines = []
    idx_str = f"{index}. " if index else ""
    platform = conv.get("platform", "AI")
    title = conv.get("title", "Untitled Conversation")
    date_str = parse_timestamp(conv.get("create_time")) or "Unknown Date"
    conv_id = conv.get("id", "N/A")

    lines.append(f"## {idx_str}{title}\n")
    lines.append(f"**Platform:** `{platform}` | **Date:** `{date_str}` | **ID:** `{conv_id}`\n")

    for msg in conv.get("messages", []):
        author = msg.get("author", "UNKNOWN")
        header = "### User:" if author == "USER" else f"### {platform}:"
        lines.append(f"{header}\n")
        lines.append(msg.get("text", "").strip() + "\n")

        refs = msg.get("references") or []
        if refs:
            lines.append("\n**Sources:**")
            for r in refs:
                t = r.get("title") or f"Source [{r['key']}]"
                lines.append(f"- [{t}]({r.get('url', '#')})")
            lines.append("\n")

    lines.append("\n---\n")
    return "\n".join(lines)


def export_all(conversations: list, output_base: str, split_files: bool = False):
    """Writes combined or split .txt and .md files."""
    if not conversations:
        print("[-] No conversations to export.")
        return

    platform = conversations[0].get("platform", "AI Chat")

    if split_files:
        # Save individual files per chat
        folder_name = f"{output_base}_individual_chats"
        os.makedirs(folder_name, exist_ok=True)
        print(f"[*] Exporting {len(conversations)} individual conversation files into: {folder_name}/")

        for idx, conv in enumerate(conversations, 1):
            clean_title = sanitize_filename(conv.get("title", f"chat_{idx}"))
            file_name = f"{idx:03d}_{clean_title}"

            txt_p = os.path.join(folder_name, f"{file_name}.txt")
            md_p = os.path.join(folder_name, f"{file_name}.md")

            with open(txt_p, "w", encoding="utf-8") as f:
                f.write(format_conversation_txt(conv, idx))

            with open(md_p, "w", encoding="utf-8") as f:
                f.write(format_conversation_md(conv, idx))

        print(f"[OK] Successfully wrote {len(conversations) * 2} files into '{folder_name}'.")

    # Always generate the consolidated file as well
    txt_path = f"{output_base}.txt"
    md_path = f"{output_base}.md"

    header_txt = [
        "=" * 80,
        f"{platform.upper()} CONVERSATIONS ARCHIVE",
        f"Export Date:         {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Total Conversations: {len(conversations)}",
        "=" * 80,
        "\n\n"
    ]

    header_md = [
        f"# {platform} Conversations Archive\n",
        f"*Export Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*\n",
        f"*Total Conversations: {len(conversations)}*\n\n---\n\n"
    ]

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header_txt))
        for idx, c in enumerate(conversations, 1):
            f.write(format_conversation_txt(c, idx) + "\n\n")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("".join(header_md))
        for idx, c in enumerate(conversations, 1):
            f.write(format_conversation_md(c, idx) + "\n\n")

    print("\n" + "=" * 80)
    print(f"SUCCESS! Exported {len(conversations)} conversations:")
    print(f"  [Text File]     : {os.path.abspath(txt_path)}  ({os.path.getsize(txt_path):,} bytes)")
    print(f"  [Markdown File] : {os.path.abspath(md_path)}  ({os.path.getsize(md_path):,} bytes)")
    print("=" * 80 + "\n")


def convert_files(file_paths: list, split_files: bool = False):
    """Loads, merges, normalizes, and exports any supported JSON files."""
    if not file_paths:
        print("[-] No files specified.")
        return

    all_raw_data = []
    seen_ids = set()

    for fp in file_paths:
        if not os.path.exists(fp):
            print(f"[-] File not found: {fp}")
            continue

        print(f"[*] Reading '{fp}' ({os.path.getsize(fp):,} bytes)...")
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = [data]

            count_before = len(all_raw_data)
            for item in data:
                cid = item.get("conversation_id") or item.get("id") or item.get("uuid")
                if cid and cid in seen_ids:
                    continue
                if cid:
                    seen_ids.add(cid)
                all_raw_data.append(item)

            added = len(all_raw_data) - count_before
            print(f"    Added {added} conversations from {os.path.basename(fp)}.")
        except Exception as e:
            print(f"[-] Error reading {fp}: {e}")

    if not all_raw_data:
        print("[-] No valid conversations loaded.")
        return

    print(f"\n[*] Total unique conversations loaded: {len(all_raw_data)}")
    normalized = detect_and_normalize(all_raw_data)

    if len(file_paths) == 1:
        base_name, _ = os.path.splitext(file_paths[0])
    else:
        platform = normalized[0].get("platform", "ai").lower()
        base_name = f"{platform}_chats_merged_{len(normalized)}_convs"

    export_all(normalized, base_name, split_files=split_files)


def main():
    parser = argparse.ArgumentParser(description="Universal AI Chat Exporter (Copilot, ChatGPT, Claude)")
    parser.add_argument("files", nargs="*", help="Paths to JSON files to convert and merge")
    parser.add_argument("--split", action="store_true", help="Split conversations into individual .txt and .md files")
    parser.add_argument("--chatgpt", action="store_true", help="Copy ChatGPT 1-Click browser console script to clipboard")
    parser.add_argument("--claude", action="store_true", help="Copy Claude 1-Click browser console script to clipboard")
    parser.add_argument("--copilot", action="store_true", help="Copy Copilot 1-Click browser console script to clipboard")

    args = parser.parse_args()

    if args.chatgpt:
        script = load_browser_script("chatgpt_dump.js")
        if script and copy_to_clipboard(script):
            print("[OK] Smart ChatGPT browser script (with 429 retry & resume) copied to clipboard!")
        else:
            print("[!] Could not auto-copy. Please open 'chatgpt_dump.js' manually.")
        print("     1. Open https://chatgpt.com in your browser")
        print("     2. Press F12 -> Console -> Ctrl+V -> Enter")
        print("     3. It will download your conversations JSON file")
        print("     4. Run: python ai_chat_export.py <downloaded_file.json>")
        return

    if args.claude:
        script = load_browser_script("claude_dump.js")
        if script and copy_to_clipboard(script):
            print("[OK] Claude browser script copied to clipboard!")
        else:
            print("[!] Could not auto-copy. Please open 'claude_dump.js' manually.")
        print("     1. Open https://claude.ai in your browser")
        print("     2. Press F12 -> Console -> Ctrl+V -> Enter")
        print("     3. It will immediately download 'claude_chats_export_<date>.json'")
        print("     4. Run: python ai_chat_export.py <downloaded_file.json>")
        return

    if args.copilot:
        script = load_browser_script("copilot_dump.js")
        if script and copy_to_clipboard(script):
            print("[OK] Microsoft Copilot browser script copied to clipboard!")
        else:
            print("[!] Could not auto-copy. Please open 'copilot_dump.js' manually.")
        print("     1. Open https://m365.cloud.microsoft/chat or https://copilot.microsoft.com")
        print("     2. Press F12 -> Console -> Ctrl+V -> Enter")
        print("     3. It will download .txt, .md, and .json export files")
        return

    if args.files:
        convert_files(args.files, split_files=args.split)
        return

    # Interactive Menu
    print("\n" + "=" * 70)
    print("      UNIVERSAL AI CHAT EXPORTER (Copilot / ChatGPT / Claude)")
    print("=" * 70)
    print(" [1] Convert a JSON export file (Copilot, ChatGPT, or Claude)")
    print(" [2] Convert and SPLIT into individual chat files per topic")
    print(" [3] Copy 1-Click ChatGPT Browser Console Script to Clipboard")
    print(" [4] Copy 1-Click Claude Browser Console Script to Clipboard")
    print(" [5] Copy 1-Click Microsoft Copilot Browser Script to Clipboard")
    print(" [0] Exit")
    print("=" * 70)
    choice = input("Select an option [0-5]: ").strip()

    if choice == "1":
        f = input("Enter path to JSON file: ").strip().strip('"').strip("'")
        convert_files([f], split_files=False)
    elif choice == "2":
        f = input("Enter path to JSON file: ").strip().strip('"').strip("'")
        convert_files([f], split_files=True)
    elif choice == "3":
        script = load_browser_script("chatgpt_dump.js")
        if script and copy_to_clipboard(script):
            print("\n[OK] Copied ChatGPT script to clipboard! Paste into F12 Console on chatgpt.com.")
        else:
            print("\n[!] Please copy the code directly from 'chatgpt_dump.js'.")
    elif choice == "4":
        script = load_browser_script("claude_dump.js")
        if script and copy_to_clipboard(script):
            print("\n[OK] Copied Claude script to clipboard! Paste into F12 Console on claude.ai.")
        else:
            print("\n[!] Please copy the code directly from 'claude_dump.js'.")
    elif choice == "5":
        script = load_browser_script("copilot_dump.js")
        if script and copy_to_clipboard(script):
            print("\n[OK] Copied Copilot script to clipboard! Paste into F12 Console on Copilot.")
        else:
            print("\n[!] Please copy the code directly from 'copilot_dump.js'.")
    else:
        print("Exiting.")

if __name__ == "__main__":
    main()
