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
    page: 1,
    pageSize: 25,
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

    // Update chip visual state and aria-pressed
    document.querySelectorAll(`.lpdb-chip[data-group="${group}"]`).forEach((c) => {
      c.className = "lpdb-chip";
      c.setAttribute("aria-pressed", "false");
    });
    el.classList.add(chipStyles[group] || "active");
    el.setAttribute("aria-pressed", "true");

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
      el.setAttribute("aria-pressed", "false");
    } else {
      state.tech.push(value);
      el.classList.add("active-purple");
      el.setAttribute("aria-pressed", "true");
    }
    apply();
  }

  /**
   * Apply all current filters and re-render.
   * @param {boolean} resetPage - Reset to page 1 (default true, false for page navigation)
   */
  function apply(resetPage = true) {
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

    const allGames = LPDB_DB.getGames(filters);
    const stats = {
      total: allGames.length,
      pt: allGames.filter((g) => g.rt_type === "pt").length,
      amd: allGames.filter((g) => ["amd_ok", "amd_pt", "amd_rt_only"].includes(g.amd_status)).length,
      broken: allGames.filter((g) => g.linux_status === "broken").length,
      cmd: allGames.filter((g) => g.linux_status === "cmd").length,
      fsr4: allGames.filter((g) => g.fsr4 === 1).length,
    };

    // Pagination
    if (resetPage) state.page = 1;
    const totalPages = Math.max(1, Math.ceil(allGames.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;

    const start = (state.page - 1) * state.pageSize;
    const end = Math.min(start + state.pageSize, allGames.length);
    const pageGames = allGames.slice(start, end);

    LPDB_Render.renderTable(pageGames);
    LPDB_Render.updateStats(stats);

    const dbTotal = LPDB_DB.scalar("SELECT COUNT(*) FROM games");
    LPDB_Render.updateResultsCount(allGames.length, dbTotal, state.page, totalPages, allGames.length > 0 ? start + 1 : 0, end);
    LPDB_Render.renderPagination(state.page, totalPages, state.pageSize);

    // Store full filtered set for export, page slice for expandAll
    LPDB._currentGames = allGames;
    LPDB._currentPageGames = pageGames;
  }

  /**
   * Navigate to a specific page.
   * @param {number} page
   */
  function setPage(page) {
    state.page = page;
    apply(false);
  }

  /**
   * Change page size and reset to page 1.
   * @param {number} size
   */
  function setPageSize(size) {
    state.pageSize = size;
    state.page = 1;
    apply(false);
  }

  /**
   * Get the current filter state (for export, etc).
   * @returns {Object}
   */
  function getState() {
    return { ...state };
  }

  return { state, set, toggle, apply, setPage, setPageSize, getState };
})();
