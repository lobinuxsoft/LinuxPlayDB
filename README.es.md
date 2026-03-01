# LinuxPlayDB

Base de datos de juegos de Steam con compatibilidad de Ray Tracing / Path Tracing, soporte AMD y NVIDIA, comandos Linux/Proton, y compatibilidad con dispositivos handheld.

[**Read in English**](README.md)

## Funcionalidades

- **Base de datos RT/PT**: ~200+ juegos con datos de Ray Tracing y Path Tracing
- **Compatibilidad AMD**: Estado por juego — funciona, solo RT, o exclusivo NVIDIA
- **Comandos Linux**: Opciones de lanzamiento Steam, variables de entorno, versiones de Proton
- **Soporte Handhelds**: 40+ dispositivos (Steam Deck, ROG Ally, Legion Go, etc.)
- **Referencia Bazzite**: Guia rapida de RT en Bazzite Linux (RADV + Mesa 26)
- **Offline-First**: Base SQLite corre en el navegador via WASM
- **i18n**: Disponible en Español e Ingles
- **Exportar**: CSV y JSON de datos filtrados
- **Auto-Update**: Actualizacion semanal via GitHub Actions

## Stack Tecnico

- **Frontend**: HTML/CSS/JS puro — sin frameworks
- **Base de datos**: SQLite via [sql.js](https://github.com/sql-js/sql.js/) (WASM)
- **Pipeline de datos**: Scripts Python para obtener datos de NVIDIA, Steam, ProtonDB
- **Hosting**: GitHub Pages (gratis)
- **CI/CD**: GitHub Actions para actualizaciones semanales automaticas

## Inicio Rapido

### Ver el sitio

Visita el sitio en GitHub Pages (link pendiente tras deployment).

### Ejecutar localmente

```bash
# Clonar
git clone https://github.com/YOUR_USERNAME/LinuxPlayDB.git
cd LinuxPlayDB

# Instalar dependencias Python
pip install -r scripts/requirements.txt

# Construir la base de datos
python scripts/build_db.py

# Servir localmente
python -m http.server 8080 --directory site
# Abrir http://localhost:8080
```

### Reconstruir con datos online

```bash
python scripts/build_db.py --fetch
```

## Fuentes de Datos

| Fuente | Tipo | Datos |
|--------|------|-------|
| [NVIDIA RTX DB](https://www.nvidia.com/en-us/geforce/news/nvidia-rtx-games-engines-apps/) | Auto | RT/PT, DLSS, Ray Reconstruction |
| [Steam Store API](https://store.steampowered.com/) | Auto | Detalles de juegos, generos, imagenes |
| [ProtonDB](https://www.protondb.com/) | Auto | Tiers de compatibilidad Linux |
| [Steam Deck Compat](https://store.steampowered.com/) | Auto | Verified/Playable/Unsupported |
| [AreWeAntiCheatYet](https://areweanticheatyet.com/) | Auto | Estado anti-cheat en Linux |
| Investigacion Manual | Manual | Quirks AMD, comandos Linux, datos handheld |

## Contribuir

Las contribuciones son bienvenidas. Areas donde mas se necesita ayuda:

1. **Datos de juegos**: Investigar compatibilidad AMD, comandos Linux, y versiones de Proton
2. **Testing en handhelds**: Reportar FPS, settings, y TDP para combinaciones dispositivo + juego
3. **Traducciones**: Mejorar contenido en Español/Ingles en la base de datos
4. **Bug Reports**: Problemas con el sitio o precision de datos

Usa los templates de prompts en `scripts/prompts/` para investigacion estructurada.

## Licencia

[MIT](LICENSE)
