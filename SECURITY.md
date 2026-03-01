# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest | Yes |
| Older | No |

As an early-stage project, only the latest version receives updates.

## Reporting a Concern

If you discover a potential security issue, please report it responsibly:

1. **Do NOT** open a public issue
2. **Do** contact the maintainer privately via [GitHub Discussions](https://github.com/lobinuxsoft/LinuxPlayDB/discussions) (private message) or email
3. Include as much detail as possible to help reproduce and understand the issue

## Response Timeline

- **Acknowledgment**: Within 72 hours
- **Initial assessment**: Within 1 week
- **Resolution timeline**: Depends on complexity, communicated after assessment

## Scope

This policy applies to:
- The LinuxPlayDB site code (HTML/CSS/JS)
- Data pipeline scripts (Python fetch/build)
- Database content and schema
- GitHub Actions workflows

**Out of scope**:
- Third-party dependencies (sql.js upstream) - report to their respective projects
- External data source APIs (NVIDIA, Steam, ProtonDB)
- User-generated data contributions

## Security Considerations

This application handles:
- **Static site**: No server-side code, no user authentication
- **SQL queries**: All queries run client-side via sql.js WASM (no injection risk to a server)
- **External fetches**: Data pipeline scripts make HTTP requests to public APIs
- **GitHub Actions**: Automated weekly database updates with write permissions

### Best Practices for Contributors

1. Never commit API keys or credentials
2. Validate all external data before inserting into the database
3. Keep dependencies updated

## Recognition

Contributors who responsibly report valid issues will be credited in release notes (unless they prefer anonymity).
