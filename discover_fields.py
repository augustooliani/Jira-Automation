"""
Descoberta dos IDs reais dos customfields do Jira para o tipo ERF do projeto MAT.
Rode UMA VEZ com `python discover_fields.py` e cole a saida no chat.
"""

import json
import urllib3
from step3_create_jira_ui import start_browser, _api_session_from_browser
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main():
    start_browser()  # garante login/cookies
    s = _api_session_from_browser()
    s.verify = False

    base = config.JIRA_BASE_URL.rstrip("/")

    # 1) Lista TODOS os campos do Jira (nome + id + tipo)
    r = s.get(f"{base}/rest/api/2/field", timeout=30)
    print(f"\n=== /rest/api/2/field status {r.status_code} ===")
    if r.status_code >= 300:
        print(r.text[:2000])
        return

    fields = r.json()
    # Termos que queremos achar (nome do campo na tela do Jira)
    alvos = [
        "origin", "material reason", "telit platform", "telit products",
        "item type", "part number", "bom line", "status", "description",
        "mpn", "manufacturer", "vendor", "package", "function",
        "component description", "component package", "component function",
    ]

    print("\n=== CAMPOS QUE COMBINAM COM OS ALVOS ===")
    for f in fields:
        nome = (f.get("name") or "").lower()
        if any(alvo in nome for alvo in alvos):
            schema = f.get("schema", {})
            tipo = schema.get("custom", "") or schema.get("type", "")
            print(f"  {f.get('id'):<25}  {f.get('name'):<40}  {tipo}")

    # 2) Pega uma issue ERF existente para conferir quais campos estao
    # realmente populados (mais confiavel que createmeta)
    sample_key = "MAT-4201"  # voce ja confirmou que existe
    r2 = s.get(f"{base}/rest/api/2/issue/{sample_key}?expand=names,schema", timeout=30)
    print(f"\n=== issue {sample_key} status {r2.status_code} ===")
    if r2.status_code < 300:
        data = r2.json()
        names = data.get("names", {})
        values = data.get("fields", {})
        print("\n=== CAMPOS COM VALOR NESSA ISSUE EXEMPLO (id | nome | valor) ===")
        for fid, val in values.items():
            if val in (None, "", [], {}):
                continue
            nome = names.get(fid, "?")
            txt = str(val)
            if len(txt) > 80:
                txt = txt[:80] + "..."
            print(f"  {fid:<25}  {nome:<40}  {txt}")


if __name__ == "__main__":
    main()
