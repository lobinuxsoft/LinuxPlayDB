/**
 * LinuxPlayDB — Render Module
 * Handles table rendering, detail panels, and stats display.
 */

const LPDB_Render = (() => {
  const expandedRows = new Set();

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderAmd(status) {
    const lang = LPDB_i18n.lang();
    switch (status) {
      case "amd_pt":
        return '<span class="badge badge-amd">AMD \u2713 (PT)</span>';
      case "amd_ok":
        return '<span class="badge badge-amd">AMD \u2713</span>';
      case "amd_rt_only":
        return '<span class="badge badge-amd-warn">AMD RT only</span>';
      case "nvidia_only":
        return '<span class="badge badge-nvidia">NVIDIA PT</span>';
      default:
        return "\u2014";
    }
  }

  function renderTech(game) {
    const badges = [];
    if (game.dlss_rr) badges.push('<span class="badge badge-nvidia-sm">RR</span>');
    if (game.dlss_mfg) badges.push('<span class="badge badge-tech">MFG</span>');
    if (game.dlss_fg && !game.dlss_mfg) badges.push('<span class="badge badge-tech">FG</span>');
    if (game.dlss_sr) badges.push('<span class="badge badge-tech">SR</span>');
    if (game.fsr4) badges.push('<span class="badge badge-fsr">FSR4</span>');
    return badges.length ? badges.join(" ") : "\u2014";
  }

  function renderLinux(status, gameName) {
    switch (status) {
      case "works":
        return `<span class="badge badge-linux">${LPDB_i18n.t("status_works")}</span>`;
      case "cmd":
        return `<span class="badge badge-linux-warn">${LPDB_i18n.t("status_cmd")}</span>`;
      case "broken":
        return '<span class="badge badge-broken">Broken</span>';
      case "check": {
        const url = `https://www.protondb.com/search?q=${encodeURIComponent(gameName || "")}`;
        return `<a href="${url}" target="_blank" rel="noopener" class="badge badge-linux-maybe" onclick="event.stopPropagation()" title="Search on ProtonDB">Check ProtonDB \u2197</a>`;
      }
      default:
        return "\u2014";
    }
  }

  function renderCmd(game) {
    if (game.launch_options) {
      const short = game.launch_options.length > 30 ? "CMD..." : "CMD";
      return `<span class="badge badge-cmd" title="${esc(game.launch_options)}">${short}</span>`;
    }
    if (game.linux_status === "cmd") {
      return `<span class="badge badge-linux-warn">${LPDB_i18n.t("see_notes")}</span>`;
    }
    return "\u2014";
  }

  function getNotes(game) {
    const lang = LPDB_i18n.lang();
    return lang === "es"
      ? game.lc_notes_es || game.lc_notes_en || ""
      : game.lc_notes_en || "";
  }

  /**
   * Render the main games table.
   * @param {Array<Object>} games
   */
  function renderTable(games) {
    const tbody = document.getElementById("gamesBody");
    let html = "";

    for (const g of games) {
      const expanded = expandedRows.has(g.app_id);
      const typeBadge = g.rt_type === "pt"
        ? '<span class="badge badge-pt">PATH TRACING</span>'
        : '<span class="badge badge-rt">RAY TRACING</span>';

      html += `<tr onclick="LPDB.toggleRow(${g.app_id})" style="cursor:pointer">
        <td class="lpdb-game-name"><span class="lpdb-expand-icon">${expanded ? "\u25BC" : "\u25B6"}</span>${esc(g.name)}</td>
        <td>${typeBadge}</td>
        <td>${renderAmd(g.amd_status)}</td>
        <td>${renderTech(g)}</td>
        <td>${renderLinux(g.linux_status, g.name)}</td>
        <td>${renderCmd(g)}</td>
      </tr>`;

      if (expanded) {
        html += renderDetailRow(g);
      }
    }

    tbody.innerHTML = html;
  }

  function renderDetailRow(g) {
    const notes = getNotes(g);
    const links = LPDB_DB.getLinks(g.app_id);
    const deviceCompat = LPDB_DB.getDeviceCompat(g.app_id);
    const lang = LPDB_i18n.lang();

    let html = `<tr class="detail-row"><td colspan="6"><div class="lpdb-detail"><div class="lpdb-detail-grid">`;

    // Left column: commands & proton
    html += `<div>`;
    if (g.launch_options) {
      html += `<h4>${LPDB_i18n.t("detail_launch")}</h4>`;
      html += `<div class="lpdb-detail-cmd" onclick="event.stopPropagation();LPDB.copyText(this)" title="Click to copy">${esc(g.launch_options)}</div>`;
    }

    if (g.env_vars) {
      try {
        const vars = JSON.parse(g.env_vars);
        if (Object.keys(vars).length > 0) {
          html += `<h4>${LPDB_i18n.t("detail_env")}</h4>`;
          for (const [k, v] of Object.entries(vars)) {
            html += `<div class="lpdb-detail-note"><code>${esc(k)}=${esc(v)}</code></div>`;
          }
        }
      } catch (_) { /* ignore */ }
    }

    if (g.proton_version) {
      html += `<div class="lpdb-detail-note"><strong>Proton:</strong> ${esc(g.proton_version)}</div>`;
    }
    if (g.protondb_tier) {
      const pdbUrl = `https://www.protondb.com/search?q=${encodeURIComponent(g.name || "")}`;
      html += `<div class="lpdb-detail-note"><strong>ProtonDB:</strong> <a href="${pdbUrl}" target="_blank" rel="noopener" onclick="event.stopPropagation()"><span class="badge badge-${protondbBadgeClass(g.protondb_tier)}">${g.protondb_tier} \u2197</span></a></div>`;
    }
    if (g.deck_status) {
      html += `<div class="lpdb-detail-note"><strong>Steam Deck:</strong> <span class="badge badge-deck-${g.deck_status}">${g.deck_status}</span></div>`;
    }
    if (g.fsr4) {
      html += `<div class="lpdb-detail-note"><strong>FSR4:</strong> <span class="badge badge-fsr">FSR4</span> ${LPDB_i18n.t("detail_fsr4_hint")}</div>`;
    }
    if (g.anticheat) {
      const acBadge = g.anticheat_linux === "supported" ? "badge-linux" : g.anticheat_linux === "denied" ? "badge-broken" : "badge-linux-warn";
      html += `<div class="lpdb-detail-note"><strong>Anti-Cheat:</strong> ${esc(g.anticheat)} <span class="badge ${acBadge}">${g.anticheat_linux || "unknown"}</span></div>`;
    }
    html += `</div>`;

    // Right column: notes, links, devices
    html += `<div>`;
    if (notes) {
      html += `<h4>${LPDB_i18n.t("detail_notes")}</h4>`;
      html += `<div class="lpdb-detail-note">${esc(notes)}</div>`;
    }

    if (links.length > 0) {
      html += `<h4>${LPDB_i18n.t("detail_links")}</h4>`;
      html += `<ul class="lpdb-detail-links">`;
      for (const link of links) {
        const title = lang === "es" ? (link.title_es || link.title_en) : link.title_en;
        html += `<li><a href="${esc(link.url)}" target="_blank" rel="noopener">${esc(title)}</a> <span class="badge badge-tech">${link.source || ""}</span></li>`;
      }
      html += `</ul>`;
    }

    if (deviceCompat.length > 0) {
      html += `<h4>${LPDB_i18n.t("detail_devices")}</h4>`;
      html += renderDeviceTable(deviceCompat);
    }

    html += `</div>`;
    html += `</div></div></td></tr>`;
    return html;
  }

  function renderDeviceTable(compat) {
    let html = `<table class="lpdb-device-table">
      <thead><tr>
        <th>${LPDB_i18n.t("col_device")}</th>
        <th>Status</th>
        <th>FPS</th>
        <th>TDP</th>
        <th>${LPDB_i18n.t("detail_notes")}</th>
      </tr></thead><tbody>`;

    for (const dc of compat) {
      const statusBadge = dc.status === "verified" ? "badge-deck-verified"
        : dc.status === "playable" ? "badge-deck-playable"
        : dc.status === "issues" ? "badge-linux-warn"
        : "badge-broken";
      const notes = LPDB_i18n.lang() === "es" ? (dc.notes_es || dc.notes_en || "") : (dc.notes_en || "");

      html += `<tr>
        <td>${esc(dc.device_name)}</td>
        <td><span class="badge ${statusBadge}">${dc.status}</span></td>
        <td>${dc.fps_estimate || "\u2014"}</td>
        <td>${dc.tdp_watts ? dc.tdp_watts + "W" : "\u2014"}</td>
        <td>${esc(notes)}</td>
      </tr>`;
    }

    html += `</tbody></table>`;
    return html;
  }

  function protondbBadgeClass(tier) {
    switch (tier) {
      case "platinum": return "deck-verified";
      case "gold": return "deck-playable";
      case "silver": return "linux-warn";
      case "bronze": return "linux-maybe";
      case "borked": return "broken";
      default: return "tech";
    }
  }

  /**
   * Toggle a row's expanded state.
   * @param {number} appId
   */
  function toggleRow(appId) {
    if (expandedRows.has(appId)) {
      expandedRows.delete(appId);
    } else {
      expandedRows.add(appId);
    }
    LPDB_Filters.apply();
  }

  function expandAll(games) {
    for (const g of games) expandedRows.add(g.app_id);
    LPDB_Filters.apply();
  }

  function collapseAll() {
    expandedRows.clear();
    LPDB_Filters.apply();
  }

  /**
   * Update stats display.
   * @param {Object} stats
   */
  function updateStats(stats) {
    document.getElementById("statTotal").textContent = stats.total;
    document.getElementById("statPT").textContent = stats.pt;
    document.getElementById("statAMD").textContent = stats.amd;
    document.getElementById("statBroken").textContent = stats.broken;
    document.getElementById("statCmd").textContent = stats.cmd;
    document.getElementById("statFSR4").textContent = stats.fsr4;
  }

  /**
   * Update results count text.
   * @param {number} shown
   * @param {number} total
   */
  function updateResultsCount(shown, total) {
    const el = document.getElementById("resultsCount");
    const clickHint = LPDB_i18n.t("click_hint");
    el.innerHTML = `${LPDB_i18n.t("showing")} <strong>${shown}</strong> ${LPDB_i18n.t("of")} <strong>${total}</strong> ${LPDB_i18n.t("games")} &middot; ${clickHint}`;
  }

  return { renderTable, updateStats, updateResultsCount, toggleRow, expandAll, collapseAll, expandedRows };
})();
