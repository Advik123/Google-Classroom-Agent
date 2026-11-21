const dashboardEl = document.getElementById("dashboard");
const updatedAtEl = document.getElementById("updatedAt");
const refreshButtonEl = document.getElementById("refreshButton");
const toastEl = document.getElementById("toast");

const AUTO_REFRESH_MS = 5 * 60 * 1000;
const STORAGE_KEY = "homework-dashboard-completion-v1";
const SECTION_TOGGLE_KEY = "homework-dashboard-section-show-completed-v1";

let lastEntries = [];
let sectionShowCompleted = loadSectionToggles();

function loadCompletionState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { done: new Set(), undone: new Set() };
    }
    const parsed = JSON.parse(raw);
    return {
      done: new Set(parsed.done || []),
      undone: new Set(parsed.undone || []),
    };
  } catch {
    return { done: new Set(), undone: new Set() };
  }
}

function saveCompletionState(state) {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      done: [...state.done],
      undone: [...state.undone],
    })
  );
}

function pruneCompletionState(entries) {
  const valid = new Set(entries.map(entryId));
  completionState.done = new Set(
    [...completionState.done].filter((id) => valid.has(id))
  );
  completionState.undone = new Set(
    [...completionState.undone].filter((id) => valid.has(id))
  );
  saveCompletionState(completionState);
}

let completionState = loadCompletionState();

