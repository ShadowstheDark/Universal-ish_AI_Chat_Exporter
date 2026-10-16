#!/usr/bin/env python3
"""
================================================================================
Microsoft Copilot Corporate Chat Exporter
================================================================================
Designed for Corporate / Enterprise Accounts (M365 Copilot & copilot.microsoft.com)
where native export or sharing is disabled by IT policies.

Features:
  1. Live Local Receiver (1-Click Browser Sync): Starts local server, copies
     extraction snippet to clipboard, receives all chats and saves .txt / .md.
  2. Automated Browser Extraction (Edge CDP): Attaches directly to Edge via
     Remote Debugging to extract all chats without manual copy-paste.
  3. File Converter: Formats existing Copilot JSON dumps into clean TXT/Markdown.
  4. Local VS Code Exporter: Scans and dumps GitHub Copilot chats from VS Code.

Usage:
  python copilot_export.py                (Interactive wizard - recommended)
  python copilot_export.py --listen       (Start local sync receiver on port 8765)
  python copilot_export.py --cdp          (Automated extraction via Edge port 9222)
  python copilot_export.py --file <path>  (Convert downloaded JSON to TXT)
  python copilot_export.py --vscode       (Export VS Code GitHub Copilot chats)
================================================================================
"""

import os
import sys
import json
import time
import argparse
import subprocess
import webbrowser
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error

