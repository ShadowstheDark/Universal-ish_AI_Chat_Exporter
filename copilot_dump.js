/**
 * Microsoft Copilot Chat Exporter (Browser Console Script)
 * 
 * Works on:
 * - https://m365.cloud.microsoft/chat
 * - https://copilot.microsoft.com
 * 
 * Instructions:
 * 1. Open Edge or Chrome and navigate to your Copilot page (e.g. https://m365.cloud.microsoft/chat)
 * 2. Press F12 (or right-click -> Inspect) to open Developer Tools.
 * 3. Go to the "Console" tab.
 * 4. Paste this entire script and press Enter.
 * 5. It will automatically fetch all your chats, format them into a clean .txt file,
 *    and trigger a download of "copilot_chats_export.txt" and "copilot_chats_export.json".
 */

(async function () {
    console.log("%c[Copilot Exporter]%c Initializing exporter...", "color: #0078d4; font-weight: bold;", "color: inherit;");

    const APP_TAG = "[Copilot Exporter]";
    const FETCH_DELAY = 1200; // ms between requests to avoid rate limits
    const MAX_CHATS = 500;    // Maximum conversations to fetch

    // Helpers
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

    // Substrate API Calls
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

    // Formatters
    function formatToTxt(conversations) {
        let lines = [];
        lines.push("=" .repeat(80));
        lines.push("MICROSOFT COPILOT CHAT EXPORT");
        lines.push(`Exported on: ${new Date().toISOString()}`);
        lines.push(`Total Conversations: ${conversations.length}`);
        lines.push("=" .repeat(80));
        lines.push("\n");

        conversations.forEach((conv, idx) => {
            const title = conv.chatName || conv.title || "Untitled Conversation";
            const convId = conv.conversationId || conv.id || "N/A";
            const createTime = conv.createTimeUtc || conv.createdAt || conv.timestamp;
            let dateStr = "Unknown Date";
            if (createTime) {
                dateStr = new Date(typeof createTime === "number" && createTime < 1e11 ? createTime * 1000 : createTime).toISOString();
            }

            lines.push("#".repeat(80));
            lines.push(`CONVERSATION ${idx + 1}: ${title}`);
            lines.push(`Date: ${dateStr}`);
            lines.push(`ID:   ${convId}`);
            lines.push("#".repeat(80));
            lines.push("");

            const messages = conv.messages || [];
            messages.forEach(msg => {
                const author = (msg.author || "unknown").toLowerCase();
                const speaker = author === "user" ? "USER" : "COPILOT";
                const msgTime = msg.createdAt || msg.timestamp;
                const timeStr = msgTime ? ` (${new Date(msgTime).toISOString()})` : "";

                lines.push(`[${speaker}]${timeStr}:`);

                let body = msg.text || "";
                if (msg.adaptiveCards && msg.adaptiveCards.length > 0) {
                    try {
                        const cardText = msg.adaptiveCards[0].body?.[0]?.text;
                        if (cardText) body = cardText;
                    } catch (e) {}
                }
                lines.push(body.trim());

                if (msg.references && Object.keys(msg.references).length > 0) {
                    lines.push("\nSources:");
                    for (const [k, ref] of Object.entries(msg.references)) {
                        let refTitle = "";
                        try {
                            if (ref.displayData?.content) {
                                const parsed = JSON.parse(ref.displayData.content);
                                refTitle = parsed.Title || parsed.title || "";
                            }
                        } catch (e) {}
                        const link = ref.targetLink || "";
                        lines.push(refTitle ? `  [${k}] ${refTitle} - ${link}` : `  [${k}] ${link}`);
                    }
                }
                lines.push("\n" + "-".repeat(80) + "\n");
            });
            lines.push("\n");
        });

        return lines.join("\n");
    }

    function formatToMarkdown(conversations) {
        let md = [];
        md.push("# Microsoft Copilot Conversations Export\n");
        md.push(`*Exported on: ${new Date().toISOString()}*\n`);
        md.push(`*Total Conversations: ${conversations.length}*\n\n---\n`);

        conversations.forEach((conv, idx) => {
            const title = conv.chatName || conv.title || "Untitled Conversation";
            const createTime = conv.createTimeUtc || conv.createdAt || conv.timestamp;
            let dateStr = "Unknown Date";
            if (createTime) {
                dateStr = new Date(typeof createTime === "number" && createTime < 1e11 ? createTime * 1000 : createTime).toISOString();
            }

            md.push(`## ${idx + 1}. ${title}\n`);
            md.push(`**Date:** \`${dateStr}\` | **ID:** \`${conv.conversationId || "N/A"}\`\n`);

            const messages = conv.messages || [];
            messages.forEach(msg => {
                const author = (msg.author || "unknown").toLowerCase();
                const icon = author === "user" ? "👤 **You**" : "🤖 **Copilot**";
                md.push(`### ${icon}\n`);

                let body = msg.text || "";
                if (msg.adaptiveCards && msg.adaptiveCards.length > 0) {
                    try {
                        const cardText = msg.adaptiveCards[0].body?.[0]?.text;
                        if (cardText) body = cardText;
                    } catch (e) {}
                }
                md.push(body.trim() + "\n");

                if (msg.references && Object.keys(msg.references).length > 0) {
                    md.push("\n**Sources:**");
                    for (const [k, ref] of Object.entries(msg.references)) {
                        let refTitle = "Source";
                        try {
                            if (ref.displayData?.content) {
                                const parsed = JSON.parse(ref.displayData.content);
                                refTitle = parsed.Title || parsed.title || "Source";
                            }
                        } catch (e) {}
                        md.push(`- [${refTitle}](${ref.targetLink || "#"})`);
                    }
                    md.push("\n");
                }
            });
            md.push("\n---\n");
        });

        return md.join("\n");
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

    // DOM Fallback Scraper for active conversation
    function scrapeActiveChatFromDOM() {
        console.log(`${APP_TAG} Attempting DOM scrape of active conversation...`);
        const messages = [];
        
        // Common message container selectors across Copilot web variants
        const turns = document.querySelectorAll(
            'cib-chat-turn, [data-content="user-message"], [data-content="ai-message"], div[class*="message-bubble"], div[class*="chat-message"]'
        );

        if (turns.length > 0) {
            turns.forEach(el => {
                const isUser = el.getAttribute("data-content") === "user-message" ||
                               el.className.includes("user") ||
                               el.querySelector('[data-author="user"]');
                messages.push({
                    author: isUser ? "user" : "bot",
                    text: el.innerText || "",
                    timestamp: new Date().toISOString()
                });
            });
        } else {
            // General fallback: grab paragraphs and code blocks
            const mainContainer = document.querySelector('main, #chat-container, [role="main"]') || document.body;
            messages.push({
                author: "system",
                text: mainContainer.innerText,
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

    // Main Execution Flow
    try {
        let conversations = [];
        const msalIds = getMsalIds();

        if (msalIds) {
            console.log(`${APP_TAG} Found MSAL identity. Fetching access token...`);
            const token = await getAccessToken(msalIds);

            if (token) {
                console.log(`${APP_TAG} Access token obtained! Querying Substrate API for chat list...`);
                const listResp = await fetchCopilotChatsList(token, msalIds.localAccountId, msalIds.tenantId, MAX_CHATS);
                const chatList = listResp.chats || [];
                console.log(`${APP_TAG} Found ${chatList.length} conversations in your corporate account.`);

                for (let i = 0; i < chatList.length; i++) {
                    const c = chatList[i];
                    console.log(`%c${APP_TAG} Fetching conversation ${i + 1}/${chatList.length}: "${c.chatName}"...`, "color: #0078d4;");
                    try {
                        const fullConv = await fetchCopilotConversation(token, msalIds.localAccountId, msalIds.tenantId, c.conversationId);
                        conversations.push(fullConv);
                    } catch (err) {
                        console.warn(`${APP_TAG} Could not fetch ${c.conversationId}:`, err);
                    }
                    await sleep(FETCH_DELAY);
                }
            } else {
                console.warn(`${APP_TAG} Could not retrieve token. Falling back to active chat DOM scrape.`);
            }
        }

        if (conversations.length === 0) {
            conversations = scrapeActiveChatFromDOM();
        }

        if (conversations.length === 0) {
            alert(`${APP_TAG} No conversations found. Please ensure you are logged into https://m365.cloud.microsoft/chat and have chats open.`);
            return;
        }

        console.log(`%c${APP_TAG} SUCCESS! Exporting ${conversations.length} conversation(s)...`, "color: green; font-weight: bold; font-size: 14px;");

        // Format to Text and Markdown
        const txtOutput = formatToTxt(conversations);
        const mdOutput = formatToMarkdown(conversations);
        const jsonOutput = JSON.stringify(conversations, null, 2);

        // Download files
        const timestamp = new Date().toISOString().slice(0, 10);
        downloadFile(txtOutput, `copilot_chats_${timestamp}.txt`, "text/plain");
        downloadFile(mdOutput, `copilot_chats_${timestamp}.md`, "text/markdown");
        downloadFile(jsonOutput, `copilot_chats_${timestamp}.json`, "application/json");

        // Attempt sending to local Python receiver if running
        try {
            await fetch("http://127.0.0.1:8765/upload", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: jsonOutput
            });
            console.log(`${APP_TAG} Successfully synced with local Python script!`);
        } catch (e) {
            // Local Python script wasn't listening, totally fine since file downloaded
        }

        alert(`Success! Exported ${conversations.length} conversation(s) to copilot_chats_${timestamp}.txt, .md, and .json.`);

    } catch (error) {
        console.error(`${APP_TAG} Error:`, error);
        alert(`${APP_TAG} Error exporting chats: ${error.message}`);
    }
})();
