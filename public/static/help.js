const questionInputEl = document.getElementById("questionInput");
const sendButtonEl = document.getElementById("sendButton");
const newConversationButtonEl = document.getElementById("newConversationButton");
const chatHistoryEl = document.getElementById("chatHistory");
const typingIndicatorEl = document.getElementById("typingIndicator");
const toastEl = document.getElementById("toast");
const uploadZoneEl = document.getElementById("uploadZone");
const uploadButtonEl = document.getElementById("uploadButton");
const fileInputEl = document.getElementById("fileInput");
const filePreviewListEl = document.getElementById("filePreviewList");
const contextBannerEl = document.getElementById("contextBanner");
const contextBannerTextEl = document.getElementById("contextBannerText");
const dismissContextButtonEl = document.getElementById("dismissContextButton");

const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024;
const ACCEPTED_MEDIA_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
  "application/pdf",
]);

let attachments = [];
let conversationHistory = [];
let isStreaming = false;
let contextInjected = false;
let contextValue = "";

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showToast(message) {
  toastEl.textContent = message;
  toastEl.classList.remove("show");
  void toastEl.offsetWidth;
  toastEl.classList.add("show");
}

function renderInlineMarkdown(raw) {
  const source = String(raw || "");
  const codeStore = [];
  let html = escapeHtml(source).replace(/```([\s\S]*?)```/g, (_, block) => {
    const token = `__CODE_BLOCK_${codeStore.length}__`;
    codeStore.push(
      `<pre class="md-code"><code>${block.replace(/^\n+|\n+$/g, "")}</code></pre>`
    );
    return token;
  });

  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  const lines = html.split("\n");
  let inList = false;
  const output = [];
  for (const line of lines) {
    if (/^\s*[-*]\s+/.test(line)) {
      if (!inList) {
        output.push("<ul>");
        inList = true;
      }
      output.push(`<li>${line.replace(/^\s*[-*]\s+/, "")}</li>`);
      continue;
    }
    if (inList) {
      output.push("</ul>");
      inList = false;
    }
    if (!line.trim()) {
      output.push("<br>");
    } else {
      output.push(`<p>${line}</p>`);
    }
  }
  if (inList) {
    output.push("</ul>");
  }

  html = output.join("");
  codeStore.forEach((code, index) => {
    html = html.replace(`__CODE_BLOCK_${index}__`, code);
  });
  return html;
}

function setStreamingState(active) {
  isStreaming = active;
  sendButtonEl.disabled = active;
  questionInputEl.disabled = active;
  fileInputEl.disabled = active;
  uploadButtonEl.disabled = active;
  typingIndicatorEl.hidden = !active;
}

function clearAttachments() {
  attachments = [];
  fileInputEl.value = "";
  filePreviewListEl.innerHTML = "";
}

function renderFilePreviews() {
  if (!attachments.length) {
    filePreviewListEl.innerHTML = "";
    return;
  }

  filePreviewListEl.innerHTML = attachments
    .map((item) => {
      const isImage = item.media_type.startsWith("image/");
      return `
        <article class="file-pill">
          ${
            isImage
              ? `<img src="data:${item.media_type};base64,${item.data}" alt="${escapeHtml(item.name)}" class="file-thumb" />`
              : `<span class="file-pdf">PDF</span>`
          }
          <div class="file-meta">
            <p class="file-name">${escapeHtml(item.name)}</p>
            <p class="file-type">${escapeHtml(item.media_type)}</p>
          </div>
          <button class="file-remove" type="button" data-file-id="${item.id}" aria-label="Remove ${escapeHtml(item.name)}">✕</button>
        </article>
      `;
    })
    .join("");
}

function removeAttachmentById(id) {
  attachments = attachments.filter((file) => file.id !== id);
  renderFilePreviews();
}

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || "");
      const base64 = raw.includes(",") ? raw.split(",")[1] : raw;
      resolve(base64);
    };
    reader.onerror = () => reject(reader.error || new Error("Read failed"));
    reader.readAsDataURL(file);
  });
}

async function addFiles(files) {
  for (const file of files) {
    if (!ACCEPTED_MEDIA_TYPES.has(file.type)) {
      showToast(`Unsupported file type: ${file.name}`);
      continue;
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      showToast(`File too large: ${file.name}`);
      continue;
    }
    try {
      const base64 = await readAsBase64(file);
      attachments.push({
        id: crypto.randomUUID(),
        type: file.type.startsWith("image/") ? "image" : "pdf",
        media_type: file.type,
        data: base64,
        name: file.name,
      });
    } catch {
      showToast(`Failed to read: ${file.name}`);
    }
  }
  renderFilePreviews();
}

function appendMessage(role, text) {
  const emptyState = document.getElementById("chatEmptyState");
  if (emptyState) {
    emptyState.remove();
  }
  const wrapper = document.createElement("article");
  wrapper.className = `chat-bubble ${role === "assistant" ? "assistant" : "user"}`;
  wrapper.innerHTML = `<div class="chat-role">${role === "assistant" ? "The Scriptor" : "You"}</div><div class="chat-content">${renderInlineMarkdown(text)}</div>`;
  chatHistoryEl.appendChild(wrapper);
  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  return wrapper.querySelector(".chat-content");
}