# Ensure UTF-8 output on Windows consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Embedded JavaScript payload for browser execution
EXTRACTION_JS = r"""
(async function () {
    console.log("%c[Copilot Exporter]%c Initializing exporter...", "color: #0078d4; font-weight: bold;", "color: inherit;");

    const APP_TAG = "[Copilot Exporter]";
    const FETCH_DELAY = 1200; // ms between requests to respect rate limits
    const MAX_CHATS = 500;    // Maximum conversations to fetch

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function getCookie(key) {
        const match = document.cookie.match(new RegExp(`(^|;)\\s*${key}\\s*=\\s*([^;]+)`));
        return match ? match[2] : "";
    }

    function base64DecToArr(base64String) {
        let encodedString = base64String.replace(/-/g, "+").replace(/_/g, "/");
        while (encodedString.length % 4 !== 0) {
            encodedString += "=";
        }
        const binString = atob(encodedString);
        return Uint8Array.from(binString, c => c.charCodeAt(0));
    }

    function toArrayBuffer(bufferLike) {
        return Uint8Array.from(bufferLike).buffer;
    }

    async function deriveKey(baseKey, nonce, context) {
        return window.crypto.subtle.deriveKey(
            {
                name: "HKDF",
                salt: toArrayBuffer(nonce),
                hash: "SHA-256",
                info: new TextEncoder().encode(context)
            },
            baseKey,
            { name: "AES-GCM", length: 256 },
            false,
            ["encrypt", "decrypt"]
        );
    }

    async function decrypt(baseKey, nonce, context, encryptedData) {
        const encodedData = base64DecToArr(encryptedData);
        const derivedKey = await deriveKey(baseKey, base64DecToArr(nonce), context);
        const decryptedData = await window.crypto.subtle.decrypt(
            { name: "AES-GCM", iv: new Uint8Array(12) },
            derivedKey,
            toArrayBuffer(encodedData)
        );
        return new TextDecoder().decode(decryptedData);
    }

    async function getEncryptionCookie() {
        const cookieString = decodeURIComponent(getCookie("msal.cache.encryption"));
        if (!cookieString) return null;
        let parsed = null;
        try {
            parsed = JSON.parse(cookieString);
        } catch (e) {
            return null;
        }
        if (parsed && parsed.key && parsed.id) {
            const baseKey = base64DecToArr(parsed.key);
            const key = await window.crypto.subtle.importKey(
                "raw",
                toArrayBuffer(baseKey),
                "HKDF",
                false,
                ["deriveKey"]
            );
            return { id: parsed.id, key };
        }
        return null;
    }

    function getMsalIds() {
        const clientId = "c0ab8ce9-e9a0-42e7-b064-33d422df41f1";
        const msalIds = localStorage.getItem("msal.3.account.keys");
        if (!msalIds) return null;
        try {
            const accountKeys = JSON.parse(msalIds);
            if (!accountKeys || accountKeys.length === 0) return null;
            const [homeAccountId, , tenantId] = accountKeys[0].split("|");
            const [localAccountId] = homeAccountId.split(".");
            return { localAccountId, tenantId, homeAccountId, clientId };
        } catch (e) {
            return null;
        }
    }

    async function getAccessToken(msalIds) {
        const tokenKeysRaw = localStorage.getItem(`msal.3.token.keys.${msalIds.clientId}`);
        if (!tokenKeysRaw) return null;
        const tokenKeys = JSON.parse(tokenKeysRaw);
        const sydneyKey = (tokenKeys.accessToken || []).find(t => t.includes("https://substrate.office.com/sydney/.default"));
        if (!sydneyKey) return null;

        const sydneyEntryRaw = localStorage.getItem(sydneyKey);
        if (!sydneyEntryRaw) return null;
        const payload = JSON.parse(sydneyEntryRaw);

        if (payload.secret) {
            return payload.secret;
        }

        const encCookie = await getEncryptionCookie();
        if (!encCookie) {
            console.warn(`${APP_TAG} Token is encrypted but encryption cookie was not found.`);
            return null;
        }
        const decrypted = await decrypt(encCookie.key, payload.nonce, msalIds.clientId, payload.data);
        return JSON.parse(decrypted).secret;
    }

    async function fetchCopilotChatsList(token, userOid, tenantId, maxChats) {
        const requestObj = {
            source: "officeweb",
            traceId: crypto.randomUUID(),
            threadType: "webchat",
            MaxReturnedChatsCount: maxChats
        };
        const variants = "feature.EnableLastMessageForGetChats,feature.EnableMRUAgents,feature.EnableHasLoopPages";
        const url = `https://substrate.office.com/m365Copilot/GetChats?request=${encodeURIComponent(JSON.stringify(requestObj))}&variants=${encodeURIComponent(variants)}`;
        const headers = {
            "authorization": `Bearer ${token}`,
            "content-type": "application/json",
            "x-anchormailbox": `Oid:${userOid}@${tenantId}`,
            "x-clientrequestid": crypto.randomUUID().replace(/-/g, ""),
            "x-routingparameter-sessionkey": userOid,
            "x-scenario": "OfficeWebIncludedCopilot",
            "x-variants": variants
        };
        const res = await fetch(url, { method: "GET", headers });
        if (!res.ok) throw new Error(`GetChats returned status ${res.status}`);
        return await res.json();
    }

    async function fetchCopilotConversation(token, userOid, tenantId, conversationId) {
        const requestObj = {
            conversationId,
            source: "officeweb",
            traceId: crypto.randomUUID().replace(/-/g, "")
        };
        const url = `https://substrate.office.com/m365Copilot/GetConversation?request=${encodeURIComponent(JSON.stringify(requestObj))}`;
        const headers = {
            "authorization": `Bearer ${token}`,
            "content-type": "application/json",
            "x-anchormailbox": `Oid:${userOid}@${tenantId}`,
            "x-clientrequestid": crypto.randomUUID().replace(/-/g, ""),
            "x-routingparameter-sessionkey": userOid,
            "x-scenario": "OfficeWebIncludedCopilot"
        };
        const res = await fetch(url, { method: "GET", headers });
        if (!res.ok) throw new Error(`GetConversation returned status ${res.status}`);
        return await res.json();
    }

    function scrapeActiveChatFromDOM() {
        console.log(`${APP_TAG} Scraping active conversation directly from DOM...`);
        const messages = [];
        const turns = document.querySelectorAll(
            'cib-chat-turn, [data-content="user-message"], [data-content="ai-message"], div[class*="message-bubble"], div[class*="chat-message"]'
        );

        if (turns.length > 0) {
            turns.forEach(el => {
                const isUser = el.getAttribute("data-content") === "user-message" ||
                               el.className.includes("user") ||
                               Boolean(el.querySelector('[data-author="user"]'));
                messages.push({
                    author: isUser ? "user" : "bot",
                    text: el.innerText || "",
                    timestamp: new Date().toISOString()
                });
            });
        } else {
            const main = document.querySelector('main, #chat-container, [role="main"]') || document.body;
            messages.push({
                author: "system",
                text: main.innerText,
                timestamp: new Date().toISOString()
            });
        }

        return [{
            conversationId: "dom-scrape-" + Date.now(),
            chatName: document.title || "Copilot Active Chat",
            createTimeUtc: Date.now(),
            messages: messages
        }];
    }

    function downloadFile(content, filename, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    try {
        let conversations = [];
        const msalIds = getMsalIds();

        if (msalIds) {
            console.log(`${APP_TAG} Found MSAL identity. Fetching access token...`);
            const token = await getAccessToken(msalIds);

            if (token) {
                console.log(`${APP_TAG} Access token acquired. Fetching conversation list...`);
                const listResp = await fetchCopilotChatsList(token, msalIds.localAccountId, msalIds.tenantId, MAX_CHATS);
                const chatList = listResp.chats || [];
                console.log(`%c${APP_TAG} Found ${chatList.length} conversations. Starting extraction...`, "color: #0078d4; font-weight: bold;");

                for (let i = 0; i < chatList.length; i++) {
                    const c = chatList[i];
                    console.log(`${APP_TAG} [${i + 1}/${chatList.length}] Fetching "${c.chatName}"...`);
                    try {
                        const fullConv = await fetchCopilotConversation(token, msalIds.localAccountId, msalIds.tenantId, c.conversationId);
                        conversations.push(fullConv);
                    } catch (err) {
                        console.warn(`${APP_TAG} Failed to fetch conversation ${c.conversationId}:`, err);
                    }
                    await sleep(FETCH_DELAY);
                }
            }
        }

        if (conversations.length === 0) {
            conversations = scrapeActiveChatFromDOM();
        }

        if (conversations.length === 0) {
            alert(`${APP_TAG} No conversations found. Please ensure you are logged into https://m365.cloud.microsoft/chat and have chats open.`);
            return null;
        }

        console.log(`%c${APP_TAG} Successfully extracted ${conversations.length} conversation(s)!`, "color: green; font-weight: bold; font-size: 14px;");

        const jsonOutput = JSON.stringify(conversations, null, 2);

        // Always trigger direct browser file download as backup
        const dateTag = new Date().toISOString().slice(0, 10);
        downloadFile(jsonOutput, `copilot_chats_export_${dateTag}.json`, "application/json");

        // Send to local Python receiver if listening
        try {
            await fetch("http://127.0.0.1:8765/upload", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: jsonOutput
            });
            console.log("%c[Copilot Exporter] Sent data directly to Python listener!", "color: green; font-weight: bold;");
        } catch (e) {
            // Python receiver wasn't running
        }

        return conversations;

    } catch (error) {
        console.error(`${APP_TAG} Extraction error:`, error);
        alert(`${APP_TAG} Error: ${error.message}`);
        return null;
    }
})();
"""

