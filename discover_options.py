"""
Lista as opcoes validas (id + value) dos campos de select.
Usa o /editmeta de uma issue ja existente para enxergar allowedValues.
"""

import json
import urllib3
from step3_create_jira_ui import start_browser, _api_session_from_browser
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SAMPLE_ISSUE = "MAT-4201"
TARGET_FIELDS = {
    "customfield_14101": "Material Reason",
    "customfield_12504": "Item Type",
    "customfield_10803": "Origin",
    "customfield_10800": "Telit Platform",
    "customfield_10801": "Telit Products",
    "customfield_11109": "Manufacturer",
    "customfield_12526": "Component Function",
}


def main():
    start_browser()
    s = _api_session_from_browser()
    s.verify = False
    base = config.JIRA_BASE_URL.rstrip("/")

    r = s.get(f"{base}/rest/api/2/issue/{SAMPLE_ISSUE}/editmeta", timeout=30)
    print(f"editmeta status {r.status_code}")
    if r.status_code >= 300:
        print(r.text[:2000])
        return

    meta = r.json().get("fields", {})
    for fid, label in TARGET_FIELDS.items():
        info = meta.get(fid)
        print("\n" + "=" * 70)
        print(f"{fid}  ({label})")
        if not info:
            print("  (campo nao aparece em editmeta desta issue)")
            continue
        schema = info.get("schema", {})
        print(f"  schema: {schema}")
        allowed = info.get("allowedValues") or []
        if not allowed:
            print("  (sem allowedValues -> provavelmente texto livre ou nFeed sem lista)")
            continue
        for opt in allowed:
            opt_id = opt.get("id")
            val = opt.get("value") or opt.get("name") or opt.get("key")
            print(f"   id={opt_id:<8} value={val}")


if __name__ == "__main__":
    main()
