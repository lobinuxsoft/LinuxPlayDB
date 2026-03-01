/**
 * LinuxPlayDB — Export Module
 * Handles CSV and JSON export of filtered data.
 */

const LPDB_Export = (() => {
  /**
   * Download data as a file.
   * @param {string} content
   * @param {string} filename
   * @param {string} mimeType
   */
  function download(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export filtered games as CSV.
   * @param {Array<Object>} games
   */
  function exportCSV(games) {
    const header = "Name,RT Type,AMD Status,Linux Status,Deck Status,FSR4,ProtonDB,Proton Version,Launch Command,Notes\n";
    const rows = games.map((g) => {
      const notes = (g.lc_notes_en || "").replace(/"/g, '""');
      const cmd = (g.launch_options || "").replace(/"/g, '""');
      return `"${g.name}","${g.rt_type || ""}","${g.amd_status || ""}","${g.linux_status || ""}","${g.deck_status || ""}",${g.fsr4 ? "true" : "false"},"${g.protondb_tier || ""}","${g.proton_version || ""}","${cmd}","${notes}"`;
    }).join("\n");

    download(header + rows, "linuxplaydb_export.csv", "text/csv;charset=utf-8");
  }

  /**
   * Export filtered games as JSON.
   * @param {Array<Object>} games
   */
  function exportJSON(games) {
    const data = games.map((g) => ({
      name: g.name,
      app_id: g.app_id,
      rt_type: g.rt_type,
      amd_status: g.amd_status,
      linux_status: g.linux_status,
      deck_status: g.deck_status,
      protondb_tier: g.protondb_tier,
      fsr4: !!g.fsr4,
      dlss: {
        sr: !!g.dlss_sr,
        fg: !!g.dlss_fg,
        rr: !!g.dlss_rr,
        mfg: !!g.dlss_mfg,
      },
      proton_version: g.proton_version || null,
      launch_options: g.launch_options || null,
      notes: g.lc_notes_en || null,
    }));

    download(
      JSON.stringify(data, null, 2),
      "linuxplaydb_export.json",
      "application/json"
    );
  }

  return { exportCSV, exportJSON };
})();