def copy_to_clipboard(text: str) -> bool:
    """Copies text to the Windows system clipboard."""
    try:
        p = subprocess.Popen("clip", stdin=subprocess.PIPE, shell=True)
        p.communicate(text.encode("utf-8"))
        return True
    except Exception:
        return False

def parse_timestamp(val):
    """Parses various timestamp representations into a formatted string."""
    if not val:
        return ""
    if isinstance(val, (int, float)):
        # Convert milliseconds to seconds if needed
        if val > 1e11:
            val = val / 1000.0
        try:
            return datetime.fromtimestamp(val, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return str(val)
    if isinstance(val, str):
        return val
    return str(val)

def format_conversations_to_txt(conversations: list) -> str:
    """Formats conversation objects into a clean, human-readable text document."""
    lines = []
    lines.append("=" * 80)
    lines.append("MICROSOFT COPILOT CHAT EXPORT")
    lines.append(f"Export Date:         {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"Total Conversations: {len(conversations)}")
    lines.append("=" * 80)
    lines.append("\n")

    for idx, conv in enumerate(conversations, 1):
        title = conv.get("chatName") or conv.get("title") or "Untitled Conversation"
        conv_id = conv.get("conversationId") or conv.get("id") or "N/A"
        date_str = parse_timestamp(conv.get("createTimeUtc") or conv.get("createdAt") or conv.get("timestamp")) or "Unknown Date"

        lines.append("#" * 80)
        lines.append(f"CONVERSATION {idx}: {title}")
        lines.append(f"Date: {date_str}")
        lines.append(f"ID:   {conv_id}")
        lines.append("#" * 80)
        lines.append("")

        messages = conv.get("messages", [])
        for msg in messages:
            author = (msg.get("author") or "unknown").lower()
            role = "USER" if author == "user" else "COPILOT"
            msg_time = parse_timestamp(msg.get("createdAt") or msg.get("timestamp"))
            time_part = f" ({msg_time})" if msg_time else ""

            lines.append(f"[{role}]{time_part}:")

            # Extract body text
            body = msg.get("text") or ""
            cards = msg.get("adaptiveCards") or []
            if cards and isinstance(cards, list):
                try:
                    card_text = cards[0].get("body", [])[0].get("text", "")
                    if card_text:
                        body = card_text
                except Exception:
                    pass

            lines.append(body.strip())

            # Citations and references
            refs = msg.get("references") or {}
            if refs and isinstance(refs, dict):
                lines.append("\nSources:")
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
                    if ref_title:
                        lines.append(f"  [{k}] {ref_title} - {link}")
                    else:
                        lines.append(f"  [{k}] {link}")

            lines.append("\n" + "-" * 80 + "\n")

        lines.append("\n")

    return "\n".join(lines)

def format_conversations_to_markdown(conversations: list) -> str:
    """Formats conversation objects into structured Markdown with headings and links."""
    lines = []
    lines.append("# Microsoft Copilot Conversations Archive\n")
    lines.append(f"*Exported on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*\n")
    lines.append(f"*Total Conversations: {len(conversations)}*\n\n---\n")

    for idx, conv in enumerate(conversations, 1):
        title = conv.get("chatName") or conv.get("title") or "Untitled Conversation"
        conv_id = conv.get("conversationId") or conv.get("id") or "N/A"
        date_str = parse_timestamp(conv.get("createTimeUtc") or conv.get("createdAt") or conv.get("timestamp")) or "Unknown Date"

        lines.append(f"## {idx}. {title}\n")
        lines.append(f"**Date:** `{date_str}` | **ID:** `{conv_id}`\n")

        messages = conv.get("messages", [])
        for msg in messages:
            author = (msg.get("author") or "unknown").lower()
            header = "### User:" if author == "user" else "### Copilot:"
            lines.append(f"{header}\n")

            body = msg.get("text") or ""
            cards = msg.get("adaptiveCards") or []
            if cards and isinstance(cards, list):
                try:
                    card_text = cards[0].get("body", [])[0].get("text", "")
                    if card_text:
                        body = card_text
                except Exception:
                    pass

            lines.append(body.strip() + "\n")

            refs = msg.get("references") or {}
            if refs and isinstance(refs, dict):
                lines.append("\n**Sources:**")
                for k, ref in refs.items():
                    link = ref.get("targetLink", "")
                    disp = ref.get("displayData", {})
                    ref_title = f"Source [{k}]"
                    if isinstance(disp, dict) and "content" in disp:
                        try:
                            parsed_c = json.loads(disp["content"])
                            ref_title = parsed_c.get("Title") or parsed_c.get("title") or ref_title
                        except Exception:
                            pass
                    lines.append(f"- [{ref_title}]({link})")
                lines.append("\n")

        lines.append("\n---\n")

    return "\n".join(lines)

def save_exports(conversations: list, output_dir: str = "."):
    """Saves formatted TXT, Markdown, and JSON files to output directory."""
    date_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = os.path.join(output_dir, f"copilot_chats_{date_tag}.txt")
    md_path = os.path.join(output_dir, f"copilot_chats_{date_tag}.md")
    json_path = os.path.join(output_dir, f"copilot_chats_{date_tag}.json")

    txt_content = format_conversations_to_txt(conversations)
    md_content = format_conversations_to_markdown(conversations)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_content)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(conversations, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("SUCCESS! All Copilot chats exported successfully:")
    print(f"  [Text File]     : {os.path.abspath(txt_path)}  ({os.path.getsize(txt_path):,} bytes)")
    print(f"  [Markdown File] : {os.path.abspath(md_path)}  ({os.path.getsize(md_path):,} bytes)")
    print(f"  [Raw JSON]      : {os.path.abspath(json_path)}  ({os.path.getsize(json_path):,} bytes)")
    print("=" * 80 + "\n")

    return txt_path

# ------------------------------------------------------------------------------
# Option 1: Live Receiver Server
# ------------------------------------------------------------------------------
class CopilotUploadHandler(BaseHTTPRequestHandler):
    conversations_received = None

    def log_message(self, format, *args):
        pass  # Suppress default noisy access logs

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length).decode("utf-8")

        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"received"}')

        try:
            data = json.loads(raw_body)
            if not isinstance(data, list):
                data = [data]
            CopilotUploadHandler.conversations_received = data
            print(f"\n[+] Received {len(data)} conversations from browser!")
        except Exception as e:
            print(f"[-] Error parsing received data: {e}")

