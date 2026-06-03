"""Tenta varias rotas para descobrir os IDs das opcoes do campo Item Type
(customfield_12504): createmeta, contexto/options e ate o HTML da pagina de criacao.
"""
import json
import urllib3
from step3_create_jira_ui import start_browser, _api_session_from_browser, _active_page
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FIELD_ID = config.FIELD_ITEM_TYPE  # customfield_12504
BASE = config.JIRA_BASE_URL.rstrip("/")

start_browser()
s = _api_session_from_browser()


def try_createmeta():
    url = (f"{BASE}/rest/api/2/issue/createmeta"
           f"?projectKeys={config.JIRA_PROJECT_KEY}"
           f"&issuetypeNames={config.JIRA_ISSUE_TYPE}"
           f"&expand=projects.issuetypes.fields")
    r = s.get(url, timeout=30)
    print(f"\n[createmeta] HTTP {r.status_code}")
    if r.status_code >= 300:
        print(r.text[:500]); return False
    try:
        proj = r.json()["projects"][0]
        itype = proj["issuetypes"][0]
        field = itype["fields"].get(FIELD_ID)
        if not field:
            print(f"Campo {FIELD_ID} nao listado. Disponiveis:",
                  list(itype["fields"].keys()))
            return False
        print(f"Campo: {field.get('name')}")
        opts = field.get("allowedValues", [])
        if not opts:
            print("Sem allowedValues.")
            return False
        print("Opcoes (id -> value):")
        for opt in opts:
            print(f"  {opt.get('id')}  ->  {opt.get('value')}")
        return True
    except Exception as e:
        print(f"Erro parse: {e}")
        return False


def try_options_endpoint():
    # Jira Server: /rest/api/2/customFieldOption/{id} so funciona com id ja conhecido.
    # Tentamos varar 13700..13900 buscando os que pertencem a 12504. Como nao sabemos,
    # melhor: usar JIRA API /rest/api/2/field (ja sabemos que retorna nome) e
    # /rest/api/1.0/customFields/contexts?customFieldId=
    url = f"{BASE}/rest/api/2/field"
    r = s.get(url, timeout=30)
    print(f"\n[field list] HTTP {r.status_code}")
    if r.status_code >= 300:
        return
    for f in r.json():
        if f.get("id") == FIELD_ID:
            print(json.dumps(f, indent=2, ensure_ascii=False))


def try_html_create():
    """Abre o popup de Create no Edge e raspa o <select> do Item Type."""
    page = _active_page()
    page.goto(f"{BASE}/secure/CreateIssue!default.jspa", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    # Seleciona projeto MAT e issuetype ERF se a tela for o passo 1
    try:
        # pode ser o popup novo (dialogo) ou a pagina classica
        if page.locator("#issuetype").count():
            # pagina classica
            page.select_option("#project", value=config.JIRA_PROJECT_KEY) if page.locator("#project").count() else None
            page.select_option("#issuetype", label=config.JIRA_ISSUE_TYPE) if page.locator("#issuetype").count() else None
            page.click("#issue-create-submit")
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2500)
    except Exception as e:
        print(f"step1 skip: {e}")

    # Agora extrai opcoes do select customfield_12504
    sel = f"select[name='{FIELD_ID}'], select#{FIELD_ID}"
    try:
        page.wait_for_selector(sel, timeout=10000)
    except Exception:
        print(f"\n[html] Nao achei <select> {sel} na pagina.")
        return
    opts = page.evaluate(
        """sel => Array.from(document.querySelectorAll(sel + ' option')).map(o => ({id:o.value, value:o.textContent.trim()}))""",
        sel,
    )
    print("\n[html] Opcoes encontradas no DOM:")
    for o in opts:
        print(f"  {o['id']}  ->  {o['value']}")


print("\n=== 1) createmeta ===")
ok = try_createmeta()
print("\n=== 2) /rest/api/2/field info ===")
try_options_endpoint()
print("\n=== 3) HTML da pagina de criacao ===")
try_html_create()