function resetConversation() {
  conversationHistory = [];
  chatHistoryEl.innerHTML =
    '<div id="chatEmptyState" class="chat-empty-state">Upload a worksheet or ask anything</div>';
  // After an explicit reset, do not prepend ?context= again (that was causing
  // "memory" of the old assignment on the next send). URL context applies only
  // to the first message of the initial visit, not after New Conversation.
  contextInjected = true;
  clearAttachments();
  questionInputEl.value = "";
  showToast("Started a new conversation");
}

function parseSseChunk(rawChunk) {
  return rawChunk
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
}

function maybeInjectContext(userText) {
  if (!contextValue || contextInjected) {
    return userText;
  }
  contextInjected = true;
  return `Homework context (for the tutor):\n\n${contextValue}\n\nStudent question: ${userText}`;
}

async function sendMessage() {
  if (isStreaming) {
    return;
  }

  const question = questionInputEl.value.trim();
  if (!question) {
    showToast("Type a question first");
    return;
  }

  const outbound = maybeInjectContext(question);
  conversationHistory.push({ role: "user", content: outbound });
  appendMessage("user", question);
  questionInputEl.value = "";

  const assistantContentEl = appendMessage("assistant", "");
  let assistantText = "";
  setStreamingState(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: conversationHistory,
        attachments,
      }),
    });

    if (!response.ok || !response.body) {
      let message = "Request failed";
      try {
        const payload = await response.json();
        message = payload.error || message;
      } catch {
        // Ignore JSON parse failures here.
      }
      throw new Error(message);
    }

    clearAttachments();

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let streamDone = false;

    while (!streamDone) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";
      for (const rawChunk of chunks) {
        const payload = parseSseChunk(rawChunk);
        if (!payload) {
          continue;
        }
        if (payload === "[DONE]") {
          streamDone = true;
          break;
        }
        assistantText += payload;
        assistantContentEl.innerHTML = renderInlineMarkdown(assistantText);
        chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
      }
    }

    conversationHistory.push({ role: "assistant", content: assistantText });
  } catch (error) {
    assistantContentEl.textContent =
      error instanceof Error ? error.message : "Something went wrong";
    showToast("Unable to get response");
  } finally {
    setStreamingState(false);
  }
}

function initContextBanner() {
  const params = new URLSearchParams(window.location.search);
  const focus = (params.get("context") || "").trim();
  const subject = (params.get("subject") || "").trim();
  let others = [];
  const othersRaw = params.get("others");
  if (othersRaw) {
    try {
      const parsed = JSON.parse(othersRaw);
      if (Array.isArray(parsed)) {
        others = parsed;
      }
    } catch {
      others = [];
    }
  }
  if (!focus && !subject) {
    return;
  }
  const lines = [];
  if (subject) {
    lines.push(`Subject: ${subject}`);
  }
  lines.push("Primary assignment (help the student with this one):");
  if (focus) {
    lines.push(focus);
  } else {
    lines.push("(see subject context)");
  }
  if (others.length) {
    lines.push("");
    lines.push(
      "Other assignments in this same subject (for background only; the student's question is about the primary assignment unless they explicitly refer to these):"
    );
    for (const o of others) {
      const due = (o.due_label || o.due_date || "").toString().trim() || "Unknown";
      const desc = (o.description || "").trim() || "—";
      lines.push(`- [${due}] ${desc}`);
    }
  }
  contextValue = lines.join("\n");
  const display =
    subject && focus
      ? `${subject} — ${
          focus.length > 90 ? `${focus.slice(0, 90)}…` : focus
        }`
      : focus || subject;
  contextBannerTextEl.textContent = display;
  contextBannerEl.hidden = false;
}

uploadButtonEl.addEventListener("click", () => fileInputEl.click());

fileInputEl.addEventListener("change", async (event) => {
  await addFiles(event.target.files || []);
});

uploadZoneEl.addEventListener("dragover", (event) => {
  event.preventDefault();
  uploadZoneEl.classList.add("is-dragover");
});

uploadZoneEl.addEventListener("dragleave", () => {
  uploadZoneEl.classList.remove("is-dragover");
});

uploadZoneEl.addEventListener("drop", async (event) => {
  event.preventDefault();
  uploadZoneEl.classList.remove("is-dragover");
  await addFiles(event.dataTransfer?.files || []);
});

filePreviewListEl.addEventListener("click", (event) => {
  const button = event.target.closest(".file-remove");
  if (!button) {
    return;
  }
  removeAttachmentById(button.dataset.fileId);
});

dismissContextButtonEl.addEventListener("click", () => {
  contextBannerEl.hidden = true;
  contextValue = "";
  contextInjected = true;
});

questionInputEl.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    sendMessage();
  }
});

sendButtonEl.addEventListener("click", sendMessage);
newConversationButtonEl.addEventListener("click", resetConversation);

initContextBanner();
