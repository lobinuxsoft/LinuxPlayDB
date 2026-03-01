/**
 * LinuxPlayDB — Main Application
 * Initializes all modules and provides the global LPDB namespace.
 */

const LPDB = (() => {
  let _currentGames = [];

  /**
   * Initialize the application.
   */
  async function init() {
    try {
      // Load i18n first
      await LPDB_i18n.init();

      // Load database
      await LPDB_DB.init();

      // Hide loading, show content
      document.getElementById("loadingOverlay").style.display = "none";
      document.getElementById("mainContent").style.display = "block";

      // Initial render
      LPDB_Filters.apply();

      // Update footer
      const sources = LPDB_DB.getDataSources();
      const seedSource = sources.find((s) => s.source_id === "seed");
      if (seedSource && seedSource.last_updated) {
        const date = seedSource.last_updated.split("T")[0];
        document.getElementById("lastUpdate").textContent = `Data: ${date}`;
      }

      console.log("[LinuxPlayDB] Ready");
    } catch (err) {
      console.error("[LinuxPlayDB] Init failed:", err);
      const loading = document.getElementById("loadingOverlay");
      loading.innerHTML = `
        <div style="color: var(--red); text-align: center; padding: 2rem;">
          <h2 style="margin-bottom: 0.5rem;">${LPDB_i18n.t("error_loading")}</h2>
          <p style="color: var(--text-muted);">${err.message}</p>
          <p style="color: var(--text-muted); font-size: 0.75rem; margin-top: 1rem;">
            ${LPDB_i18n.t("error_hint")}
          </p>
        </div>
      `;
    }
  }

  /**
   * Sort table by column.
   * @param {string} key
   */
  function sort(key) {
    const state = LPDB_Filters.state;
    if (state.sortKey === key) {
      state.sortAsc = !state.sortAsc;
    } else {
      state.sortKey = key;
      state.sortAsc = true;
    }

    // Update sort arrow visuals
    document.querySelectorAll(".lpdb-table th").forEach((th) => th.classList.remove("sorted"));
    const th = document.querySelector(`.lpdb-table th[data-sort="${key}"]`);
    if (th) {
      th.classList.add("sorted");
      th.querySelector(".sort-arrow").textContent = state.sortAsc ? "\u25B2" : "\u25BC";
    }

    LPDB_Filters.apply();
  }

  /**
   * Toggle a game row's expanded detail view.
   * @param {number} appId
   */
  function toggleRow(appId) {
    LPDB_Render.toggleRow(appId);
  }

  /**
   * Expand all visible rows.
   */
  function expandAll() {
    LPDB_Render.expandAll(_currentGames);
  }

  /**
   * Collapse all rows.
   */
  function collapseAll() {
    LPDB_Render.collapseAll();
  }

  /**
   * Export data in specified format.
   * @param {string} format - "csv" or "json"
   */
  function exportData(format) {
    if (!_currentGames || _currentGames.length === 0) {
      showToast(LPDB_i18n.t("no_data_export"));
      return;
    }

    if (format === "csv") {
      LPDB_Export.exportCSV(_currentGames);
    } else {
      LPDB_Export.exportJSON(_currentGames);
    }

    showToast(`${LPDB_i18n.t("exported")} ${_currentGames.length} ${LPDB_i18n.t("games")} (${format.toUpperCase()})`);
  }

  /**
   * Copy a code block's text to clipboard.
   * @param {HTMLElement} el
   */
  function copyCmd(el) {
    const label = el.dataset.copyLabel;
    const text = el.textContent.replace(label, "").replace("copied!", "").trim();
    navigator.clipboard.writeText(text).then(() => {
      el.dataset.copyLabel = "copied!";
      el.classList.add("copied");
      setTimeout(() => {
        el.dataset.copyLabel = "click to copy";
        el.classList.remove("copied");
      }, 1500);
    });
  }

  /**
   * Copy inline text to clipboard.
   * @param {HTMLElement} el
   */
  function copyText(el) {
    navigator.clipboard.writeText(el.textContent.trim()).then(() => {
      const origBorder = el.style.borderColor;
      el.style.borderColor = "var(--green)";
      setTimeout(() => {
        el.style.borderColor = origBorder;
      }, 1000);
    });
  }

  /**
   * Show a toast notification.
   * @param {string} message
   * @param {number} duration - ms
   */
  function showToast(message, duration = 2500) {
    // Remove existing toast
    const existing = document.querySelector(".lpdb-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = "lpdb-toast";
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("hiding");
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  return {
    init,
    sort,
    toggleRow,
    expandAll,
    collapseAll,
    exportData,
    copyCmd,
    copyText,
    showToast,
    filters: LPDB_Filters,
    i18n: LPDB_i18n,
    get _currentGames() { return _currentGames; },
    set _currentGames(v) { _currentGames = v; },
  };
})();

// Boot
document.addEventListener("DOMContentLoaded", LPDB.init);