function loadSectionToggles() {
  try {
    const raw = localStorage.getItem(SECTION_TOGGLE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveSectionToggles(obj) {
  localStorage.setItem(SECTION_TOGGLE_KEY, JSON.stringify(obj));
}

function pruneSectionToggles(entries) {
  const keys = new Set();
  entries.forEach((e) => {
    keys.add((e.subject || "other").trim().toLowerCase() || "other");
  });
  const next = {};
  Object.keys(sectionShowCompleted).forEach((k) => {
    if (keys.has(k)) {
      next[k] = sectionShowCompleted[k];
    }
  });
  sectionShowCompleted = next;
  saveSectionToggles(sectionShowCompleted);
}

function isSectionShowingCompleted(sectionKey) {
  return Boolean(sectionShowCompleted[sectionKey]);
}

function entryId(entry) {
  return [entry.due_date || "", entry.subject || "", entry.description || ""]
    .join("|")
    .replace(/\s+/g, " ")
    .trim();
}

function effectiveCompleted(entry) {
  const id = entryId(entry);
  if (completionState.undone.has(id)) {
    return false;
  }
  if (completionState.done.has(id)) {
    return true;
  }
  return Boolean(entry.completed);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function startOfToday() {
  const t = new Date();
  t.setHours(0, 0, 0, 0);
  return t;
}

function parseDueDate(iso) {
  if (!iso) {
    return null;
  }
  const d = new Date(`${iso}T12:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function urgencyKey(entry) {
  const due = parseDueDate(entry.due_date);
  const today = startOfToday();
  if (!due) {
    return [2, 0];
  }
  due.setHours(0, 0, 0, 0);
  if (due < today) {
    return [0, -due.getTime()];
  }
  return [1, due.getTime()];
}

function compareEntries(a, b) {
  const sub = (e) => (e.subject || "").toLowerCase();
  const sc = sub(a).localeCompare(sub(b));
  if (sc !== 0) {
    return sc;
  }
  const ca = effectiveCompleted(a) ? 1 : 0;
  const cb = effectiveCompleted(b) ? 1 : 0;
  if (ca !== cb) {
    return ca - cb;
  }
  const ua = urgencyKey(a);
  const ub = urgencyKey(b);
  if (ua[0] !== ub[0]) {
    return ua[0] - ub[0];
  }
  return ua[1] - ub[1];
}

function sortEntriesWithLocalState(entries) {
  return [...entries].sort(compareEntries);
}

function displayDueLabel(entry) {
  if (effectiveCompleted(entry)) {
    const due = parseDueDate(entry.due_date);
    if (!due) {
      return "Done";
    }
    return `Done · ${due.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    })}`;
  }
  return entry.due_label || "";
}

function formatDateStamp(input) {
  const parsed = new Date(input);
  if (Number.isNaN(parsed.getTime())) {
    return "--";
  }
  return parsed.toLocaleString();
}

function classSectionTitle(entry) {
  return (entry.subject || "Other").trim() || "Other";
}

function showToast(message) {
  toastEl.textContent = message;
  toastEl.classList.remove("show");
  void toastEl.offsetWidth;
  toastEl.classList.add("show");
}

function groupEntries(entries) {
  const groups = [];
  const map = new Map();
  entries.forEach((entry) => {
    const key = (entry.subject || "other").trim().toLowerCase() || "other";
    if (!map.has(key)) {
      const section = { key, title: classSectionTitle(entry), items: [] };
      map.set(key, section);
      groups.push(section);
    }
    map.get(key).items.push(entry);
  });
  return groups;
}

function renderEmptyState() {
  dashboardEl.innerHTML = '<section class="empty">All clear ✓</section>';
}

function renderEntries(entries) {
  if (!entries.length) {
    renderEmptyState();
    return;
  }

  const sorted = sortEntriesWithLocalState(entries);
  const groups = groupEntries(sorted);
  const sections = groups
    .map((group) => {
      const showCompleted = isSectionShowingCompleted(group.key);
      const visibleItems = showCompleted
        ? group.items
        : group.items.filter((e) => !effectiveCompleted(e));
      const allComplete =
        group.items.length > 0 &&
        group.items.every((e) => effectiveCompleted(e));
      const showNoHomework = visibleItems.length === 0 && allComplete;

      const headerRow = `
        <div class="date-header-row">
          <h2 class="date-header">${escapeHtml(group.title)}</h2>
          <label class="section-show-completed">
            <input
              type="checkbox"
              class="section-toggle-completed"
              data-section-key="${escapeHtml(group.key)}"
              ${showCompleted ? "checked" : ""}
            />
            <span class="section-toggle-visual" aria-hidden="true">
              <span class="section-toggle-thumb"></span>
            </span>
            <span class="section-toggle-text">
              <span class="section-toggle-title">Completed</span>
              <span class="section-toggle-sub">reveal in list</span>
            </span>
          </label>
        </div>
      `;

      if (showNoHomework) {
        return `
        <section class="date-section">
          ${headerRow}
          <p class="section-no-homework">no homework</p>
        </section>
      `;
      }

      const cards = visibleItems
        .map((entry, index) => {
          const done = effectiveCompleted(entry);
          const overdueClass =
            !done &&
            String(entry.due_label || "").toLowerCase() === "overdue"
              ? " overdue"
              : "";
          const completedClass = done ? " completed" : "";
          const delay = `${index * 70}ms`;
          const subject = entry.subject || "Other";
          const description = entry.description || "";
          const dueLabel = displayDueLabel(entry);
          const color = entry.subject_color || "#8B8B93";
          const currentId = entryId(entry);
          const otherInSubject = group.items
            .filter((e) => entryId(e) !== currentId)
            .map((e) => ({
              due_label: displayDueLabel(e),
              due_date: e.due_date || "",
              description: (e.description || "").trim().slice(0, 500),
            }))
            .slice(0, 25);
          const helpParams = new URLSearchParams();
          helpParams.set("context", description);
          helpParams.set("subject", subject);
          if (otherInSubject.length) {
            helpParams.set("others", JSON.stringify(otherInSubject));
          }
          const helpHref = `/help?${helpParams.toString()}`;
          const id = currentId;
          const idAttr = encodeURIComponent(id);
          return `
            <article class="card${overdueClass}${completedClass}" style="animation-delay:${delay}">
              <div class="card-head">
                <span class="subject-pill" style="--subject-color:${color}">${escapeHtml(subject)}</span>
                <label class="card-complete-label">
                  <input type="checkbox" class="card-complete" data-entry-id="${idAttr}" ${done ? "checked" : ""} />
                  <span>Done</span>
                </label>
              </div>
              <p class="description">${escapeHtml(description)}</p>
              <div class="card-footer">
                <a class="help-link" href="${helpHref}">Get Help →</a>
                <p class="due-label">${escapeHtml(dueLabel)}</p>
              </div>
            </article>
          `;
        })
        .join("");

      return `
        <section class="date-section">
          ${headerRow}
          <div class="cards-grid">${cards}</div>
        </section>
      `;
    })
    .join("");

  dashboardEl.innerHTML = sections;
}

dashboardEl.addEventListener("change", (e) => {
  const input = e.target;
  if (input.classList.contains("section-toggle-completed")) {
    const key = input.dataset.sectionKey || "";
    if (key) {
      sectionShowCompleted[key] = input.checked;
      saveSectionToggles(sectionShowCompleted);
      renderEntries(lastEntries);
    }
    return;
  }
  if (!input.classList.contains("card-complete")) {
    return;
  }
  const id = decodeURIComponent(input.dataset.entryId || "");
  const entry = lastEntries.find((item) => entryId(item) === id);
  const checked = input.checked;

  if (checked) {
    completionState.done.add(id);
    completionState.undone.delete(id);
  } else {
    completionState.done.delete(id);
    if (entry && entry.completed) {
      completionState.undone.add(id);
    }
  }
  saveCompletionState(completionState);
  renderEntries(lastEntries);
});

async function fetchHomework({ showAutoToast = false } = {}) {
  refreshButtonEl.classList.add("spinning");
  try {
    const response = await fetch("/api/homework", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    lastEntries = payload.entries || [];
    pruneCompletionState(lastEntries);
    pruneSectionToggles(lastEntries);
    renderEntries(lastEntries);
    updatedAtEl.textContent = `Last updated: ${formatDateStamp(payload.updated_at)}`;

    if (showAutoToast) {
      showToast("Updated just now");
    }
  } catch (error) {
    showToast("Update failed");
    console.error(error);
  } finally {
    refreshButtonEl.classList.remove("spinning");
  }
}

refreshButtonEl.addEventListener("click", () => {
  fetchHomework({ showAutoToast: true });
});

fetchHomework();
setInterval(() => {
  fetchHomework({ showAutoToast: true });
}, AUTO_REFRESH_MS);
