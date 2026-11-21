(function () {
  const state = {
    inputMode: "file",
    sourceType: "file",
    currentSource: "",
    generated: { flashcards: [], quiz: [] },
    flashcards: {
      items: [],
      index: 0,
      flipped: false,
      knownSet: new Set(),
      learningSet: new Set(),
      saved: false,
    },
    quiz: {
      items: [],
      originalItems: [],
      index: 0,
      score: 0,
      wrongItems: [],
      answered: false,
      saved: false,
    },
    historyOpen: true,
    historySessions: [],
    selectedMode: "both",
  };

  const els = {
    tabs: Array.from(document.querySelectorAll(".study-tab")),
    panels: {
      upload: document.getElementById("uploadSection"),
      flashcards: document.getElementById("flashcardsSection"),
      quiz: document.getElementById("quizSection"),
    },
    historyPanel: document.getElementById("historyPanel"),
    historyToggle: document.getElementById("historyToggle"),
    historyList: document.getElementById("historyList"),
    progressBar: document.getElementById("studyProgressBar"),
    inputModeButtons: Array.from(document.querySelectorAll(".input-mode-btn")),
    fileModePanel: document.getElementById("fileModePanel"),
    textModePanel: document.getElementById("textModePanel"),
    fileInput: document.getElementById("studyFileInput"),
    fileButton: document.getElementById("studyFileButton"),
    uploadZone: document.getElementById("studyUploadZone"),
    selectedFileName: document.getElementById("selectedFileName"),
    topicInput: document.getElementById("topicInput"),
    topicCounter: document.getElementById("topicCounter"),
    flashModeToggle: document.getElementById("flashcardsModeToggle"),
    quizModeToggle: document.getElementById("quizModeToggle"),
    generateButton: document.getElementById("generateButton"),
    loadingWrap: document.getElementById("studyLoading"),
    loadingText: document.getElementById("studyLoadingText"),
    flashcardCard: document.getElementById("flashcardCard"),
    flashFrontText: document.getElementById("flashFrontText"),
    flashBackText: document.getElementById("flashBackText"),
    flashCounter: document.getElementById("flashCounter"),
    flashPrevButton: document.getElementById("flashPrevButton"),
    flashNextButton: document.getElementById("flashNextButton"),
    markKnownButton: document.getElementById("markKnownButton"),
    markLearningButton: document.getElementById("markLearningButton"),
    flashSummary: document.getElementById("flashSummary"),
    flashStage: document.getElementById("flashcardStage"),
    quizCounter: document.getElementById("quizCounter"),
    quizQuestion: document.getElementById("quizQuestion"),
    quizOptions: document.getElementById("quizOptions"),
    quizNextButton: document.getElementById("quizNextButton"),
    quizSummary: document.getElementById("quizSummary"),
    quizStage: document.getElementById("quizStage"),
    quizExplanation: document.getElementById("quizExplanation"),
    quizExplanationText: document.getElementById("quizExplanationText"),
  };

  function truncate(text, max = 40) {
    const value = String(text || "");
    if (value.length <= max) return value;
    return `${value.slice(0, max - 3)}...`;
  }

  function activeTabName() {
    const active = document.querySelector(".study-tab.is-active");
    return active ? active.dataset.tab : "upload";
  }

  function setActiveTab(tabName) {
    els.tabs.forEach((tab) => tab.classList.toggle("is-active", tab.dataset.tab === tabName));
    Object.entries(els.panels).forEach(([name, panel]) => {
      panel.classList.toggle("is-active", name === tabName);
    });
  }

  function getSelectedMode() {
    const wantsFlashcards = els.flashModeToggle.classList.contains("is-active");
    const wantsQuiz = els.quizModeToggle.classList.contains("is-active");
    if (wantsFlashcards && wantsQuiz) return "both";
    if (wantsFlashcards) return "flashcards";
    if (wantsQuiz) return "quiz";
    return "";
  }

  function setInputMode(mode) {
    state.inputMode = mode;
    els.inputModeButtons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.inputMode === mode);
    });
    els.fileModePanel.classList.toggle("is-active", mode === "file");
    els.textModePanel.classList.toggle("is-active", mode === "text");
  }

  function renderUploadSelection() {
    const file = els.fileInput.files && els.fileInput.files[0];
    els.selectedFileName.textContent = file ? `${file.name} (${Math.round(file.size / 1024)} KB)` : "";
  }

  function setLoading(isLoading, type) {
    els.loadingWrap.hidden = !isLoading;
    els.generateButton.disabled = isLoading;
    if (!isLoading) return;
    if (type === "file") {
      els.loadingText.textContent = "Extracting study content...";
    } else {
      els.loadingText.textContent = "Generating study content...";
    }
  }

  function updateProgress(current, total) {
    const percent = total > 0 ? (current / total) * 100 : 0;
    els.progressBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  }

  async function saveProgress(payload) {
    try {
      await fetch("/api/save-progress", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await loadHistory();
    } catch (err) {
      console.error("Failed to save progress", err);
    }
  }

  function renderFlashcard() {
    const cards = state.flashcards.items;
    const index = state.flashcards.index;
    if (!cards.length) {
      els.flashFrontText.textContent = "No flashcards yet";
      els.flashBackText.textContent = "Generate study material to begin.";
      els.flashCounter.textContent = "0 / 0";
      updateProgress(0, 0);
      return;
    }
    const card = cards[index];
    els.flashFrontText.textContent = card.front;
    els.flashBackText.textContent = card.back;
    els.flashCounter.textContent = `${index + 1} / ${cards.length}`;
    els.flashcardCard.classList.toggle("flipped", state.flashcards.flipped);
    updateProgress(state.flashcards.knownSet.size, cards.length);
  }

  function showFlashSummary() {
    const total = state.flashcards.items.length;
    const known = state.flashcards.knownSet.size;
    const learningCards = Array.from(state.flashcards.learningSet).map((idx) => state.flashcards.items[idx]);
    els.flashStage.hidden = true;
    els.flashSummary.hidden = false;
    els.flashSummary.innerHTML = `
      <h2 class="score-percentage">${total ? Math.round((known / total) * 100) : 0}%</h2>
      <p>Known: ${known} / ${total}</p>
      <p>Still learning: ${learningCards.length}</p>
      <button id="flashRestartButton" class="summary-action-btn" type="button">Restart</button>
    `;
    document.getElementById("flashRestartButton").addEventListener("click", () => {
      startFlashcards(state.generated.flashcards || []);
    });
    if (!state.flashcards.saved && total > 0 && state.currentSource) {
      state.flashcards.saved = true;
      saveProgress({
        session_id: crypto.randomUUID(),
        type: "flashcards",
        source: state.currentSource,
        date: new Date().toISOString(),
        score: known,
        total,
        wrong_items: learningCards,
      });
    }
  }

  function startFlashcards(items) {
    state.flashcards = {
      items: Array.isArray(items) ? items : [],
      index: 0,
      flipped: false,
      knownSet: new Set(),
      learningSet: new Set(),
      saved: false,
    };
    els.flashStage.hidden = false;
    els.flashSummary.hidden = true;
    renderFlashcard();
  }

  function markFlashcard(isKnown) {
    if (!state.flashcards.items.length) return;
    const idx = state.flashcards.index;
    if (isKnown) {
      state.flashcards.knownSet.add(idx);
      state.flashcards.learningSet.delete(idx);
    } else {
      state.flashcards.learningSet.add(idx);
      state.flashcards.knownSet.delete(idx);
    }
    renderFlashcard();
  }

  function nextFlashcard() {
    if (!state.flashcards.items.length) return;
    if (state.flashcards.index >= state.flashcards.items.length - 1) {
      showFlashSummary();
      return;
    }
    state.flashcards.index += 1;
    state.flashcards.flipped = false;
    renderFlashcard();
  }

  function prevFlashcard() {
    if (!state.flashcards.items.length || state.flashcards.index <= 0) return;
    state.flashcards.index -= 1;
    state.flashcards.flipped = false;
    renderFlashcard();
  }

  function renderQuizQuestion() {
    const quiz = state.quiz.items;
    const idx = state.quiz.index;
    if (!quiz.length) {
      els.quizCounter.textContent = "0 / 0";
      els.quizQuestion.textContent = "Generate a quiz to begin.";
      els.quizOptions.innerHTML = "";
      els.quizNextButton.hidden = true;
      els.quizExplanation.hidden = true;
      els.quizExplanationText.textContent = "";
      els.quizExplanation.classList.remove("is-loading");
      updateProgress(0, 0);
      return;
    }

    const current = quiz[idx];
    state.quiz.answered = false;
    els.quizNextButton.hidden = true;
    els.quizExplanation.hidden = true;
    els.quizExplanationText.textContent = "";
    els.quizExplanation.classList.remove("is-loading");
    els.quizCounter.textContent = `${idx + 1} / ${quiz.length}`;
    els.quizQuestion.textContent = current.question;
    updateProgress(idx, quiz.length);
    const options = current.type === "true_false" ? ["True", "False"] : current.options;
    els.quizOptions.innerHTML = "";
    options.forEach((option, optionIndex) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "quiz-option-btn";
      btn.dataset.optionIndex = String(optionIndex);
      btn.textContent = option;
      btn.addEventListener("click", () => handleQuizAnswer(option, btn));
      els.quizOptions.appendChild(btn);
    });
  }

  function finalizeQuiz() {
    const total = state.quiz.items.length;
    const percent = total ? Math.round((state.quiz.score / total) * 100) : 0;
    updateProgress(total, total);
    els.quizStage.hidden = true;
    els.quizSummary.hidden = false;
    const wrongMarkup = state.quiz.wrongItems
      .map(
        (item) => `
          <div class="wrong-item">
            <strong>${item.question}</strong>
            <p>Correct answer: ${item.answer}</p>
          </div>
        `,
      )
      .join("");
    els.quizSummary.innerHTML = `
      <h2 class="score-percentage">${percent}%</h2>
      <p>Score: ${state.quiz.score} / ${total}</p>
      <div class="wrong-items-list">${wrongMarkup || "<p>No wrong answers.</p>"}</div>
      <div class="summary-actions">
        <button id="retryWrongButton" class="summary-action-btn" type="button">Retry Wrong</button>
        <button id="startOverQuizButton" class="summary-action-btn" type="button">Start Over</button>
      </div>
    `;

    const retryButton = document.getElementById("retryWrongButton");
    retryButton.disabled = state.quiz.wrongItems.length === 0;
    retryButton.addEventListener("click", () => {
      startQuiz(state.quiz.wrongItems);
    });
    document.getElementById("startOverQuizButton").addEventListener("click", () => {
      startQuiz(state.generated.quiz || []);
    });

    if (!state.quiz.saved && total > 0 && state.currentSource) {
      state.quiz.saved = true;
      saveProgress({
        session_id: crypto.randomUUID(),
        type: "quiz",
        source: state.currentSource,
        date: new Date().toISOString(),
        score: state.quiz.score,
        total,
        wrong_items: state.quiz.wrongItems,
      });
    }
  }

  function handleQuizAnswer(selectedText, selectedButton) {
    if (state.quiz.answered) return;
    const current = state.quiz.items[state.quiz.index];
    state.quiz.answered = true;
    const gotItRight = selectedText === current.answer;
    const optionButtons = Array.from(els.quizOptions.querySelectorAll(".quiz-option-btn"));
    optionButtons.forEach((button) => {
      button.disabled = true;
      const optionText = button.textContent || "";
      if (optionText === current.answer) {
        button.classList.add("correct");
      }
    });
    if (!gotItRight) {
      selectedButton.classList.add("wrong");
      state.quiz.wrongItems.push(current);
    } else {
      state.quiz.score += 1;
    }
    els.quizNextButton.hidden = false;

    const base = String(current.explanation || "").trim();
    els.quizExplanation.hidden = false;
    els.quizExplanation.classList.remove("is-loading");
    if (gotItRight) {
      els.quizExplanationText.textContent = base
        ? `Correct. ${base}`
        : "That choice matches what the question is asking for — well done.";
    } else {
      els.quizExplanationText.textContent = base
        ? `You chose “${selectedText}”. The correct answer is “${current.answer}”. ${base}`
        : `The correct answer is “${current.answer}.” Compare each option to the question’s wording to see which one fits best.`;
    }
  }

  function nextQuizQuestion() {
    if (!state.quiz.items.length) return;
    if (state.quiz.index >= state.quiz.items.length - 1) {
      finalizeQuiz();
      return;
    }
    state.quiz.index += 1;
    renderQuizQuestion();
  }

  function startQuiz(items) {
    const validItems = Array.isArray(items) ? items : [];
    state.quiz = {
      items: validItems.slice(),
      originalItems: validItems.slice(),
      index: 0,
      score: 0,
      wrongItems: [],
      answered: false,
      saved: false,
    };
    els.quizStage.hidden = false;
    els.quizSummary.hidden = true;
    renderQuizQuestion();
  }

  function renderHistorySessions() {
    const sessions = [...state.historySessions].reverse();
    if (!sessions.length) {
      els.historyList.innerHTML = "<p class='history-meta'>No sessions yet.</p>";
      return;
    }
    els.historyList.innerHTML = "";
    sessions.forEach((session) => {
      const row = document.createElement("div");
      row.className = "history-row";
      const icon = session.type === "flashcards" ? "🃏" : "📝";
      const dateText = session.date ? new Date(session.date).toLocaleString() : "--";
      row.innerHTML = `
        <div class="history-head">
          <strong>${icon} ${session.type || "session"}</strong>
          <span>${session.score || 0}/${session.total || 0}</span>
        </div>
        <p class="history-source">${truncate(session.source || "Unknown source")}</p>
        <p class="history-meta">${dateText}</p>
      `;
      row.addEventListener("click", () => {
        const existing = row.querySelector(".history-details");
        if (existing) {
          existing.remove();
          return;
        }
        const details = document.createElement("div");
        details.className = "history-details";
        const wrongItems = Array.isArray(session.wrong_items) ? session.wrong_items : [];
        if (!wrongItems.length) {
          details.innerHTML = "<p class='history-meta'>No wrong items.</p>";
        } else {
          details.innerHTML = wrongItems
            .map((item) => {
              const front = item.front || item.question || "Item";
              const back = item.back || item.answer || "";
              return `<div class="wrong-item"><strong>${front}</strong><p>${back}</p></div>`;
            })
            .join("");
        }
        row.appendChild(details);
      });
      els.historyList.appendChild(row);
    });
  }

  async function loadHistory() {
    try {
      const response = await fetch("/api/get-progress");
      const data = await response.json();
      state.historySessions = Array.isArray(data.sessions) ? data.sessions : [];
      renderHistorySessions();
    } catch (err) {
      console.error("Could not load history", err);
    }
  }

  async function generateStudy() {
    const mode = getSelectedMode();
    if (!mode) {
      alert("Select Flashcards and/or Quiz before generating.");
      return;
    }
    state.selectedMode = mode;
    let response;
    let source = "";
    setLoading(true, state.inputMode);
    try {
      if (state.inputMode === "file") {
        const file = els.fileInput.files && els.fileInput.files[0];
        if (!file) {
          alert("Select an image or PDF first.");
          return;
        }
        source = file.name;
        const formData = new FormData();
        formData.append("file", file);
        formData.append("mode", mode);
        response = await fetch("/api/generate-study", { method: "POST", body: formData });
      } else {
        const prompt = (els.topicInput.value || "").trim();
        if (!prompt) {
          alert("Enter a topic prompt first.");
          return;
        }
        source = prompt;
        response = await fetch("/api/generate-study", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt, mode }),
        });
      }
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Failed to generate study content");
      }
      state.currentSource = source;
      state.generated.flashcards = Array.isArray(data.flashcards) ? data.flashcards : [];
      state.generated.quiz = Array.isArray(data.quiz) ? data.quiz : [];
      if ((mode === "flashcards" || mode === "both") && state.generated.flashcards.length) {
        startFlashcards(state.generated.flashcards);
        setActiveTab("flashcards");
      }
      if ((mode === "quiz" || mode === "both") && state.generated.quiz.length) {
        startQuiz(state.generated.quiz);
        if (mode === "quiz" || !state.generated.flashcards.length) {
          setActiveTab("quiz");
        }
      }
    } catch (err) {
      alert(err.message || "Could not generate study content.");
    } finally {
      setLoading(false, state.inputMode);
    }
  }

  function onKeyDown(event) {
    const tag = (document.activeElement && document.activeElement.tagName || "").toLowerCase();
    const isTyping = tag === "input" || tag === "textarea";
    if (isTyping) return;
    const tab = activeTabName();
    if (tab === "flashcards") {
      if (event.code === "Space") {
        event.preventDefault();
        state.flashcards.flipped = !state.flashcards.flipped;
        renderFlashcard();
      } else if (event.key === "ArrowLeft") {
        prevFlashcard();
      } else if (event.key === "ArrowRight") {
        nextFlashcard();
      }
    }
    if (tab === "quiz" && /^[1-4]$/.test(event.key)) {
      const optionButtons = Array.from(els.quizOptions.querySelectorAll(".quiz-option-btn"));
      const index = Number(event.key) - 1;
      if (optionButtons[index]) optionButtons[index].click();
    }
  }

  function initEvents() {
    els.tabs.forEach((tab) => tab.addEventListener("click", () => setActiveTab(tab.dataset.tab)));
    els.historyToggle.addEventListener("click", () => {
      state.historyOpen = !state.historyOpen;
      els.historyPanel.classList.toggle("is-collapsed", !state.historyOpen);
    });
    els.inputModeButtons.forEach((button) => {
      button.addEventListener("click", () => setInputMode(button.dataset.inputMode));
    });
    els.fileButton.addEventListener("click", () => els.fileInput.click());
    els.fileInput.addEventListener("change", renderUploadSelection);
    ["dragenter", "dragover"].forEach((name) => {
      els.uploadZone.addEventListener(name, (event) => {
        event.preventDefault();
        els.uploadZone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      els.uploadZone.addEventListener(name, (event) => {
        event.preventDefault();
        els.uploadZone.classList.remove("is-dragover");
      });
    });
    els.uploadZone.addEventListener("drop", (event) => {
      const files = event.dataTransfer && event.dataTransfer.files;
      if (files && files.length) {
        els.fileInput.files = files;
        renderUploadSelection();
      }
    });
    els.topicInput.addEventListener("input", () => {
      els.topicCounter.textContent = `${els.topicInput.value.length} / 1200`;
    });
    [els.flashModeToggle, els.quizModeToggle].forEach((toggle) => {
      toggle.addEventListener("click", () => toggle.classList.toggle("is-active"));
    });
    els.generateButton.addEventListener("click", generateStudy);
    els.flashcardCard.addEventListener("click", () => {
      state.flashcards.flipped = !state.flashcards.flipped;
      renderFlashcard();
    });
    els.flashPrevButton.addEventListener("click", prevFlashcard);
    els.flashNextButton.addEventListener("click", nextFlashcard);
    els.markKnownButton.addEventListener("click", () => markFlashcard(true));
    els.markLearningButton.addEventListener("click", () => markFlashcard(false));
    els.quizNextButton.addEventListener("click", nextQuizQuestion);
    window.addEventListener("keydown", onKeyDown);
  }

  initEvents();
  loadHistory();
  setInputMode("file");
  startFlashcards([]);
  startQuiz([]);
})();
