"""Imprime id + value (sem truncar) dos campos select da issue exemplo."""
import json, urllib3
from step3_create_jira_ui import start_browser, _api_session_from_browser
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SAMPLE = "MAT-4201"
TARGETS = ["customfield_14101", "customfield_12504", "customfield_10803",
           "customfield_10800", "customfield_10801", "customfield_11109",
           "customfield_12526"]

start_browser()
s = _api_session_from_browser(); s.verify = False
r = s.get(f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/2/issue/{SAMPLE}", timeout=30)
data = r.json().get("fields", {})
for fid in TARGETS:
    print(f"\n{fid}:")
    print(json.dumps(data.get(fid), indent=2, ensure_ascii=False))
