// AI Copilot Drawer UI Manager with Math-Safe Markdown, KaTeX & Session Management
(function () {
  const drawerEl = document.getElementById("copilot-drawer");
  const closeBtnEl = document.getElementById("copilot-close");
  const toggleBtnEl = document.getElementById("btn-toggle-copilot");
  const chatBodyEl = document.getElementById("copilot-chat-body");
  const inputEl = document.getElementById("copilot-input-box");
  const sendBtnEl = document.getElementById("copilot-send-btn");
  const statusDotEl = document.getElementById("copilot-status-dot");
  const statusTextEl = document.getElementById("copilot-status-text");

  // Session elements
  const btnNewSession = document.getElementById("btn-new-session");
  const btnSessionHistory = document.getElementById("btn-session-history");
  const sessionsPanel = document.getElementById("copilot-sessions-panel");
  const btnCloseSessions = document.getElementById("btn-close-sessions");
  const sessionsListEl = document.getElementById("copilot-sessions-list");

  let activeSessionId = localStorage.getItem("sna_active_session_id") || null;
  let lastDossierNode = null;

  function renderQuickChips(node) {
    const bar = document.getElementById("copilot-chips-bar");
    if (!bar) return;

    // Label dan nama pusat berasal dari presentation bundle; tidak ada nama
    // domain di berkas ini.
    const meta = (typeof window !== "undefined" && window.PRESENTATION) || {};
    const ego = meta.ego || null;
    const egoName = ego ? (ego.label || ego.id) : "";
    const wording = meta.wording || {};

    let chips = [];
    if (node && node.id) {
      const name = node.label || node.id;
      chips = [
        { label: `Dossier: ${name}`, prompt: wording.chip_dossier || `Analisis profil dan peran jaringan ${name}` },
        { label: "What-If", prompt: wording.chip_whatif || `Bagaimana jika ${name} tidak ada dalam jaringan?` },
        { label: "Sentimen & Isu", prompt: wording.chip_sentiment || `Bagaimana sentimen dan isu terkini seputar ${name}?` },
        {
          label: egoName ? `Lacak ke ${egoName}` : "Lacak Jalur",
          prompt: egoName
            ? `Lacak jalur relasi dari ${name} ke ${egoName}`
            : `Lacak jalur relasi dari ${name} ke simpul terdekat`
        },
        { label: "✕ Reset Fokus", isReset: true }
      ];
    } else {
      chips = [
        {
          label: "Ringkasan",
          prompt: wording.chip_summary || (egoName
            ? `Berikan ringkasan topologi jaringan ${egoName}`
            : "Berikan ringkasan topologi jaringan")
        },
        { label: "Memo Eksekutif", prompt: wording.chip_memo || "Buatkan memo eksekutif terkini" },
        { label: "Aktor Broker", prompt: wording.chip_broker || "Siapa aktor broker terpenting dalam jaringan?" },
        { label: "Risiko Sentimen", prompt: wording.chip_risk || "Siapa entitas dengan risiko sentimen negatif tertinggi?" },
        { label: "Peta Relasi", prompt: wording.chip_map || (egoName
          ? `Bagaimana peta relasi ${egoName} dengan entitas lain?`
          : "Bagaimana peta relasi antar entitas dalam jaringan?") }
      ];
    }

    bar.innerHTML = "";
    chips.forEach(c => {
      const btn = document.createElement("button");
      btn.className = "copilot-chip" + (node ? " active-context" : "");
      btn.textContent = c.label;
      if (c.isReset) {
        btn.addEventListener("click", () => {
          lastDossierNode = null;
          renderQuickChips(null);
          if (window.copilotBridge && typeof window.copilotBridge.sendChatQuery === "function") {
            window.copilotBridge.sendChatQuery("Kembalikan tampilan normal dan berikan ringkasan jaringan.", activeSessionId);
          }
        });
      } else {
        btn.addEventListener("click", () => {
          openCopilotDrawer();
          appendUserMessage(c.prompt);
          if (window.copilotBridge && typeof window.copilotBridge.sendChatQuery === "function") {
            window.copilotBridge.sendChatQuery(c.prompt, activeSessionId);
          }
        });
      }
      bar.appendChild(btn);
    });
  }

  function updateActiveNodeBadge(d) {
    if (!d || !d.id) return;
    lastDossierNode = d;
    renderQuickChips(d);
  }

  function openCopilotDrawer() {
    if (!drawerEl) return;
    drawerEl.classList.add("open");
    document.body.classList.add("copilot-open");
    // Mutual exclusivity: hide other right drawers
    const nodeDrawer = document.getElementById("node-drawer");
    if (nodeDrawer) nodeDrawer.style.display = "none";
    const tracerDrawer = document.getElementById("tracer-drawer");
    if (tracerDrawer) tracerDrawer.style.display = "none";

    if (toggleBtnEl) toggleBtnEl.classList.add("active");
    if (inputEl) inputEl.focus();

    // Ensure session initialized
    if (!activeSessionId) {
      initSession();
    }
  }

  function closeCopilotDrawer() {
    if (!drawerEl) return;
    drawerEl.classList.remove("open");
    document.body.classList.remove("copilot-open");
    if (toggleBtnEl) toggleBtnEl.classList.remove("active");
    if (sessionsPanel) sessionsPanel.style.display = "none";
  }

  function toggleCopilotDrawer() {
    if (!drawerEl) return;
    if (drawerEl.classList.contains("open")) {
      closeCopilotDrawer();
    } else {
      openCopilotDrawer();
    }
  }

  function setConnectionStatus(connected, text) {
    if (statusDotEl) {
      statusDotEl.classList.toggle("connected", connected);
    }
    if (statusTextEl) {
      statusTextEl.textContent = text || (connected ? "Live Connected" : "Disconnected");
    }
  }

  function fallbackRegexMarkdown(txt) {
    return txt
      .replace(/^### (.*$)/gim, '<h3>$1</h3>')
      .replace(/^## (.*$)/gim, '<h2>$1</h2>')
      .replace(/^# (.*$)/gim, '<h1>$1</h1>')
      .replace(/^\s*[\*\-]\s+(.*$)/gim, '<li>$1</li>')
      .replace(/(<li>.*<\/li>)/gis, '<ul>$1</ul>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`(.*?)`/g, '<code>$1</code>')
      .replace(/\n\n+/g, '<br><br>')
      .replace(/\n/g, '<br>');
  }

  /**
   * Pipeline Rendering Matematika dan Markdown Bebas Konflik
   */
  function renderMarkdownAndMath(rawText) {
    if (!rawText) return "";

    const mathTokens = [];
    function saveMathToken(mathStr, isBlock) {
      const idx = mathTokens.length;
      mathTokens.push({ math: mathStr, isBlock: isBlock });
      return `@@KATEX_TOKEN_${idx}@@`;
    }

    // A. Display Math: $$...$$ atau \[...\]
    let processed = rawText.replace(/\$\$([\s\S]*?)\$\$/g, function (match, equation) {
      return saveMathToken(equation.trim(), true);
    });
    processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, function (match, equation) {
      return saveMathToken(equation.trim(), true);
    });

    // B. Inline Math: $...$ atau \(...\)
    processed = processed.replace(/(?<!\\)\$([^\$\n]+?)(?<!\\)\$/g, function (match, equation) {
      const eq = equation.trim();
      if (!eq) return match;
      return saveMathToken(eq, false);
    });
    processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, function (match, equation) {
      return saveMathToken(equation.trim(), false);
    });

    // C. Parse Markdown via Marked.js
    let htmlOutput = "";
    if (typeof marked !== "undefined" && typeof marked.parse === "function") {
      try {
        if (typeof marked.setOptions === "function") {
          marked.setOptions({
            gfm: true,
            breaks: true,
            headerIds: false,
            mangle: false
          });
        }
        htmlOutput = marked.parse(processed);
      } catch (e) {
        htmlOutput = fallbackRegexMarkdown(processed);
      }
    } else {
      htmlOutput = fallbackRegexMarkdown(processed);
    }

    // D. Detokenisasi dan Render KaTeX
    htmlOutput = htmlOutput.replace(/@@KATEX_TOKEN_(\d+)@@/g, function (match, idxStr) {
      const idx = parseInt(idxStr, 10);
      if (idx >= 0 && idx < mathTokens.length) {
        const item = mathTokens[idx];
        if (typeof katex !== "undefined" && typeof katex.renderToString === "function") {
          try {
            return katex.renderToString(item.math, {
              displayMode: item.isBlock,
              throwOnError: false,
              output: "htmlAndMath"
            });
          } catch (err) {
            return item.isBlock ? `<pre>$$${item.math}$$</pre>` : `<code>$${item.math}$</code>`;
          }
        } else {
          return item.isBlock ? `$$${item.math}$$` : `$${item.math}$`;
        }
      }
      return match;
    });

    return htmlOutput;
  }

  function appendUserMessage(text) {
    if (!chatBodyEl) return;
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble user";
    bubble.textContent = text;
    chatBodyEl.appendChild(bubble);
    chatBodyEl.scrollTop = chatBodyEl.scrollHeight;
  }

  function appendAgentMessage(agentName, rawMarkdown) {
    if (!chatBodyEl) return;
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble agent";
    const tag = document.createElement("span");
    tag.className = "agent-tag";
    tag.textContent = agentName || "AI AGENT";
    bubble.appendChild(tag);

    const body = document.createElement("div");
    body.className = "bubble-content";
    body.innerHTML = renderMarkdownAndMath(rawMarkdown);
    bubble.appendChild(body);

    chatBodyEl.appendChild(bubble);
    chatBodyEl.scrollTop = chatBodyEl.scrollHeight;
  }

  // --- Session Management Functions ---
  async function initSession() {
    // Copilot adalah lapisan opsional: server mengumumkan lewat /api/health.
    // Tanpa dukungan, tidak ada permintaan sesi yang dikirim.
    try {
      const health = await fetch("/api/health?t=" + Date.now());
      if (!health.ok) return;
      const capabilities = await health.json();
      if (!(capabilities && capabilities.capabilities && capabilities.capabilities.copilot)) {
        return;
      }
    } catch (e) {
      return;
    }
    try {
      const resp = await fetch("/api/chat/sessions");
      const data = await resp.json();
      const sessions = data.sessions || [];

      if (sessions.length > 0) {
        // Gunakan sesi aktif tersimpan atau sesi paling terbaru
        const found = sessions.find(s => s.id === activeSessionId);
        if (found) {
          switchSession(found.id, false);
        } else {
          switchSession(sessions[0].id, false);
        }
      } else {
        await createNewSession();
      }
    } catch (e) {
      console.warn("[CopilotUI] Init sessions failed:", e);
    }
  }

  async function createNewSession() {
    try {
      const resp = await fetch("/api/chat/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "Percakapan Baru" })
      });
      const data = await resp.json();
      activeSessionId = data.id;
      localStorage.setItem("sna_active_session_id", activeSessionId);

      // Bersihkan chat body
      if (chatBodyEl) chatBodyEl.innerHTML = "";
      if (sessionsPanel) sessionsPanel.style.display = "none";

      const meta = (typeof window !== "undefined" && window.PRESENTATION) || {};
      const ego = meta.ego || null;
      const egoName = ego ? (ego.label || ego.id) : "";
      const greeting = (meta.wording && meta.wording.chip_greeting)
        || (egoName
          ? `Silakan tanyakan analisis jaringan seputar ${egoName}.`
          : "Silakan tanyakan analisis jaringan pada bundle ini.");
      appendAgentMessage(
        "Copilot",
        `**Sesi Baru Dimulai.**\n${greeting}`
      );
    } catch (e) {
      console.error("[CopilotUI] Gagal membuat sesi baru:", e);
    }
  }

  async function switchSession(sessionId, hidePanel = true) {
    activeSessionId = sessionId;
    localStorage.setItem("sna_active_session_id", activeSessionId);

    if (hidePanel && sessionsPanel) {
      sessionsPanel.style.display = "none";
    }

    try {
      const resp = await fetch(`/api/chat/sessions/${sessionId}/messages`);
      const data = await resp.json();
      const msgs = data.messages || [];

      if (chatBodyEl) {
        chatBodyEl.innerHTML = "";
        if (msgs.length === 0) {
          appendAgentMessage("SNA Copilot", "Sesi ini belum memiliki percakapan. Silakan ajukan pertanyaan.");
        } else {
          for (const m of msgs) {
            if (m.role === "user") {
              appendUserMessage(m.content);
            } else {
              appendAgentMessage(m.agent_name || "AI AGENT", m.content);
            }
          }
        }
      }
    } catch (e) {
      console.error("[CopilotUI] Gagal memuat pesan sesi:", e);
    }
  }

  async function deleteSession(sessionId) {
    try {
      await fetch(`/api/chat/sessions/${sessionId}`, { method: "DELETE" });
      if (sessionId === activeSessionId) {
        localStorage.removeItem("sna_active_session_id");
        activeSessionId = null;
        await initSession();
      } else {
        await loadSessionsList();
      }
    } catch (e) {
      console.error("[CopilotUI] Gagal menghapus sesi:", e);
    }
  }

  async function loadSessionsList() {
    if (!sessionsListEl) return;
    sessionsListEl.innerHTML = '<div style="padding:8px; color:#64748B; font-size:10px;">Memuat riwayat...</div>';

    try {
      const resp = await fetch("/api/chat/sessions");
      const data = await resp.json();
      const sessions = data.sessions || [];

      sessionsListEl.innerHTML = "";
      if (sessions.length === 0) {
        sessionsListEl.innerHTML = '<div style="padding:8px; color:#64748B; font-size:10px;">Belum ada riwayat sesi.</div>';
        return;
      }

      sessions.forEach(s => {
        const item = document.createElement("div");
        item.className = "session-item" + (s.id === activeSessionId ? " active" : "");
        item.innerHTML = `
          <div class="session-item-info">
            <div class="session-item-title">${s.title || "Percakapan"}</div>
            <div class="session-item-date">${(s.updated_at || "").substring(0, 10)}</div>
          </div>
          <button class="session-item-del" title="Hapus sesi ini">✕</button>
        `;
        const infoEl = item.querySelector(".session-item-info");
        if (infoEl) infoEl.addEventListener("click", () => switchSession(s.id));
        const delEl = item.querySelector(".session-item-del");
        if (delEl) {
          delEl.addEventListener("click", (e) => {
            e.stopPropagation();
            deleteSession(s.id);
          });
        }
        sessionsListEl.appendChild(item);
      });
    } catch (e) {
      sessionsListEl.innerHTML = '<div style="padding:8px; color:#EF4444; font-size:10px;">Gagal memuat sesi.</div>';
    }
  }

  function handleSend() {
    if (!inputEl) return;
    const text = inputEl.value.trim();
    if (!text) return;
    appendUserMessage(text);
    inputEl.value = "";

    if (window.copilotBridge && typeof window.copilotBridge.sendChatQuery === "function") {
      window.copilotBridge.sendChatQuery(text, activeSessionId);
    }
  }

  // Event Listeners
  if (closeBtnEl) closeBtnEl.addEventListener("click", closeCopilotDrawer);
  if (toggleBtnEl) toggleBtnEl.addEventListener("click", toggleCopilotDrawer);

  if (btnNewSession) btnNewSession.addEventListener("click", createNewSession);
  if (btnSessionHistory) {
    btnSessionHistory.addEventListener("click", () => {
      if (!sessionsPanel) return;
      if (sessionsPanel.style.display === "none" || !sessionsPanel.style.display) {
        sessionsPanel.style.display = "flex";
        loadSessionsList();
      } else {
        sessionsPanel.style.display = "none";
      }
    });
  }
  if (btnCloseSessions) {
    btnCloseSessions.addEventListener("click", () => {
      if (sessionsPanel) sessionsPanel.style.display = "none";
    });
  }

  if (sendBtnEl) sendBtnEl.addEventListener("click", handleSend);
  if (inputEl) {
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });
  }

  // Preset quick prompt pills
  document.querySelectorAll(".copilot-preset-pill").forEach(pill => {
    pill.addEventListener("click", function () {
      const prompt = this.getAttribute("data-prompt");
      if (prompt) {
        openCopilotDrawer();
        appendUserMessage(prompt);
        if (window.copilotBridge && typeof window.copilotBridge.sendChatQuery === "function") {
          window.copilotBridge.sendChatQuery(prompt, activeSessionId);
        }
      }
    });
  });

  // Tactical Quick Prompt Chips
  document.querySelectorAll(".quick-chip-btn").forEach(btn => {
    btn.addEventListener("click", function () {
      const query = this.getAttribute("data-query");
      if (!query) return;
      openCopilotDrawer();
      const input = document.getElementById("copilot-input-box") || document.getElementById("copilot-input");
      if (input) input.value = query;
      const form = document.getElementById("copilot-chat-form");
      if (form) {
        form.dispatchEvent(new Event("submit"));
      } else {
        handleSend();
      }
    });
  });

  // Export to window
  window.copilotUI = {
    openDrawer: openCopilotDrawer,
    closeDrawer: closeCopilotDrawer,
    setConnectionStatus: setConnectionStatus,
    appendUserMessage: appendUserMessage,
    appendAgentMessage: appendAgentMessage,
    renderMarkdownAndMath: renderMarkdownAndMath,
    getActiveSessionId: () => activeSessionId,
    createNewSession: createNewSession,
    switchSession: switchSession,
    lastSelectedNodeId: null,
    updateActiveNodeBadge: updateActiveNodeBadge
  };

  // Auto init session on DOM loaded
  document.addEventListener("DOMContentLoaded", initSession);
})();
