/**
 * LinuxPlayDB — Filters Module
 * Handles search, chip filters, and sort state.
 */

const LPDB_Filters = (() => {
  const state = {
    search: "",
    rtType: "all",
    tech: [],
    amd: "all",
    linux: "all",
    deck: "all",
    sortKey: "name",
    sortAsc: true,
  };

  const chipStyles = {
    rtType: "active",
    amd: "active-green",
    linux: "active",
    deck: "active",
  };

  /**
   * Set a single-select filter chip.
   * @param {HTMLElement} el - Clicked chip element
   */
  function set(el) {
    const group = el.dataset.group;
    const value = el.dataset.value;
    state[group] = value;

    // Update chip visual state
    document.querySelectorAll(`.lpdb-chip[data-group="${group}"]`).forEach((c) => {
      c.className = "lpdb-chip";
    });
    el.classList.add(chipStyles[group] || "active");

    apply();
  }

  /**
   * Toggle a multi-select filter chip (tech features).
   * @param {HTMLElement} el
   */
  function toggle(el) {
    const value = el.dataset.value;
    const idx = state.tech.indexOf(value);
    if (idx >= 0) {
      state.tech.splice(idx, 1);
      el.className = "lpdb-chip";
    } else {
      state.tech.push(value);
      el.classList.add("active-purple");
    }
    apply();
  }

  /**
   * Apply all current filters and re-render.
   */
  function apply() {
    state.search = (document.getElementById("searchInput").value || "").trim();

    const filters = {
      search: state.search || null,
      rtType: state.rtType,
      tech: state.tech.length > 0 ? state.tech : null,
      amd: state.amd,
      linux: state.linux,
      deck: state.deck,
      sortKey: state.sortKey,
      sortAsc: state.sortAsc,
    };

    const games = LPDB_DB.getGames(filters);
    const stats = {
      total: games.length,
      pt: games.filter((g) => g.rt_type === "pt").length,
      amd: games.filter((g) => ["amd_ok", "amd_pt", "amd_rt_only"].includes(g.amd_status)).length,
      broken: games.filter((g) => g.linux_status === "broken").length,
      cmd: games.filter((g) => g.linux_status === "cmd").length,
      fsr4: games.filter((g) => g.fsr4 === 1).length,
    };

    LPDB_Render.renderTable(games);
    LPDB_Render.updateStats(stats);
    LPDB_Render.updateResultsCount(games.length, LPDB_DB.scalar("SELECT COUNT(*) FROM games"));

    // Store for export
    LPDB._currentGames = games;
  }

  /**
   * Get the current filter state (for export, etc).
   * @returns {Object}
   */
  function getState() {
    return { ...state };
  }

  return { state, set, toggle, apply, getState };
})();
