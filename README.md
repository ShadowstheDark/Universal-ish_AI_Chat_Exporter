# 🌐 Universal AI Chat Exporter

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Standard%20Lib)-success)](#features)
[![Privacy](https://img.shields.io/badge/Privacy-100%25%20Local-blue)](#privacy--security)

Export your full conversation histories from **ChatGPT**, **Claude**, and **Microsoft Copilot** (Personal & Enterprise M365) into clean, beautifully formatted **Plain Text (`.txt`)** and **Markdown (`.md`)** files.

This exists because the current ways are to rely on the companies to give you **your** data and they just be making it extra annoying for no reason which is ironic considering how they got their data.

**Note: If you have like a ton of Conversations like 200+ it will hit the rate limit in that case just let the program run in the background and you'll have your chats in a couple of hours or so. (yes this is hacky, sue me)
**
---

## ⚡ Highlights

- **🔒 100% Local & Private:** Runs entirely within your own browser and machine. No API keys, passwords, or conversations are ever sent to any third-party server.
- **🚀 Zero Python Dependencies:** Built using Python's standard library (`json`, `urllib`, `http.server`). No `pip install` required!
- **🏢 Enterprise Bypasses:** Extracts corporate chats from **Microsoft Copilot (M365)** even when IT policies disable native export or sharing.
- **🛡️ Rate-Limit Resilience:** Features automatic HTTP 429 exponential backoff, safe request pacing, and offset-based resuming for accounts with hundreds of conversations (aka it waits for a bit before retrying when it hits the rate limit).
- **🌳 Tree Branch Reconstruction:** Reconstructs ChatGPT's complex tree-branched node mapping into chronological linear discussions.
- **📑 Dual Output Modes:** Generate one master archive file or split conversations into individual topic files.

---

## 📁 Repository Structure

```text
ai-chats-exports/
├── ai_chat_export.py     # Universal converter & CLI tool (detects format automatically)
├── copilot_export.py     # Copilot corporate extractor (Local Sync Receiver & CDP)
├── chatgpt_dump.js       # Browser console script for https://chatgpt.com
├── claude_dump.js        # Browser console script for https://claude.ai
├── copilot_dump.js       # Browser console script for M365 Copilot
├── .gitignore            # Safeguard to prevent chat logs from being committed
├── LICENSE               # MIT License
└── README.md
```

---

## Quick Start Guide

### Option 1: Interactive Menu (Easiest)

Simply run:
```bash
python ai_chat_export.py
```
You'll see an interactive menu where you can copy the browser extraction scripts to your clipboard or convert downloaded JSON files with a single keystroke.

---

### Option 2: Step-by-Step Per Service

#### 🟢 1. ChatGPT (`chatgpt.com`)
1. Log into [chatgpt.com](https://chatgpt.com) in Chrome, Edge, or Firefox.
2. Open Developer Tools: press `F12` (or Right-Click $\rightarrow$ **Inspect**) and click the **Console** tab.
3. Copy the script:
   - Run `python ai_chat_export.py --chatgpt` to copy it to your clipboard automatically, OR copy the contents of [`chatgpt_dump.js`](chatgpt_dump.js).
4. Paste it into the browser console and hit `Enter`.
5. It will safely fetch all conversations and trigger a download of `chatgpt_chats_export_<date>.json`.
6. Convert to clean Markdown and Text:
   ```bash
   python ai_chat_export.py "path/to/chatgpt_chats_export.json"
   ```

> **Tip (Resuming large accounts):** If you have over 500 chats and want to resume where you left off, edit line 25 of `chatgpt_dump.js` (e.g. `const START_OFFSET = 200;`).

---

#### 🟠 2. Claude (`claude.ai`)
1. Log into [claude.ai](https://claude.ai).
2. Open Developer Tools (`F12` $\rightarrow$ **Console**).
3. Copy the script:
   - Run `python ai_chat_export.py --claude`, OR copy [`claude_dump.js`](claude_dump.js).
4. Paste into the console and press `Enter`.
5. It downloads `claude_chats_export_<date>.json`.
6. Convert to clean Markdown and Text:
   ```bash
   python ai_chat_export.py "path/to/claude_chats_export.json"
   ```

---

#### 🔵 3. Microsoft Copilot (M365 & Personal)
For corporate accounts where export is blocked:

**Method A: 1-Click Live Local Sync (Recommended)**
1. Run the local receiver:
   ```bash
   python copilot_export.py --listen
   ```
   *(This automatically copies the extraction script to your clipboard and opens a local receiver on port 8765)*
2. Go to your Copilot tab ([m365.cloud.microsoft/chat](https://m365.cloud.microsoft/chat) or [copilot.microsoft.com](https://copilot.microsoft.com)).
3. Press `F12` $\rightarrow$ **Console** $\rightarrow$ press `Ctrl+V` $\rightarrow$ `Enter`.
4. The browser script extracts all chats, sends them directly to your running Python receiver, and saves `.txt`, `.md`, and `.json` automatically.

**Method B: Browser Console Only**
- Copy [`copilot_dump.js`](copilot_dump.js) into your browser console. It will decrypt tokens client-side, query the Substrate API, and trigger browser file downloads.

---

## 🛠️ Advanced Usage & Options

### Split into Individual Conversation Files
If you prefer each conversation in its own separate file organized by title:
```bash
python ai_chat_export.py --split "path/to/export.json"
```
This generates a folder named `*_individual_chats/` containing indexed files:
- `001_Python_Async_Architecture.md`
- `002_Quarterly_Strategy_Draft.md`

### Merge Multiple Part Exports
If you exported your chats in multiple chunks (e.g., part 1 and part 2):
```bash
python ai_chat_export.py part1.json part2.json
```
The script will deduplicate conversations by ID and combine them into a single archive.

---

## 🔄 Maintenance & Keeping Up With UI/API Changes

Web platforms update their frontend code and API routes from time to time. This project is intentionally designed to be transparent and straightforward to maintain:

### How it works under the hood:
1. **Authentication:** The browser scripts reuse your existing active browser session cookie/token (no credentials entered in scripts).
2. **Data endpoints:**
   - **ChatGPT:** `/backend-api/conversations` and `/backend-api/conversation/<id>`
   - **Claude:** `/api/organizations/<orgId>/chat_conversations`
   - **Copilot:** Substrate API `https://substrate.office.com/m365Copilot/GetChats`

### Updating with AI Assistants (Antigravity, Cursor, etc.):
If OpenAI, Anthropic, or Microsoft ever updates their internal payload format:
1. Open your browser DevTools (`F12`), go to the **Network** tab, and filter by `Fetch/XHR` to view the new conversation endpoint.
2. Open this folder in an AI coding assistant (like **Google Antigravity**) and prompt:
   > *"The service changed its conversation API response to [paste new response sample]. Please update the extraction script and the parser in ai_chat_export.py to support this format."*
3. Test locally and submit a Pull Request!

---

## 🔒 Privacy & Security

- **No telemetry, no analytics, no external servers.**
- All conversion and formatting happens strictly in-memory on your local device.

---

## 📜 License

This project is licensed under the [MIT License](LICENSE). Feel free to use, modify, and distribute.
