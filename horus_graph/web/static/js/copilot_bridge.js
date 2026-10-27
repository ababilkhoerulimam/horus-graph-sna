// AI Copilot WebSocket Bridge & Two-Way Canvas Control
(function () {
  let ws = null;
  let reconnectTimer = null;

  function getWsUrl() {
    const isHttps = window.location.protocol === "https:";
    const protocol = isHttps ? "wss:" : "ws:";
    // If served via file://, fallback to default local backend 127.0.0.1:8000
    const host = window.location.host || "127.0.0.1:8000";
    return `${protocol}//${host}/ws/copilot`;
  }

  function connect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);

    try {
      const url = getWsUrl();
      ws = new WebSocket(url);

      ws.onopen = function () {
        console.log("[CopilotBridge] WebSocket connected to", url);
        if (window.copilotUI) {
          window.copilotUI.setConnectionStatus(true, "Live Connected");
        }
      };

      ws.onclose = function () {
        console.warn("[CopilotBridge] WebSocket disconnected. Reconnecting in 3s...");
        if (window.copilotUI) {
          window.copilotUI.setConnectionStatus(false, "Disconnected");
        }
        reconnectTimer = setTimeout(connect, 3000);
      };

      ws.onerror = function (err) {
        console.error("[CopilotBridge] WebSocket error:", err);
      };

      ws.onmessage = function (event) {
        try {
          const msg = JSON.parse(event.data);
          handleDownlinkMessage(msg);
        } catch (e) {
          console.error("[CopilotBridge] Error parsing incoming message:", e);
        }
      };
    } catch (err) {
      console.warn("[CopilotBridge] Connection attempt failed:", err);
      reconnectTimer = setTimeout(connect, 3000);
    }
  }

  function handleDownlinkMessage(msg) {
    const type = msg.type;
    const payload = msg.payload || {};

    if (type === "SYSTEM_CONNECTED") {
      console.log("[CopilotBridge] System handshake:", payload.message);
    }

    else if (type === "AGENT_MESSAGE") {
      if (window.copilotUI) {
        window.copilotUI.appendAgentMessage(payload.agent || "AI AGENT", payload.text || "");
      }
    }

    else if (type === "NODE_DOSSIER_READY") {
      const drawerEl = document.getElementById("copilot-drawer");
      const isCopilotOpen = drawerEl && drawerEl.classList.contains("open");

      if (window.copilotUI && isCopilotOpen) {
        const d = payload;
        // Hanya cetak jika berbeda dari simpul terakhir yang baru saja dicetak
        if (window.copilotUI.lastSelectedNodeId !== d.id) {
          window.copilotUI.lastSelectedNodeId = d.id;
          const text = `**Simpul Terfokus: ${d.label}** (\`${d.entity_type}\`)\n` +
            `• Sektor: **${d.cluster}** (${d.community})\n` +
            `• Derajat Relasi: **${d.degree} koneksi** (Undirected)\n` +
            `• Burt Constraint (C_i): **${d.burt_constraint !== undefined ? d.burt_constraint.toFixed(4) : '-'}** (${d.structural_hole_role || 'Bridge'})\n` +
            `• Sentimen: **${d.sentiment_stance > 0 ? '+' : ''}${d.sentiment_stance}** (${d.sentiment_pos}% Pos, ${d.sentiment_neg}% Neg)\n` +
            `• Rekomendasi: *${d.tactical_action}*`;
          window.copilotUI.appendAgentMessage("NODE INTELLIGENCE", text);
        }
      }
    }

    else if (type === "CANVAS_COMMAND" || type === "CANVAS_DIRECTOR") {
      handleCanvasCommand(payload);
    }

    else if (type === "GRAPH_RELOADED") {
      if (window.copilotUI) {
        window.copilotUI.appendAgentMessage("SENTINEL AGENT", `Dataset graf baru telah dimuat pada ${payload.timestamp}. Memuat ulang visualizer radar...`);
      }
      setTimeout(() => {
        window.location.reload();
      }, 1200);
    }
  }

  let isProgrammaticFocus = false;

  function handleCanvasCommand(cmd) {
    const action = cmd.action;

    // 1. Fokus simpul tunggal
    if (action === "CANVAS_FOCUS" || action === "FOCUS_NODE") {
      const nid = cmd.node_id || (cmd.target_nodes && cmd.target_nodes[0]);
      if (!nid) return;
      if (typeof allData !== "undefined" && allData.nodes && typeof svg !== "undefined" && typeof zoom !== "undefined") {
        const targetNode = allData.nodes.find(n => n.id === nid || n.label === nid);
        if (targetNode) {
          isProgrammaticFocus = true;
          if (typeof selectAndInspectNode === "function") {
            selectAndInspectNode(targetNode);
          }
          isProgrammaticFocus = false;
          const scale = cmd.scale || 1.15;
          svg.transition().duration(750).call(
            zoom.transform,
            d3.zoomIdentity.translate(-targetNode.x * scale, -targetNode.y * scale).scale(scale)
          );
        }
      }
    }

    // 2. Isolasi subgraf klaster
    else if (action === "ISOLATE_CLUSTER") {
      const cName = (cmd.cluster_name || "").toLowerCase();
      if (typeof nodeG !== "undefined" && typeof allData !== "undefined") {
        nodeG.each(function (n) {
          const egoId = (typeof window !== "undefined" && window.EGO_ID) || null;
          const matchCluster = (n.cluster && n.cluster.toLowerCase().includes(cName)) ||
                                (n.louvain_community && String(n.louvain_community).toLowerCase().includes(cName)) ||
                                (egoId && n.id === egoId);
          d3.select(this)
            .classed("dimmed", !matchCluster)
            .style("opacity", matchCluster ? 1.0 : 0.15);
        });
        console.log(`[CopilotBridge] Subgraf klaster '${cName}' diisolasi pada kanvas.`);
      }
    }

    // 3. Komparasi dua simpul
    else if (action === "COMPARE_NODES") {
      const targets = cmd.target_nodes || [];
      if (targets.length >= 2 && typeof nodeG !== "undefined" && typeof allData !== "undefined") {
        const targetSet = new Set(targets);
        const egoId = (typeof window !== "undefined" && window.EGO_ID) || null;
        nodeG.each(function (n) {
          const isTarget = targetSet.has(n.id) || targetSet.has(n.label) || (egoId && n.id === egoId);
          d3.select(this)
            .classed("dimmed", !isTarget)
            .style("opacity", isTarget ? 1.0 : 0.18);
        });
        console.log(`[CopilotBridge] Mode komparasi simpul [${targets.join(", ")}] aktif.`);
      }
    }

    // 4. Picu perambatan kausal di layar
    else if (action === "TRIGGER_TRACE" || action === "HIGHLIGHT_PATH") {
      const route = cmd.trace_route || {};
      const orig = route.origin || (cmd.path && cmd.path[0]);
      const targ = route.target || (cmd.path && cmd.path[cmd.path.length - 1]);

      if (orig && targ && typeof traceAndAnimatePath === "function") {
        const tracerEl = document.getElementById("tracer-drawer");
        if (tracerEl && !tracerEl.classList.contains("open")) {
          tracerEl.classList.add("open");
        }
        traceAndAnimatePath(orig, targ);
        console.log(`[CopilotBridge] Pemicu perambatan kausal: ${orig} -> ${targ}.`);
      }
    }

    // 5. Kembalikan tampilan kanvas ke posisi normal
    else if (action === "RESET_VIEW") {
      if (typeof resetNodeHighlight === "function") resetNodeHighlight();
      if (typeof deactivateNodes === "function") deactivateNodes();
      if (typeof svg !== "undefined" && typeof zoom !== "undefined" && typeof getCloseFitTransform === "function") {
        const t = getCloseFitTransform();
        svg.transition().duration(750).call(zoom.transform, t);
      }
      console.log("[CopilotBridge] Tampilan kanvas dikembalikan ke normal.");
    }
  }

  // Uplink Send Functions
  function sendJson(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  }

  function sendNodeSelected(nodeId) {
    sendJson({
      type: "NODE_SELECTED",
      payload: { node_id: nodeId }
    });
  }

  function sendChatQuery(message, sessionId) {
    sendJson({
      type: "USER_CHAT_QUERY",
      payload: {
        message: message,
        session_id: sessionId || (window.copilotUI && typeof window.copilotUI.getActiveSessionId === "function" ? window.copilotUI.getActiveSessionId() : null)
      }
    });
  }

  // Hook into global node selection (hanya kirim ke server jika interaksi klik manual pengguna di kanvas)
  const originalSelect = window.selectAndInspectNode;
  window.selectAndInspectNode = function (d) {
    if (typeof originalSelect === "function") {
      originalSelect(d);
    }
    if (window.copilotUI && typeof window.copilotUI.updateActiveNodeBadge === "function") {
      window.copilotUI.updateActiveNodeBadge(d);
    }
    if (!isProgrammaticFocus && d && d.id) {
      sendNodeSelected(d.id);
    }
  };

  // Export to window
  window.copilotBridge = {
    connect: connect,
    sendNodeSelected: sendNodeSelected,
    sendChatQuery: sendChatQuery
  };

  // Copilot adalah lapisan opsional. Server mengumumkan dukungannya lewat
  // /api/health; kalau belum ada, UI disembunyikan tanpa percobaan koneksi.
  async function detectCapability() {
    try {
      const res = await fetch("/api/health?t=" + Date.now());
      if (!res.ok) return false;
      const payload = await res.json();
      return !!(payload && payload.capabilities && payload.capabilities.copilot);
    } catch (err) {
      return false;
    }
  }

  function hideCopilotUi() {
    ["btn-toggle-copilot", "copilot-drawer"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    });
  }

  async function init() {
    if (!(await detectCapability())) {
      hideCopilotUi();
      return;
    }
    connect();
  }

  // Auto connect when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
