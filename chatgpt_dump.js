/**
 * ChatGPT Smart Chat Exporter (With 429 Rate-Limit Retry, Early Stop & Resume Support)
 * Works on: https://chatgpt.com
 *
 * Key Features:
 * - ⏹ Stop & Save Anytime: Click the on-screen "Stop & Save Now" button or type `stopExport()`
 *   in the console to instantly download whatever you've fetched so far.
 * - 🔄 Resume Support: Prints the exact START_OFFSET to resume right where you left off.
 * - 🛡️ 429 Too Many Requests Handling: Automatically pauses and retries with backoff.
 * - ⏱️ Safe Pacing: 1.4s delay + periodic pauses to stay under OpenAI rate limits.
 *
 * Instructions:
 * 1. Open https://chatgpt.com while logged into your account.
 * 2. Press F12 (or right-click -> Inspect) -> click "Console".
 * 3. Paste this script and press Enter.
 * 4. To stop early: Click the red "Stop & Save" button on the bottom right or type `stopExport()`.
 */

(async function () {
    console.log("%c[ChatGPT Exporter v2.1]%c Initializing smart exporter...", "color: #10a37f; font-weight: bold; font-size: 14px;", "color: inherit;");

    // =========================================================================
    // CONFIGURATION
    // =========================================================================
    // If you already downloaded conversations (e.g. the first 200) and need to resume,
    // change this value to skip those (e.g. const START_OFFSET = 200;)
    const START_OFFSET = 0; 

    const BASE_DELAY_MS = 1400;      // ms delay between conversations (safe pacing)
    const BATCH_REST_INTERVAL = 30;  // Pause every N conversations
    const BATCH_REST_MS = 5000;      // Rest pause duration (5 seconds)
    const MAX_RETRIES = 6;           // Max attempts when hitting 429

    // =========================================================================
    // STOP & SAVE CONTROLS
    // =========================================================================
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
        console.log("%c[ChatGPT Exporter] Stop requested! Finalizing downloaded chats and saving...", "color: #ef4444; font-weight: bold; font-size: 13px;");
        if (currentSleepResolve) {
            currentSleepResolve(); // Break sleep immediately
        }
    }

    // Expose stop command to DevTools console
    window.stopExport = triggerStop;
    window.stopChatGPTExport = triggerStop;

    // =========================================================================
    // ON-SCREEN FLOATING WIDGET
    // =========================================================================
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
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.18);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 16px;
            backdrop-filter: blur(8px);
            transition: all 0.3s ease;
        `;

        widget.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 3px;">
                <div style="font-weight: 600; color: #10a37f; display: flex; align-items: center; gap: 6px;">
                    <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#10a37f;"></span>
                    ChatGPT Exporter
                </div>
                <div id="ai-exporter-status" style="color: #cbd5e1; font-size: 12px;">Connecting...</div>
            </div>
            <button id="ai-exporter-stop-btn" title="Stop now and save downloaded chats" style="
                background: #ef4444;
                color: #ffffff;
                border: none;
                padding: 7px 13px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 5px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            ">
                ⏹ Stop & Save Now
            </button>
        `;

        document.body.appendChild(widget);

        const btn = document.getElementById("ai-exporter-stop-btn");
        btn.onmouseover = () => btn.style.background = "#dc2626";
        btn.onmouseout = () => btn.style.background = "#ef4444";
        btn.onclick = () => {
            btn.disabled = true;
            btn.innerText = "Saving...";
            btn.style.background = "#64748b";
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

    // =========================================================================
    // HELPERS & STORAGE
    // =========================================================================
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

    // Robust fetch with 429 Exponential Backoff & Cancellable Sleep
    async function fetchWithRetry(url, headers) {
        let attempt = 0;
        let waitSeconds = 10;

        while (attempt < MAX_RETRIES && !isStopRequested) {
            try {
                const res = await fetch(url, { headers });

                if (res.status === 429) {
                    attempt++;
                    const retryHeader = res.headers.get("Retry-After");
                    const backoffTime = retryHeader ? parseInt(retryHeader, 10) : waitSeconds;
                    console.warn(`%c[ChatGPT Exporter] 429 Rate Limit hit! Waiting ${backoffTime}s before retry (Attempt ${attempt}/${MAX_RETRIES})...`, "color: #eab308; font-weight: bold;");
                    await cancellableSleep(backoffTime * 1000);
                    waitSeconds = Math.min(waitSeconds * 2, 60);
                    continue;
                }

                if (!res.ok) {
                    console.warn(`[ChatGPT Exporter] HTTP ${res.status} for ${url}`);
                    return null;
                }

                return await res.json();
            } catch (err) {
                if (isStopRequested) return null;
                attempt++;
                console.warn(`[ChatGPT Exporter] Network error: ${err.message}. Retrying in ${waitSeconds}s...`);
                await cancellableSleep(waitSeconds * 1000);
                waitSeconds = Math.min(waitSeconds * 2, 60);
            }
        }

        if (!isStopRequested) {
            console.error(`[ChatGPT Exporter] Failed after ${MAX_RETRIES} retries: ${url}`);
        }
        return null;
    }

    // =========================================================================
    // MAIN EXECUTION
    // =========================================================================
    let overlay = null;

    try {
        console.log("%c[ChatGPT Exporter] Tip: You can type stopExport() in this console or click the on-screen button to stop & save at any time!", "color: #0284c7; font-weight: bold;");

        // 1. Get Authentication Token
        const sessRes = await fetch("/api/auth/session");
        if (!sessRes.ok) throw new Error("Could not retrieve session. Please refresh chatgpt.com and try again.");
        const sess = await sessRes.json();
        const token = sess.accessToken;
        const headers = token ? { "Authorization": `Bearer ${token}` } : {};

        // 2. Fetch Full Conversation List
        console.log("[ChatGPT Exporter] Querying conversation directory...");
        let offset = 0;
        const limit = 50;
        let allItems = [];

        while (!isStopRequested) {
            const listUrl = `/backend-api/conversations?offset=${offset}&limit=${limit}&order=updated`;
            const listData = await fetchWithRetry(listUrl, headers);
            if (!listData) break;

            const items = listData.items || [];
            if (items.length === 0) break;

            allItems.push(...items);
            offset += items.length;
            console.log(`[ChatGPT Exporter] Loaded ${allItems.length} conversation headers...`);
            if (items.length < limit) break;
            await cancellableSleep(400);
        }

        const totalFound = allItems.length;
        console.log(`%c[ChatGPT Exporter] Total conversations found: ${totalFound}`, "color: #10a37f; font-weight: bold; font-size: 13px;");

        // 3. Apply Offset / Resume Filter
        let targetItems = allItems;
        if (START_OFFSET > 0 && START_OFFSET < totalFound) {
            console.log(`%c[ChatGPT Exporter] Resuming from conversation #${START_OFFSET + 1} (skipping first ${START_OFFSET} chats)...`, "color: #0284c7; font-weight: bold;");
            targetItems = allItems.slice(START_OFFSET);
        }

        // Show floating on-screen widget
        overlay = createFloatingWidget(totalFound);

        const downloadedBatch = [];
        let consecutiveErrors = 0;
        let lastProcessedIndex = START_OFFSET;

        for (let i = 0; i < targetItems.length; i++) {
            if (isStopRequested) {
                console.log("%c[ChatGPT Exporter] Halting export loop per user request.", "color: #ef4444; font-weight: bold;");
                break;
            }

            const item = targetItems[i];
            const currentIndex = (START_OFFSET || 0) + i + 1;
            lastProcessedIndex = currentIndex;

            overlay.update(currentIndex, totalFound, item.title || "Untitled");
            console.log(`%c[ChatGPT Exporter] [${currentIndex}/${totalFound}] Fetching "${item.title || 'Untitled'}"...`, "color: #0284c7;");

            const detailUrl = `/backend-api/conversation/${item.id}`;
            const detailData = await fetchWithRetry(detailUrl, headers);

            if (detailData) {
                downloadedBatch.push(detailData);
                consecutiveErrors = 0;
            } else if (!isStopRequested) {
                consecutiveErrors++;
                if (consecutiveErrors >= 5) {
                    console.error("[ChatGPT Exporter] 5 consecutive failures. Pausing for 30s to be safe...");
                    await cancellableSleep(30000);
                }
            }

            if (isStopRequested) break;

            // Normal pacing delay
            await cancellableSleep(BASE_DELAY_MS);

            // Periodic rest pause every BATCH_REST_INTERVAL items
            if ((i + 1) % BATCH_REST_INTERVAL === 0 && (i + 1) < targetItems.length && !isStopRequested) {
                console.log(`%c[ChatGPT Exporter] Pacing: taking a short ${BATCH_REST_MS / 1000}s breather to respect rate limits...`, "color: #64748b; font-style: italic;");
                await cancellableSleep(BATCH_REST_MS);
            }
        }

        if (overlay) overlay.remove();

        if (downloadedBatch.length === 0) {
            alert("[ChatGPT Exporter] No conversations were downloaded.");
            return;
        }

        // 4. Save to Disk
        const dateTag = new Date().toISOString().slice(0, 10);
        const startNumber = (START_OFFSET || 0) + 1;
        const endNumber = (START_OFFSET || 0) + downloadedBatch.length;
        const isPartial = isStopRequested || (endNumber < totalFound);
        const fileSuffix = isPartial ? `part_${startNumber}_to_${endNumber}` : "complete";
        const filename = `chatgpt_chats_export_${dateTag}_${fileSuffix}.json`;

        downloadFile(JSON.stringify(downloadedBatch, null, 2), filename, "application/json");

        const nextResumeOffset = endNumber;

        console.log("%c" + "=".repeat(70), "color: #10a37f; font-weight: bold;");
        console.log(`%c[ChatGPT Exporter] SUCCESS! Saved ${downloadedBatch.length} conversation(s) to '${filename}'`, "color: #16a34a; font-weight: bold; font-size: 14px;");
        if (isPartial) {
            console.log(`%c[ChatGPT Exporter] TO RESUME NEXT TIME:`, "color: #0284c7; font-weight: bold; font-size: 13px;");
            console.log(`%c  Set line 25 of chatgpt_dump.js to: const START_OFFSET = ${nextResumeOffset};`, "color: #f59e0b; font-weight: bold; font-size: 13px;");
            console.log(`%c  Then run it again to pick up from conversation #${nextResumeOffset + 1}!`, "color: #0284c7;");
        }
        console.log("%c" + "=".repeat(70), "color: #10a37f; font-weight: bold;");

        const resumeMsg = isPartial 
            ? `\n\n📌 TO RESUME LATER:\nIn chatgpt_dump.js, set:\nconst START_OFFSET = ${nextResumeOffset};\n(This will resume from conversation #${nextResumeOffset + 1})`
            : "";

        alert(`Success! Saved ${downloadedBatch.length} conversations to '${filename}'.${resumeMsg}\n\nNext step:\nRun python ai_chat_export.py "${filename}" to convert to clean text/markdown.`);

    } catch (err) {
        if (overlay) overlay.remove();
        console.error("[ChatGPT Exporter] Error:", err);
        alert(`[ChatGPT Exporter] Error: ${err.message}`);
    }
})();
