"""Check local Zotero control capabilities for Stage 2.4i."""

from __future__ import annotations

import json

from zotero_stage2_4i_common import REPORTS_DIR, capability_summary, write_key_value_report


REPORT_PATH = REPORTS_DIR / "stage2_4i_zotero_control_capabilities.md"


def main() -> int:
    caps = capability_summary()
    write_key_value_report(
        REPORT_PATH,
        "Stage 2.4i Zotero Control Capabilities",
        caps,
        [
            "Programmatic full-text retrieval is only marked available when a local supported Zotero endpoint or automation hook is detected.",
            "This workflow does not bypass paywalls, login prompts, MFA, CAPTCHA, or publisher access controls.",
        ],
    )
    print(json.dumps(caps, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
