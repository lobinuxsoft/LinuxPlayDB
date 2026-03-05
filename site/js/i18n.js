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
      legend_fg: "Generación de Cuadros",
      legend_sr: "Super Resolución",
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

      // Filter chip tooltips
      tip_filter_all: "Mostrar todos los juegos sin filtro",
      tip_filter_pt: "Solo juegos con Path Tracing completo",
      tip_filter_rt_only: "Solo juegos con Ray Tracing (sin PT)",
      tip_dlss_rr: "DLSS Ray Reconstruction: reemplaza el denoiser tradicional con IA",
      tip_dlss_mfg: "DLSS Multi Frame Generation: genera multiples cuadros extra via IA",
      tip_dlss_fg: "DLSS Frame Generation: genera un cuadro extra entre cada cuadro real",
      tip_dlss_sr: "DLSS Super Resolution: upscaling de resolucion via IA",
      tip_fsr4: "AMD FSR4 Redstone: upscaling de nueva generacion para RDNA4",
      tip_amd_ok: "RT/PT funciona completamente en GPUs AMD",
      tip_amd_pt: "Path Tracing funciona en AMD (via VKD3D u otro metodo)",
      tip_nvidia_only: "Requiere GPU NVIDIA (RTX Remix, OptiX, extensiones exclusivas)",
      tip_linux_works: "Funciona en Linux sin configuracion extra",
      tip_linux_cmd: "Necesita comando de lanzamiento o variables de entorno en Linux",
      tip_linux_broken: "Roto o no funcional en Linux actualmente",
      tip_deck_verified: "Verificado por Valve para Steam Deck",
      tip_deck_playable: "Jugable en Steam Deck con ajustes",
      tip_deck_unsupported: "No soportado en Steam Deck",

      // Badge tooltips
      badge_tip_pt: "Path Tracing: iluminacion global completa por trazado de rayos",
      badge_tip_rt: "Ray Tracing: reflejos, sombras o GI parcial por trazado de rayos",
      badge_tip_rr: "Ray Reconstruction: denoiser IA de NVIDIA reemplaza el tradicional",
      badge_tip_mfg: "Multi Frame Gen: genera multiples cuadros extra via IA",
      badge_tip_fg: "Frame Generation: genera cuadros intermedios para mayor fluidez",
      badge_tip_sr: "Super Resolution: upscaling IA para mayor rendimiento",
      badge_tip_fsr4: "FSR4 Redstone: upscaling AMD de nueva generacion (RDNA4)",
      badge_tip_amd_ok: "AMD compatible: RT/PT funciona correctamente en GPUs AMD",
      badge_tip_amd_pt: "AMD Path Tracing: PT funciona en AMD via VKD3D u otro metodo",
      badge_tip_amd_rt_only: "AMD solo RT: Ray Tracing funciona, Path Tracing no disponible en AMD",
      badge_tip_nvidia_only: "Exclusivo NVIDIA: requiere RTX (Remix, OptiX, extensiones Vulkan RT)",
      badge_tip_works: "Funciona en Linux sin configuracion adicional",
      badge_tip_cmd: "Necesita comando de lanzamiento o variables de entorno",
      badge_tip_broken: "Roto o no funcional en Linux actualmente",

      // Help panel
      help_title: "Guia rapida",
      help_what: "Que es LinuxPlayDB?",
      help_what_desc: "Base de datos de juegos Steam con Ray Tracing y Path Tracing. Muestra compatibilidad AMD/NVIDIA, estado en Linux, y soporte para handhelds.",
      help_rt_pt: "RT vs PT",
      help_rt_pt_desc: "Ray Tracing (RT) agrega reflejos y sombras realistas. Path Tracing (PT) simula TODA la iluminacion via rayos, resultado mas cinematografico pero mas costoso.",
      help_filters: "Filtros Tech",
      help_filters_desc: "RR = Ray Reconstruction, FG = Frame Generation, SR = Super Resolution, MFG = Multi Frame Gen, FSR4 = AMD FSR4 Redstone.",
      help_cmd: "CMD (Comandos)",
      help_cmd_desc: "Algunos juegos necesitan opciones de lanzamiento o variables de entorno en Steam para que RT funcione en Linux. Haz click en un juego para ver los comandos.",
      help_broken: "Broken (Roto)",
      help_broken_desc: "Juegos donde RT/PT no funciona en Linux actualmente. Puede ser por anti-cheat, shaders incompatibles, o falta de soporte Vulkan RT.",
      help_amd: "AMD Status",
      help_amd_desc: "AMD OK = funciona, AMD PT = path tracing funciona via VKD3D, NVIDIA Only = requiere GPU NVIDIA por extensiones exclusivas.",

      // Expanded legend descriptions
      legend_amd_ok_desc: "RT/PT funciona en AMD",
      legend_amd_pt_desc: "Path Tracing funciona en AMD",
      legend_amd_rt_only_desc: "Solo RT funciona en AMD",
      legend_nvidia_only_desc: "Requiere GPU NVIDIA",
      legend_cmd_desc: "Necesita comando de lanzamiento",
      legend_broken_desc: "Roto en Linux",

      // Pagination
      page_prev: "Anterior",
      page_next: "Siguiente",
      per_page: "Por pagina",
      filtered_games: "juegos filtrados",
      total: "total",

      // Mobile scroll hint
      table_scroll_hint: "Desliza para ver mas columnas",
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
      legend_fg: "Frame Generation",
      legend_sr: "Super Resolution",
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

      // Filter chip tooltips
      tip_filter_all: "Show all games without filtering",
      tip_filter_pt: "Only games with full Path Tracing",
      tip_filter_rt_only: "Only games with Ray Tracing (no PT)",
      tip_dlss_rr: "DLSS Ray Reconstruction: replaces traditional denoiser with AI",
      tip_dlss_mfg: "DLSS Multi Frame Generation: generates multiple extra frames via AI",
      tip_dlss_fg: "DLSS Frame Generation: generates an extra frame between each real frame",
      tip_dlss_sr: "DLSS Super Resolution: AI-powered resolution upscaling",
      tip_fsr4: "AMD FSR4 Redstone: next-gen upscaling for RDNA4",
      tip_amd_ok: "RT/PT fully works on AMD GPUs",
      tip_amd_pt: "Path Tracing works on AMD (via VKD3D or other method)",
      tip_nvidia_only: "Requires NVIDIA GPU (RTX Remix, OptiX, exclusive extensions)",
      tip_linux_works: "Works on Linux without extra configuration",
      tip_linux_cmd: "Needs launch command or environment variables on Linux",
      tip_linux_broken: "Broken or non-functional on Linux currently",
      tip_deck_verified: "Verified by Valve for Steam Deck",
      tip_deck_playable: "Playable on Steam Deck with adjustments",
      tip_deck_unsupported: "Not supported on Steam Deck",

      // Badge tooltips
      badge_tip_pt: "Path Tracing: full global illumination via ray tracing",
      badge_tip_rt: "Ray Tracing: partial reflections, shadows, or GI via ray tracing",
      badge_tip_rr: "Ray Reconstruction: NVIDIA AI denoiser replaces traditional one",
      badge_tip_mfg: "Multi Frame Gen: generates multiple extra frames via AI",
      badge_tip_fg: "Frame Generation: generates intermediate frames for smoother gameplay",
      badge_tip_sr: "Super Resolution: AI upscaling for higher performance",
      badge_tip_fsr4: "FSR4 Redstone: AMD next-gen upscaling (RDNA4)",
      badge_tip_amd_ok: "AMD compatible: RT/PT works correctly on AMD GPUs",
      badge_tip_amd_pt: "AMD Path Tracing: PT works on AMD via VKD3D or other method",
      badge_tip_amd_rt_only: "AMD RT only: Ray Tracing works, Path Tracing not available on AMD",
      badge_tip_nvidia_only: "NVIDIA exclusive: requires RTX (Remix, OptiX, Vulkan RT extensions)",
      badge_tip_works: "Works on Linux without extra configuration",
      badge_tip_cmd: "Needs launch command or environment variables",
      badge_tip_broken: "Broken or non-functional on Linux currently",

      // Help panel
      help_title: "Quick guide",
      help_what: "What is LinuxPlayDB?",
      help_what_desc: "Database of Steam games with Ray Tracing and Path Tracing. Shows AMD/NVIDIA compatibility, Linux status, and handheld support.",
      help_rt_pt: "RT vs PT",
      help_rt_pt_desc: "Ray Tracing (RT) adds realistic reflections and shadows. Path Tracing (PT) simulates ALL lighting via rays, more cinematic but more demanding.",
      help_filters: "Tech Filters",
      help_filters_desc: "RR = Ray Reconstruction, FG = Frame Generation, SR = Super Resolution, MFG = Multi Frame Gen, FSR4 = AMD FSR4 Redstone.",
      help_cmd: "CMD (Commands)",
      help_cmd_desc: "Some games need launch options or environment variables in Steam for RT to work on Linux. Click a game to see the commands.",
      help_broken: "Broken",
      help_broken_desc: "Games where RT/PT doesn't work on Linux currently. May be due to anti-cheat, incompatible shaders, or missing Vulkan RT support.",
      help_amd: "AMD Status",
      help_amd_desc: "AMD OK = works, AMD PT = path tracing works via VKD3D, NVIDIA Only = requires NVIDIA GPU for exclusive extensions.",

      // Expanded legend descriptions
      legend_amd_ok_desc: "RT/PT works on AMD",
      legend_amd_pt_desc: "Path Tracing works on AMD",
      legend_amd_rt_only_desc: "RT only works on AMD",
      legend_nvidia_only_desc: "Requires NVIDIA GPU",
      legend_cmd_desc: "Needs launch command",
      legend_broken_desc: "Broken on Linux",

      // Pagination
      page_prev: "Prev",
      page_next: "Next",
      per_page: "Per page",
      filtered_games: "filtered games",
      total: "total",

      // Mobile scroll hint
      table_scroll_hint: "Swipe to see more columns",
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
      LPDB_Filters.apply(false);
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
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const key = el.getAttribute("data-i18n-title");
      const val = t(key);
      if (val !== key) el.title = val;
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