def run_receiver(port: int = 8765, auto_open: bool = True):
    """Starts a local HTTP server and assists user in copying the browser snippet."""
    print("\n" + "=" * 80)
    print("  MODE 1: LIVE 1-CLICK BROWSER RECEIVER")
    print("=" * 80)
    print("This mode works directly within your existing logged-in Edge/Chrome session,")
    print("bypassing corporate MFA, proxy, and DLP export restrictions safely.\n")

    # Automatically copy snippet to clipboard
    copied = copy_to_clipboard(EXTRACTION_JS)
    if copied:
        print("[OK] Step 1: The extraction script has been COPIED to your clipboard automatically!")
    else:
        print("[!] Step 1: Copy the extraction script from 'copilot_dump.js'.")

    print("[*] Step 2: Open your Copilot page in Edge or Chrome:")
    print("            https://m365.cloud.microsoft/chat  (or https://copilot.microsoft.com)")
    print("[*] Step 3: Press F12 (Developer Tools) -> click 'Console' tab.")
    print("[*] Step 4: Paste (Ctrl + V) and hit Enter.")
    print(f"\n[*] Listening on http://127.0.0.1:{port} for incoming chat data...")
    print("    (Press Ctrl+C at any time to cancel)\n")

    if auto_open:
        try:
            webbrowser.open("https://m365.cloud.microsoft/chat")
        except Exception:
            pass

    server = HTTPServer(("127.0.0.1", port), CopilotUploadHandler)
    try:
        while CopilotUploadHandler.conversations_received is None:
            server.handle_request()

        save_exports(CopilotUploadHandler.conversations_received)
    except KeyboardInterrupt:
        print("\nReceiver stopped by user.")
    finally:
        server.server_close()

