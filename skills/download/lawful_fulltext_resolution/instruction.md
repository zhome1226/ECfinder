# Lawful Full-text Resolution Skill

Resolve open-access, user-provided, institutional repository, publisher HTML, or Zotero-managed full text. Do not use Sci-Hub, pirate mirrors, paywall bypass, browser cookie scraping, credential automation, or MFA bypass. Missing full text is a blocked_external result, not a batch failure.

## Stage 2.8 Legacy DownloadAgent Integration

Legacy `agents/DownloadAgent.md` guidance is now part of this skill:

- Run only after `title_abstract_screening_v1` returns `include_for_fulltext`.
- Prefer Zotero attachments and local cache before external open-access links.
- Record URL, access status, license/access notes, byte size, and SHA-256 only when a lawful local file is actually present.
- Do not commit raw PDF, publisher HTML, supplemental information, or Zotero database files.
- If no lawful full text is available, record `blocked_external` and continue the workflow.
- Do not use paywall bypass, credential automation, browser cookie scraping, or pirate mirrors.
