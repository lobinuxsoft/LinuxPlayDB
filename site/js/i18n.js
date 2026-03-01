/**
 * LinuxPlayDB — i18n Module
 * Handles language switching between ES and EN.
 * Translations are embedded inline so the site works from file:// too.
 */

const LPDB_i18n = (() => {
  let currentLang = "es";

  const strings = {
    es: {
      subtitle: "Base de datos Steam RT/PT \u00b7 AMD + NVIDIA + Linux + Handhelds",
      loading: "Cargando base de datos...",
      stat_total: "Total RT",
      stat_pt: "Path Tracing",
      stat_amd: "AMD OK",
      stat_broken: "Broken Linux",
      stat_cmd: "Necesitan CMD",
      stat_fsr4: "FSR4",
      bazzite_title: "Bazzite Linux \u2014 RT Quick Reference (RADV + Mesa 26.0)",
      bazzite_verify: "Verificar setup",
      bazzite_rt_vars: "Variables RT",
      filter_search: "Buscar",
      search_placeholder: "Nombre del juego...",
      filter_all: "Todos",
      filter_works: "Funciona",
      filter_cmd: "Necesita CMD",
      filter_verified: "Verificado",
      filter_playable: "Jugable",
      filter_unsupported: "No soportado",
      legend: "Leyenda:",
      legend_compatible: "Compatible",
      legend_needs_cmd: "Necesita comando",
      legend_broken: "Roto",
      export_csv: "Exportar CSV",
      export_json: "Exportar JSON",
      expand_all: "Expandir todo",
      collapse_all: "Colapsar todo",
      col_game: "Juego",
      col_device: "Dispositivo",
      showing: "Mostrando",
      of: "de",
      games: "juegos",
      click_hint: "Click en un juego para ver comandos Linux",
      status_works: "Funciona",
      status_cmd: "Necesita CMD",
      see_notes: "ver notas",
      detail_launch: "Opciones de lanzamiento",
      detail_env: "Variables de entorno",
      detail_notes: "Notas",
      detail_links: "Links \u00fatiles",
      detail_devices: "Compatibilidad de dispositivos",
      detail_fsr4_hint: "Soportado. Agregar PROTON_FSR4_UPGRADE=1 SteamDeck=0",
      detail_no_data: "Sin datos de compatibilidad aún. Buscá info en:",
      filter_pt: "Path Tracing",
      filter_rt_only: "Solo RT",
      filter_amd_ok: "AMD OK",
      filter_amd_pt: "AMD PT",
      filter_nvidia_only: "Solo NVIDIA",
      filter_broken: "Roto",
      legend_pt: "Path Tracing",
      legend_rt: "Ray Tracing",
      legend_rr: "Reconstrucción de Rayos",
      legend_mfg: "Multi Frame Gen",
      legend_fsr4: "AMD FSR4",
      legend_nvidia_excl: "Exclusivo NVIDIA",
      col_type: "Tipo",
      col_tech: "Tecnología",
      col_linux: "Linux",
      col_cmd: "CMD",
      footer_sources: "Fuentes",
      error_loading: "Error cargando la base de datos",
      error_hint: "Verifica que db_inline.js est\u00e9 generado. Ejecuta: python scripts/build_db.py",
      no_data_export: "No hay datos para exportar",
      exported: "Exportados",
    },
    en: {
      subtitle: "Steam RT/PT Database \u00b7 AMD + NVIDIA + Linux + Handhelds",
      loading: "Loading database...",
      stat_total: "Total RT",
      stat_pt: "Path Tracing",
      stat_amd: "AMD OK",
      stat_broken: "Broken Linux",
      stat_cmd: "Need CMD",
      stat_fsr4: "FSR4",
      bazzite_title: "Bazzite Linux \u2014 RT Quick Reference (RADV + Mesa 26.0)",
      bazzite_verify: "Verify Setup",
      bazzite_rt_vars: "RT Variables",
      filter_search: "Search",
      search_placeholder: "Game name...",
      filter_all: "All",
      filter_works: "Works",
      filter_cmd: "Needs CMD",
      filter_verified: "Verified",
      filter_playable: "Playable",
      filter_unsupported: "Unsupported",
      legend: "Legend:",
      legend_compatible: "Compatible",
      legend_needs_cmd: "Needs command",
      legend_broken: "Broken",
      export_csv: "Export CSV",
      export_json: "Export JSON",
      expand_all: "Expand all",
      collapse_all: "Collapse all",
      col_game: "Game",
      col_device: "Device",
      showing: "Showing",
      of: "of",
      games: "games",
      click_hint: "Click on a game to see Linux commands",
      status_works: "Works",
      status_cmd: "Needs CMD",
      see_notes: "see notes",
      detail_launch: "Launch Options",
      detail_env: "Environment Variables",
      detail_notes: "Notes",
      detail_links: "Useful Links",
      detail_devices: "Device Compatibility",
      detail_fsr4_hint: "Supported. Add PROTON_FSR4_UPGRADE=1 SteamDeck=0",
      detail_no_data: "No compatibility data yet. Search for info on:",
      filter_pt: "Path Tracing",
      filter_rt_only: "RT Only",
      filter_amd_ok: "AMD OK",
      filter_amd_pt: "AMD PT",
      filter_nvidia_only: "NVIDIA Only",
      filter_broken: "Broken",
      legend_pt: "Path Tracing",
      legend_rt: "Ray Tracing",
      legend_rr: "Ray Reconstruction",
      legend_mfg: "Multi Frame Gen",
      legend_fsr4: "AMD FSR4",
      legend_nvidia_excl: "NVIDIA Exclusive",
      col_type: "Type",
      col_tech: "Tech",
      col_linux: "Linux",
      col_cmd: "CMD",
      footer_sources: "Sources",
      error_loading: "Error loading database",
      error_hint: "Make sure db_inline.js is generated. Run: python scripts/build_db.py",
      no_data_export: "No data to export",
      exported: "Exported",
    },
  };

  /**
   * Initialize i18n (synchronous — no fetch needed).
   */
  async function init() {
    const saved = localStorage.getItem("lpdb_lang");
    if (saved && strings[saved]) {
      currentLang = saved;
    }
    applyToDOM();
    updateToggleButton();
  }

  /**
   * Get current language.
   * @returns {string}
   */
  function lang() {
    return currentLang;
  }

  /**
   * Get a translated string by key.
   * @param {string} key
   * @returns {string}
   */
  function t(key) {
    return (strings[currentLang] && strings[currentLang][key])
      || (strings.en && strings.en[key])
      || key;
  }

  /**
   * Toggle between ES and EN.
   */
  function toggle() {
    currentLang = currentLang === "es" ? "en" : "es";
    localStorage.setItem("lpdb_lang", currentLang);
    applyToDOM();
    updateToggleButton();
    if (typeof LPDB_Filters !== "undefined") {
      LPDB_Filters.apply();
    }
  }

  /**
   * Apply translations to all [data-i18n] elements.
   */
  function applyToDOM() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      const val = t(key);
      if (val !== key) el.textContent = val;
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-i18n-placeholder");
      const val = t(key);
      if (val !== key) el.placeholder = val;
    });
    document.documentElement.lang = currentLang;
  }

  function updateToggleButton() {
    const btn = document.getElementById("langToggle");
    if (btn) btn.textContent = currentLang.toUpperCase();
  }

  return { init, lang, t, toggle };
})();