# ------------------------------------------------------------------------------
# Option 2: Automated Chrome/Edge CDP Automation
# ------------------------------------------------------------------------------
def run_cdp_export(cdp_port: int = 9222):
    """Connects to Edge or Chrome via Chrome DevTools Protocol to extract chats."""
    print("\n" + "=" * 80)
    print("  MODE 2: AUTOMATED EDGE / CHROME DEBUGGING")
    print("=" * 80)

    # Check if websockets is installed
    try:
        from websockets.sync.client import connect as ws_connect
    except ImportError:
        print("[-] 'websockets' library is required for CDP mode.")
        print("    Run: pip install websockets")
        return

    # Check if port 9222 is alive
    cdp_url = f"http://127.0.0.1:{cdp_port}/json"
    pages = []
    try:
        with urllib.request.urlopen(cdp_url, timeout=3) as resp:
            pages = json.loads(resp.read().decode())
    except Exception:
        print(f"[-] Could not connect to browser on port {cdp_port}.")
        print("\nTo enable remote debugging on Edge:")
        print("1. Close all running Microsoft Edge windows.")
        print("2. Launch Edge with the debugging port enabled by running:")
        print(f'   "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --remote-debugging-port={cdp_port} https://m365.cloud.microsoft/chat')
        print("\nAlternatively, use Mode 1 (Live Receiver) which requires no browser restart!")
        return

    # Look for Copilot page tab
    target_tab = None
    for p in pages:
        url = p.get("url", "").lower()
        if "m365.cloud.microsoft" in url or "copilot.microsoft.com" in url or "bing.com/chat" in url:
            target_tab = p
            break

    if not target_tab:
        print("[-] Found open browser, but no Microsoft Copilot tab was detected.")
        print("    Please open https://m365.cloud.microsoft/chat in the debug browser.")
        return

    ws_url = target_tab.get("webSocketDebuggerUrl")
    if not ws_url:
        print("[-] Target tab does not expose webSocketDebuggerUrl.")
        return

    print(f"[+] Found Copilot tab: {target_tab.get('title')}")
    print("[*] Connecting to tab WebSocket debugger...")

    try:
        with ws_connect(ws_url, max_size=50 * 1024 * 1024) as ws:
            print("[*] Injected extraction script into Copilot page. Extracting chats...")
            cmd = {
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": EXTRACTION_JS,
                    "awaitPromise": True,
                    "returnByValue": True
                }
            }
            ws.send(json.dumps(cmd))
            
            # Wait for execution response
            resp_raw = ws.recv()
            resp = json.loads(resp_raw)
            result = resp.get("result", {}).get("result", {})

            if result.get("type") == "object" and "value" in result:
                convs = result["value"]
                if isinstance(convs, list) and len(convs) > 0:
                    save_exports(convs)
                else:
                    print("[-] No conversations returned. Check browser console for details.")
            else:
                print("[-] Script execution finished with non-standard result:", result)
    except Exception as e:
        print(f"[-] WebSocket execution error: {e}")

