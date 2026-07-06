# External Fulltext Resolution Skill

Resolve lawful fulltext availability for external metadata sources after title/abstract screening has returned `include_for_fulltext`.

Allowed behavior:

- Prefer existing Zotero attachment and local fulltext cache before external links.
- Use open-access PDF or HTML links only when metadata indicates lawful access.
- Record metadata-only publisher landing pages as unresolved fulltext.
- Mark unavailable or inaccessible fulltext as `blocked_external`.
- Never bypass paywalls, automate credentials, scrape browser cookies, or use pirate mirrors.
- Never commit PDF, HTML, supplemental information, or Zotero database files.
