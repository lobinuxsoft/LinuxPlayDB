/**
 * LinuxPlayDB — sql.js Database Wrapper
 *
 * Loading strategy (works from file:// AND http://):
 *  1. WASM: try local lib/ first, fall back to CDN
 *  2. DB:   try fetch data/linuxplaydb.db first, fall back to
 *           embedded base64 in db_inline.js (LPDB_INLINE_DB global)
 */

const LPDB_DB = (() => {
  let db = null;

  const CDN_WASM = "https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.11.0/sql-wasm.wasm";

  /**
   * Initialize sql.js and load the database.
   */
  async function init() {
    // 1. Init sql.js — try local WASM, fall back to CDN
    let SQL;
    try {
      SQL = await initSqlJs({ locateFile: (file) => `lib/${file}` });
    } catch (_) {
      console.warn("[DB] Local WASM failed, trying CDN...");
      SQL = await initSqlJs({ locateFile: () => CDN_WASM });
    }

    // 2. Load database — try fetch, fall back to inline base64
    let dbBytes;
    try {
      const res = await fetch("data/linuxplaydb.db");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      dbBytes = new Uint8Array(await res.arrayBuffer());
    } catch (_) {
      console.warn("[DB] Fetch failed, using inline database...");
      if (typeof LPDB_INLINE_DB === "undefined") {
        throw new Error("No database available. Run: python scripts/build_db.py");
      }
      dbBytes = base64ToUint8Array(LPDB_INLINE_DB);
    }

    db = new SQL.Database(dbBytes);
    console.log("[LinuxPlayDB] Database loaded");
  }

  /**
   * Decode a base64 string to Uint8Array.
   */
  function base64ToUint8Array(b64) {
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) {
      arr[i] = bin.charCodeAt(i);
    }
    return arr;
  }

  /**
   * Execute a SQL query and return results as an array of objects.
   */
  function query(sql, params = []) {
    if (!db) throw new Error("Database not initialized");
    const stmt = db.prepare(sql);
    stmt.bind(params);
    const results = [];
    while (stmt.step()) {
      results.push(stmt.getAsObject());
    }
    stmt.free();
    return results;
  }

  /**
   * Execute a SQL query and return the first result.
   */
  function queryOne(sql, params = []) {
    const results = query(sql, params);
    return results.length > 0 ? results[0] : null;
  }

  /**
   * Get a scalar value (first column of first row).
   */
  function scalar(sql, params = []) {
    if (!db) throw new Error("Database not initialized");
    const stmt = db.prepare(sql);
    stmt.bind(params);
    let value = null;
    if (stmt.step()) value = stmt.get()[0];
    stmt.free();
    return value;
  }

  /**
   * Get filtered games with joined graphics and linux compat data.
   */
  function getGames(filters = {}) {
    let where = ["1=1"];
    let params = [];

    if (filters.search) {
      where.push("g.name LIKE ?");
      params.push(`%${filters.search}%`);
    }
    if (filters.rtType === "pt") {
      where.push("gf.rt_type = 'pt'");
    } else if (filters.rtType === "rt") {
      where.push("gf.rt_type = 'rt'");
    }
    if (filters.tech && filters.tech.length > 0) {
      for (const t of filters.tech) {
        where.push(`gf.${t} = 1`);
      }
    }
    if (filters.amd === "ok") {
      where.push("gf.amd_status IN ('amd_ok', 'amd_pt', 'amd_rt_only')");
    } else if (filters.amd === "pt") {
      where.push("gf.amd_status = 'amd_pt'");
    } else if (filters.amd === "nvidia_only") {
      where.push("gf.amd_status = 'nvidia_only'");
    }
    if (filters.linux && filters.linux !== "all") {
      where.push("lc.linux_status = ?");
      params.push(filters.linux);
    }
    if (filters.deck && filters.deck !== "all") {
      where.push("lc.deck_status = ?");
      params.push(filters.deck);
    }

    let orderBy = "g.name ASC";
    if (filters.sortKey) {
      const dir = filters.sortAsc ? "ASC" : "DESC";
      const sortMap = {
        name: `g.name ${dir}`,
        rt_type: `CASE gf.rt_type WHEN 'pt' THEN 0 ELSE 1 END ${dir}, g.name ASC`,
        amd_status: `CASE gf.amd_status WHEN 'amd_pt' THEN 0 WHEN 'amd_ok' THEN 1 WHEN 'amd_rt_only' THEN 2 WHEN 'nvidia_only' THEN 3 ELSE 4 END ${dir}, g.name ASC`,
        linux_status: `CASE lc.linux_status WHEN 'works' THEN 0 WHEN 'cmd' THEN 1 WHEN 'check' THEN 2 WHEN 'broken' THEN 3 ELSE 4 END ${dir}, g.name ASC`,
      };
      orderBy = sortMap[filters.sortKey] || orderBy;
    }

    return query(`
      SELECT
        g.app_id, g.name, g.steam_url, g.header_image,
        gf.rt_type, gf.dlss_sr, gf.dlss_fg, gf.dlss_rr, gf.dlss_mfg,
        gf.dlaa, gf.fsr4, gf.fsr3, gf.fsr2, gf.xess,
        gf.amd_status, gf.notes_en AS gf_notes_en, gf.notes_es AS gf_notes_es,
        lc.native_linux, lc.protondb_tier, lc.proton_version, lc.deck_status,
        lc.linux_status, lc.launch_options, lc.env_vars,
        lc.anticheat, lc.anticheat_linux,
        lc.notes_en AS lc_notes_en, lc.notes_es AS lc_notes_es
      FROM games g
      LEFT JOIN graphics_features gf ON g.app_id = gf.app_id
      LEFT JOIN linux_compat lc ON g.app_id = lc.app_id
      WHERE ${where.join(" AND ")}
      ORDER BY ${orderBy}
    `, params);
  }

  function getStats(filters = {}) {
    const games = getGames(filters);
    return {
      total: games.length,
      pt: games.filter((g) => g.rt_type === "pt").length,
      amd: games.filter((g) => ["amd_ok", "amd_pt", "amd_rt_only"].includes(g.amd_status)).length,
      broken: games.filter((g) => g.linux_status === "broken").length,
      cmd: games.filter((g) => g.linux_status === "cmd").length,
      fsr4: games.filter((g) => g.fsr4 === 1).length,
    };
  }

  function getLinks(appId) {
    return query("SELECT url, title_en, title_es, source, link_type FROM useful_links WHERE app_id = ?", [appId]);
  }

  function getDeviceCompat(appId) {
    return query(
      `SELECT dc.*, d.name AS device_name, d.manufacturer, d.gpu, d.gpu_arch, d.gpu_cus
       FROM device_compat dc JOIN devices d ON dc.device_id = d.device_id
       WHERE dc.app_id = ? ORDER BY d.manufacturer, d.name`, [appId]);
  }

  function getDevices() {
    return query("SELECT * FROM devices ORDER BY manufacturer, name");
  }

  function getDataSources() {
    return query("SELECT * FROM data_sources");
  }

  return { init, query, queryOne, scalar, getGames, getStats, getLinks, getDeviceCompat, getDevices, getDataSources };
})();