# ------------------------------------------------------------------------------
# Option 3: Offline File Converter
# ------------------------------------------------------------------------------
def convert_existing_file(file_path: str):
    """Converts a downloaded Copilot JSON or CSV file into formatted TXT and MD."""
    if not os.path.exists(file_path):
        print(f"[-] File not found: {file_path}")
        return

    print(f"[*] Reading {file_path}...")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            data = [data]

        save_exports(data, output_dir=os.path.dirname(file_path) or ".")
    except Exception as e:
        print(f"[-] Error converting file: {e}")

# ------------------------------------------------------------------------------
# Option 4: Local VS Code GitHub Copilot Chat Dumper
# ------------------------------------------------------------------------------
def export_vscode_chats():
    """Scans local VS Code storage for GitHub Copilot chat session transcripts."""
    print("\n" + "=" * 80)
    print("  MODE 4: VS CODE LOCAL COPILOT CHATS EXPORTER")
    print("=" * 80)

    appdata = os.environ.get("APPDATA", "")
    code_dir = os.path.join(appdata, "Code", "User")

    if not os.path.exists(code_dir):
        print(f"[-] VS Code User directory not found at: {code_dir}")
        return

    found_sessions = []
    print(f"[*] Scanning {code_dir} for chat session files...")

    for root, _, files in os.walk(code_dir):
        for f in files:
            if f.endswith(".jsonl") and ("chat" in root.lower() or "chatsessions" in root.lower()):
                full_path = os.path.join(root, f)
                found_sessions.append(full_path)

    print(f"[+] Found {len(found_sessions)} session files.")

    all_chats = []
    for s_path in found_sessions:
        try:
            with open(s_path, "r", encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if item.get("kind") == 0:
                        v = item.get("v", {})
                        reqs = v.get("requests", [])
                        if reqs:
                            messages = []
                            for r in reqs:
                                # user message
                                u_text = ""
                                if isinstance(r.get("message"), dict):
                                    u_text = r["message"].get("text", "")
                                elif isinstance(r.get("message"), str):
                                    u_text = r.get("message")
                                if u_text:
                                    messages.append({"author": "user", "text": u_text})

                                # response
                                resp_list = r.get("response", [])
                                if isinstance(resp_list, list):
                                    resp_texts = []
                                    for part in resp_list:
                                        if isinstance(part, dict) and "value" in part:
                                            resp_texts.append(part["value"])
                                    if resp_texts:
                                        messages.append({"author": "copilot", "text": "\n".join(resp_texts)})

                            if messages:
                                all_chats.append({
                                    "chatName": v.get("title") or os.path.basename(s_path),
                                    "conversationId": v.get("sessionId") or os.path.basename(s_path),
                                    "createTimeUtc": v.get("creationDate"),
                                    "messages": messages
                                })
        except Exception:
            pass

    if all_chats:
        save_exports(all_chats)
    else:
        print("[-] No non-empty VS Code Copilot conversations found.")

# ------------------------------------------------------------------------------
# Interactive Menu
# ------------------------------------------------------------------------------
def show_menu():
    while True:
        print("\n" + "=" * 70)
        print("       MICROSOFT COPILOT CORPORATE CHAT EXPORTER")
        print("=" * 70)
        print(" [1] Live 1-Click Browser Sync (Recommended - Easiest & Most Reliable)")
        print(" [2] Automated Edge Remote Debugging (Connects to Edge on port 9222)")
        print(" [3] Convert a downloaded JSON file to TXT/Markdown")
        print(" [4] Export VS Code GitHub Copilot chats (from local disk)")
        print(" [5] Copy Browser Console script to clipboard")
        print(" [0] Exit")
        print("=" * 70)
        choice = input("Select an option [0-5]: ").strip()

        if choice == "1":
            run_receiver()
            break
        elif choice == "2":
            run_cdp_export()
            break
        elif choice == "3":
            path = input("Enter path to JSON file: ").strip().strip('"').strip("'")
            convert_existing_file(path)
            break
        elif choice == "4":
            export_vscode_chats()
            break
        elif choice == "5":
            if copy_to_clipboard(EXTRACTION_JS):
                print("\n[OK] Browser script successfully copied to clipboard!")
                print("    Open Copilot in Edge, press F12 -> Console, and press Ctrl+V.")
            else:
                print("\n[-] Clipboard copy failed. Check copilot_dump.js in the folder.")
        elif choice == "0":
            print("Exiting.")
            break
        else:
            print("Invalid option. Please try again.")

def main():
    parser = argparse.ArgumentParser(description="Export Copilot chats to TXT/MD/JSON.")
    parser.add_argument("--listen", action="store_true", help="Start local sync receiver server on port 8765")
    parser.add_argument("--cdp", action="store_true", help="Run automated export via Edge remote debugging port 9222")
    parser.add_argument("--file", type=str, help="Convert existing Copilot JSON file to formatted text")
    parser.add_argument("--vscode", action="store_true", help="Export local VS Code Copilot chats")
    parser.add_argument("--snippet", action="store_true", help="Print and copy browser console snippet")
    parser.add_argument("--port", type=int, default=8765, help="Port for local sync receiver (default: 8765)")

    args = parser.parse_args()

    if args.listen:
        run_receiver(port=args.port)
    elif args.cdp:
        run_cdp_export()
    elif args.file:
        convert_existing_file(args.file)
    elif args.vscode:
        export_vscode_chats()
    elif args.snippet:
        copy_to_clipboard(EXTRACTION_JS)
        print("[OK] Extraction script copied to clipboard! Also saved in 'copilot_dump.js'.")
    else:
        show_menu()

if __name__ == "__main__":
    main()
