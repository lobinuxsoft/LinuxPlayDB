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
    switch (status) {
      case "amd_pt":
        return `<span class="badge badge-amd" title="${esc(LPDB_i18n.t("badge_tip_amd_pt"))}">AMD \u2713 (PT)</span>`;
      case "amd_ok":
        return `<span class="badge badge-amd" title="${esc(LPDB_i18n.t("badge_tip_amd_ok"))}">AMD \u2713</span>`;
      case "amd_rt_only":
        return `<span class="badge badge-amd-warn" title="${esc(LPDB_i18n.t("badge_tip_amd_rt_only"))}">AMD RT only</span>`;
      case "nvidia_only":
        return `<span class="badge badge-nvidia" title="${esc(LPDB_i18n.t("badge_tip_nvidia_only"))}">NVIDIA PT</span>`;
      default:
        return "\u2014";
    }
  }

  function renderTech(game) {
    const badges = [];
    if (game.dlss_rr) badges.push(`<span class="badge badge-nvidia-sm" title="${esc(LPDB_i18n.t("badge_tip_rr"))}">RR</span>`);
    if (game.dlss_mfg) badges.push(`<span class="badge badge-tech" title="${esc(LPDB_i18n.t("badge_tip_mfg"))}">MFG</span>`);
    if (game.dlss_fg && !game.dlss_mfg) badges.push(`<span class="badge badge-tech" title="${esc(LPDB_i18n.t("badge_tip_fg"))}">FG</span>`);
    if (game.dlss_sr) badges.push(`<span class="badge badge-tech" title="${esc(LPDB_i18n.t("badge_tip_sr"))}">SR</span>`);
    if (game.fsr4) badges.push(`<span class="badge badge-fsr" title="${esc(LPDB_i18n.t("badge_tip_fsr4"))}">FSR4</span>`);
    return badges.length ? badges.join(" ") : "\u2014";
  }

  function renderLinux(status, gameName) {
    switch (status) {
      case "works":
        return `<span class="badge badge-linux" title="${esc(LPDB_i18n.t("badge_tip_works"))}">${LPDB_i18n.t("status_works")}</span>`;
      case "cmd":
        return `<span class="badge badge-linux-warn" title="${esc(LPDB_i18n.t("badge_tip_cmd"))}">${LPDB_i18n.t("status_cmd")}</span>`;
      case "broken":
        return `<span class="badge badge-broken" title="${esc(LPDB_i18n.t("badge_tip_broken"))}">${LPDB_i18n.t("filter_broken")}</span>`;
      case "check": {
        const url = `https://www.protondb.com/search?q=${encodeURIComponent(gameName || "")}`;
        return `<a href="${url}" target="_blank" rel="noopener" class="badge badge-linux-maybe" onclick="event.stopPropagation()" title="Search on ProtonDB">\uD83D\uDD0D ProtonDB \u2197</a>`;
      }
      default:
        return "\u2014";
    }
  }

  function renderCmd(game) {
    if (game.launch_options) {
      const short = game.launch_options.length > 30 ? "CMD..." : "CMD";
      const tipPrefix = LPDB_i18n.t("badge_tip_cmd");
      return `<span class="badge badge-cmd" title="${esc(tipPrefix + ": " + game.launch_options)}">${short}</span>`;
    }
    if (game.linux_status === "cmd") {
      return `<span class="badge badge-linux-warn" title="${esc(LPDB_i18n.t("badge_tip_cmd"))}">${LPDB_i18n.t("see_notes")}</span>`;
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
        ? `<span class="badge badge-pt" title="${esc(LPDB_i18n.t("badge_tip_pt"))}">PATH TRACING</span>`
        : `<span class="badge badge-rt" title="${esc(LPDB_i18n.t("badge_tip_rt"))}">RAY TRACING</span>`;

      const expandLabel = expanded ? "Collapse" : "Expand";
      html += `<tr onclick="LPDB.toggleRow(${g.app_id})" style="cursor:pointer">
        <td class="lpdb-game-name"><span class="lpdb-expand-icon" aria-label="${expandLabel}">${expanded ? "\u25BC" : "\u25B6"}</span>${esc(g.name)}</td>
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
      if (g.proton_version.toLowerCase().includes("check")) {
        const pdbSearchUrl = `https://www.protondb.com/search?q=${encodeURIComponent(g.name || "")}`;
        html += `<div class="lpdb-detail-note"><strong>Proton:</strong> <a href="${pdbSearchUrl}" target="_blank" rel="noopener" class="badge badge-linux-maybe" onclick="event.stopPropagation()">\uD83D\uDD0D ProtonDB \u2197</a></div>`;
      } else {
        html += `<div class="lpdb-detail-note"><strong>Proton:</strong> ${esc(g.proton_version)}</div>`;
      }
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

    // Right column: description, notes, links, devices
    html += `<div>`;
    if (g.short_description) {
      html += `<div class="lpdb-detail-desc">${esc(g.short_description)}</div>`;
    }
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

    // Fallback: if both columns are empty, show a helpful message
    const hasLeftCol = g.launch_options || g.env_vars || g.proton_version || g.protondb_tier || g.deck_status || g.fsr4 || g.anticheat;
    const hasRightCol = g.short_description || notes || links.length > 0 || deviceCompat.length > 0;
    if (!hasLeftCol && !hasRightCol) {
      const pdbUrl = `https://www.protondb.com/search?q=${encodeURIComponent(g.name || "")}`;
      const pcgwUrl = `https://www.pcgamingwiki.com/w/index.php?search=${encodeURIComponent(g.name || "")}`;
      html += `<div class="lpdb-detail-empty">
        <p>${LPDB_i18n.t("detail_no_data")}</p>
        <div class="lpdb-detail-empty-links">
          <a href="${pdbUrl}" target="_blank" rel="noopener" class="badge badge-linux-maybe" onclick="event.stopPropagation()">\uD83D\uDD0D ProtonDB \u2197</a>
          <a href="${pcgwUrl}" target="_blank" rel="noopener" class="badge badge-tech" onclick="event.stopPropagation()">\uD83D\uDD0D PCGamingWiki \u2197</a>
        </div>
      </div>`;
    }

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
    LPDB_Filters.apply(false);
  }

  function expandAll(games) {
    for (const g of games) expandedRows.add(g.app_id);
    LPDB_Filters.apply(false);
  }

  function collapseAll() {
    expandedRows.clear();
    LPDB_Filters.apply(false);
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
   * Update results count text with pagination info.
   * @param {number} filtered - Number of filtered games
   * @param {number} total - Total games in DB
   * @param {number} page - Current page (1-based)
   * @param {number} totalPages - Total pages
   * @param {number} rangeStart - First item index on page (1-based)
   * @param {number} rangeEnd - Last item index on page (1-based)
   */
  function updateResultsCount(filtered, total, page, totalPages, rangeStart, rangeEnd) {
    const el = document.getElementById("resultsCount");
    const clickHint = LPDB_i18n.t("click_hint");
    if (filtered === 0) {
      el.innerHTML = `${LPDB_i18n.t("showing")} <strong>0</strong> ${LPDB_i18n.t("of")} <strong>${total}</strong> ${LPDB_i18n.t("games")}`;
    } else {
      el.innerHTML = `${LPDB_i18n.t("showing")} <strong>${rangeStart}&ndash;${rangeEnd}</strong> ${LPDB_i18n.t("of")} <strong>${filtered}</strong> ${LPDB_i18n.t("filtered_games")} (${total} ${LPDB_i18n.t("total")}) &middot; ${clickHint}`;
    }
  }

  /**
   * Compute page number array with ellipsis for pagination.
   * @param {number} current - Current page (1-based)
   * @param {number} total - Total pages
   * @returns {Array<number|string>}
   */
  function getPageNumbers(current, total) {
    if (total <= 7) {
      return Array.from({ length: total }, (_, i) => i + 1);
    }
    const pages = new Set([1, total]);
    for (let i = current - 1; i <= current + 1; i++) {
      if (i >= 1 && i <= total) pages.add(i);
    }
    const sorted = [...pages].sort((a, b) => a - b);
    const result = [];
    for (let i = 0; i < sorted.length; i++) {
      if (i > 0 && sorted[i] - sorted[i - 1] > 1) {
        result.push("...");
      }
      result.push(sorted[i]);
    }
    return result;
  }

  /**
   * Render pagination controls.
   * @param {number} currentPage - Current page (1-based)
   * @param {number} totalPages
   * @param {number} pageSize
   */
  function renderPagination(currentPage, totalPages, pageSize) {
    const container = document.getElementById("paginationControls");
    if (totalPages <= 1) {
      container.innerHTML = "";
      return;
    }

    const pages = getPageNumbers(currentPage, totalPages);
    let html = `<div class="lpdb-pagination">`;
    html += `<button class="lpdb-page-btn" onclick="LPDB.filters.setPage(${currentPage - 1})"${currentPage <= 1 ? " disabled" : ""}>${LPDB_i18n.t("page_prev")}</button>`;

    for (const p of pages) {
      if (p === "...") {
        html += `<span class="lpdb-page-ellipsis">&hellip;</span>`;
      } else {
        const active = p === currentPage ? " lpdb-page-btn--active" : "";
        html += `<button class="lpdb-page-btn${active}" onclick="LPDB.filters.setPage(${p})">${p}</button>`;
      }
    }

    html += `<button class="lpdb-page-btn" onclick="LPDB.filters.setPage(${currentPage + 1})"${currentPage >= totalPages ? " disabled" : ""}>${LPDB_i18n.t("page_next")}</button>`;
    html += `</div>`;

    // Page size selector
    const sizes = [25, 50, 100, 250];
    html += `<div class="lpdb-page-size">`;
    html += `<span>${LPDB_i18n.t("per_page")}</span>`;
    html += `<select class="lpdb-page-size-select" onchange="LPDB.filters.setPageSize(Number(this.value))">`;
    for (const s of sizes) {
      html += `<option value="${s}"${s === pageSize ? " selected" : ""}>${s}</option>`;
    }
    html += `</select></div>`;

    container.innerHTML = html;
  }

  return { renderTable, updateStats, updateResultsCount, renderPagination, toggleRow, expandAll, collapseAll, expandedRows };
})();
