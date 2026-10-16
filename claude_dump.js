/**
 * Claude Instant Chat Exporter (Browser Console Script)
 * Works on: https://claude.ai
 *
 * Key Features:
 * - ⏹ Stop & Save Anytime: Type `stopExport()` in the console or click the on-screen button.
 * - Auto-Download: Saves structured JSON directly to your browser's Downloads folder.
 *
 * Instructions:
 * 1. Open https://claude.ai while logged into your account.
 * 2. Press F12 (or right-click -> Inspect) and select the "Console" tab.
 * 3. Paste this script and press Enter.
 * 4. To stop early: Click the red "Stop & Save" button or type `stopExport()`.
 */
(async function () {
    console.log("%c[Claude Exporter]%c Initializing exporter...", "color: #d97706; font-weight: bold;", "color: inherit;");

    let isStopRequested = false;
    let currentSleepResolve = null;

    function cancellableSleep(ms) {
        return new Promise(resolve => {
            currentSleepResolve = resolve;
            setTimeout(() => {
                currentSleepResolve = null;
                resolve();
            }, ms);
        });
    }

    function triggerStop() {
        if (isStopRequested) return;
        isStopRequested = true;
        console.log("%c[Claude Exporter] Stop requested! Finalizing and saving downloaded chats...", "color: #ef4444; font-weight: bold;");
        if (currentSleepResolve) currentSleepResolve();
    }

    window.stopExport = triggerStop;
    window.stopClaudeExport = triggerStop;

    function createFloatingWidget(total) {
        const existing = document.getElementById("ai-exporter-overlay");
        if (existing) existing.remove();

        const widget = document.createElement("div");
        widget.id = "ai-exporter-overlay";
        widget.style.cssText = `
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 999999;
            background: rgba(15, 23, 42, 0.94);
            color: #f8fafc;
            padding: 12px 18px;
            border-radius: 12px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.18);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 16px;
            backdrop-filter: blur(8px);
        `;

        widget.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 3px;">
                <div style="font-weight: 600; color: #d97706; display: flex; align-items: center; gap: 6px;">
                    <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#d97706;"></span>
                    Claude Exporter
                </div>
                <div id="ai-exporter-status" style="color: #cbd5e1; font-size: 12px;">Fetching conversations...</div>
            </div>
            <button id="ai-exporter-stop-btn" style="
                background: #ef4444;
                color: #ffffff;
                border: none;
                padding: 7px 13px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                cursor: pointer;
            ">
                ⏹ Stop & Save Now
            </button>
        `;

        document.body.appendChild(widget);

        const btn = document.getElementById("ai-exporter-stop-btn");
        btn.onclick = () => {
            btn.disabled = true;
            btn.innerText = "Saving...";
            triggerStop();
        };

        return {
            update(current, totalCount, title) {
                const status = document.getElementById("ai-exporter-status");
                if (status) {
                    const shortTitle = title ? ` ("${title.slice(0, 18)}...")` : "";
                    status.innerText = `[${current}/${totalCount}] fetched${shortTitle}`;
                }
            },
            remove() {
                const el = document.getElementById("ai-exporter-overlay");
                if (el) el.remove();
            }
        };
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

    let overlay = null;

    try {
        const orgRes = await fetch("/api/organizations");
        const orgs = await orgRes.json();
        const orgId = orgs[0]?.uuid;
        if (!orgId) throw new Error("Could not find active Claude organization ID.");

        console.log(`[Claude Exporter] Active Organization: ${orgId}`);
        const listRes = await fetch(`/api/organizations/${orgId}/chat_conversations`);
        const chatsList = await listRes.json();

        console.log(`%c[Claude Exporter] Found ${chatsList.length} conversations. Fetching details...`, "color: #d97706; font-weight: bold;");

        overlay = createFloatingWidget(chatsList.length);
        const fullConversations = [];

        for (let i = 0; i < chatsList.length; i++) {
            if (isStopRequested) break;

            const chat = chatsList[i];
            overlay.update(i + 1, chatsList.length, chat.name);
            console.log(`[${i + 1}/${chatsList.length}] Fetching "${chat.name}"...`);

            try {
                const cRes = await fetch(`/api/organizations/${orgId}/chat_conversations/${chat.uuid}`);
                if (cRes.ok) {
                    const cData = await cRes.json();
                    fullConversations.push(cData);
                }
            } catch (e) {}

            if (isStopRequested) break;
            await cancellableSleep(600); // Rate limit safety
        }

        if (overlay) overlay.remove();

        if (fullConversations.length === 0) {
            alert("[Claude Exporter] No conversations were downloaded.");
            return;
        }

        const dateTag = new Date().toISOString().slice(0, 10);
        const filename = `claude_chats_export_${dateTag}.json`;
        downloadFile(JSON.stringify(fullConversations, null, 2), filename, "application/json");

        alert(`Success! Exported ${fullConversations.length} Claude conversation(s) to '${filename}'.\n\nNext step:\nRun python ai_chat_export.py "${filename}" to convert to clean text/markdown.`);
    } catch (e) {
        if (overlay) overlay.remove();
        console.error(e);
        alert("Claude export error: " + e.message);
    }
})();
