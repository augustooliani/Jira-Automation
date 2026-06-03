"""
Versao com UI visivel: abre o Microsoft Edge via Playwright, cria a issue
pela tela do Jira, anexa o datasheet e preenche os campos.

- Usa um perfil persistente em .edge_profile/ (login fica salvo entre execucoes).
- Na primeira execucao voce faz login manualmente; nas seguintes ja entra direto.
- Os anexos e a atualizacao de campos sao feitos via API REST do Jira,
  reaproveitando os cookies da sessao do Edge, e a pagina e recarregada
  para voce ver visualmente cada passo.
"""

from pathlib import Path
from urllib.parse import urlparse, quote
import time
import requests

from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError as PWTimeout

import config


PROFILE_DIR = Path(__file__).parent / ".edge_profile"

# Pagina inicial: uma issue ja existente; usamos o botao 'Create' do header.
LANDING_URL = "https://pmo.telit.com/browse/MAT-4201"

_pw = None
_ctx: BrowserContext | None = None
_page: Page | None = None


# ---------------------------------------------------------------------------
# Inicializacao / encerramento do navegador
# ---------------------------------------------------------------------------
def start_browser() -> Page:
    """Abre o Edge (visivel) com perfil persistente e devolve a pagina.
    Se a pagina ou o contexto tiverem sido fechados, reabre tudo.
    """
    global _pw, _ctx, _page

    # Reaproveita se ainda esta vivo
    if _page is not None and not _page.is_closed():
        return _page

    # Se o contexto morreu, limpa antes de reabrir
    if _ctx is not None:
        try:
            _ctx.close()
        except Exception:
            pass
        _ctx = None
    if _pw is not None:
        try:
            _pw.stop()
        except Exception:
            pass
        _pw = None

    PROFILE_DIR.mkdir(exist_ok=True)
    _pw = sync_playwright().start()
    _ctx = _pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="msedge",
        headless=False,
        slow_mo=400,
        args=["--start-maximized"],
        viewport=None,
    )
    # Pega/cria a primeira pagina valida
    _page = None
    for p in _ctx.pages:
        if not p.is_closed():
            _page = p
            break
    if _page is None:
        _page = _ctx.new_page()

    _page.goto(LANDING_URL, wait_until="domcontentloaded")

    if "login" in _page.url.lower():
        print(">> Faca login no Jira na janela que abriu e tecle ENTER aqui...")
        input()
        _page.goto(LANDING_URL, wait_until="domcontentloaded")
    return _page


def _active_page() -> Page:
    """Sempre devolve uma pagina aberta; se a atual fechou, troca por outra."""
    global _page
    if _page is None or _page.is_closed():
        # tenta pegar outra ja existente no contexto
        if _ctx is not None:
            for p in _ctx.pages:
                if not p.is_closed():
                    _page = p
                    return _page
        # nada aberto -> reinicia tudo
        return start_browser()
    return _page


def close_browser() -> None:
    global _pw, _ctx, _page
    if _ctx is not None:
        _ctx.close()
    if _pw is not None:
        _pw.stop()
    _pw = _ctx = _page = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe(value):
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() == "nan" else s


def _split_alternative(alt: str) -> tuple[str, str]:
    """'Murata#GRM31CD71H106KE11L' -> ('Murata', 'GRM31CD71H106KE11L').
    Se nao tiver '#', devolve ('', alt).
    """
    alt = _safe(alt)
    if "#" in alt:
        manuf, mpn = alt.split("#", 1)
        return manuf.strip(), mpn.strip()
    return "", alt


def _extract_package(description: str, is_generic: bool) -> str:
    """Deduz o Component Package a partir do DESCR.
    - Generic: procura por um codigo SMD padrao (0201, 0402, 0603, ...) na descr.
    - Specific: usa o ultimo 'token' (separado por espaco) da descr.
    Retorna '' se nada puder ser deduzido.
    """
    desc = _safe(description)
    if not desc:
        return ""
    tokens = desc.split()
    if is_generic:
        codes_upper = {c.upper() for c in config.SMD_PACKAGE_CODES}
        for tk in tokens:
            if tk.upper() in codes_upper:
                return tk
        return ""
    # Specific: ultimo token
    return tokens[-1] if tokens else ""


def _extract_function(description: str) -> str:
    """Deduz o Component Function pelo DESCR usando config.COMPONENT_FUNCTION_MAP.
    Retorna '' se nenhuma palavra-chave for encontrada.
    """
    desc_upper = _safe(description).upper()
    if not desc_upper:
        return ""
    for needle, value in config.COMPONENT_FUNCTION_MAP:
        if needle.upper() in desc_upper:
            return value
    return ""


def _api_session_from_browser() -> requests.Session:
    """Cria uma requests.Session com os cookies da sessao atual do Edge."""
    assert _ctx is not None, "Browser nao inicializado"
    s = requests.Session()
    for c in _ctx.cookies():
        s.cookies.set(c["name"], c["value"], domain=c.get("domain"))
    s.headers.update({
        "Accept": "application/json",
        "X-Atlassian-Token": "no-check",
    })
    # Rede corporativa intercepta TLS -> desliga verificacao do certificado
    s.verify = False
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return s


# ---------------------------------------------------------------------------
# Etapa 1 - criar a issue ja COMPLETA via API (com todos os campos)
# A UI do Edge eh usada para voce visualizar a issue criada, mas a criacao
# em si vai por API porque o tipo ERF tem 11 campos obrigatorios.
# ---------------------------------------------------------------------------
def create_minimal_issue_ui(row) -> str:
    """Cria a issue completa via API e navega ate ela no Edge para voce ver."""
    page = _active_page()
    part_number = _safe(row.get(config.COLUMN_PART_NUMBER))
    line = _safe(row.get(config.COLUMN_LINE))
    description = _safe(row.get(config.COLUMN_COMP_DESCRIPTION))
    summary = f"ERF - {part_number} ({line})" if part_number else f"ERF - {line}"

    fields = {
        "project": {"key": config.JIRA_PROJECT_KEY},
        "issuetype": {"name": config.JIRA_ISSUE_TYPE},
        "summary": summary,
        "description": description or f"Solicitacao de ERF para {part_number}",
    }
    # mescla campos da BOM/valores fixos
    fields.update(_build_fields(row))

    session = _api_session_from_browser()
    url = f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/2/issue"
    payload = {"fields": fields}

    import json
    print(">>> PAYLOAD create:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    resp = session.post(
        url, json=payload,
        headers={"Content-Type": "application/json"}, timeout=30,
    )
    print(f">>> Resposta create {resp.status_code}: {resp.text}")

    if resp.status_code >= 300:
        # Mostra quais campos sao obrigatorios/aceitos para o tipo ERF
        meta = session.get(
            f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/2/issue/createmeta"
            f"?projectKeys={config.JIRA_PROJECT_KEY}"
            f"&issuetypeNames={config.JIRA_ISSUE_TYPE}&expand=projects.issuetypes.fields",
            timeout=30,
        )
        if meta.status_code < 300:
            try:
                proj = meta.json()["projects"][0]
                itype = proj["issuetypes"][0]
                obrigs = {fid: f["name"] for fid, f in itype["fields"].items() if f.get("required")}
                print(">>> Campos OBRIGATORIOS para ERF (id -> nome):")
                print(json.dumps(obrigs, indent=2, ensure_ascii=False))
            except Exception:
                print(meta.text[:2000])
        raise RuntimeError(f"Falha ao criar issue ({resp.status_code}): {resp.text}")

    issue_key = resp.json()["key"]
    print(f"  >> Issue criada via API: {issue_key}")

    # Abre a issue em uma NOVA aba e a torna a pagina ativa,
    # de modo que o anexo e o update subsequentes apareçam nela.
    global _page
    new_tab = _ctx.new_page()
    new_tab.goto(f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{issue_key}",
                 wait_until="domcontentloaded")
    new_tab.wait_for_timeout(1500)
    _page = new_tab
    return issue_key


# ---------------------------------------------------------------------------
# Etapa 2 - anexar o datasheet (via API com os cookies do Edge) + reload visivel
# ---------------------------------------------------------------------------
def attach_file_ui(issue_key: str, file_path: Path) -> None:
    page = _active_page()
    session = _api_session_from_browser()
    url = f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/2/issue/{issue_key}/attachments"

    with open(file_path, "rb") as fh:
        files = {"file": (file_path.name, fh, "application/pdf")}
        resp = session.post(url, files=files, timeout=60)
    if resp.status_code >= 300:
        raise RuntimeError(f"Falha ao anexar ({resp.status_code}): {resp.text}")

    # Navega ate a issue e recarrega para voce VER o anexo aparecendo
    page.goto(f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{issue_key}",
              wait_until="domcontentloaded")
    page.wait_for_timeout(1000)


# ---------------------------------------------------------------------------
# Etapa 3 - preencher os customfields (via API) + reload visivel
# ---------------------------------------------------------------------------
def _build_fields(row) -> dict:
    alt = _safe(row.get(config.COLUMN_PART_NUMBER))
    manuf_from_alt, mpn_from_alt = _split_alternative(alt)

    description = _safe(row.get(config.COLUMN_COMP_DESCRIPTION))
    manufacturer = _safe(row.get(config.COLUMN_MANUFACTURER)) or manuf_from_alt \
                   or config.DEFAULT_MANUFACTURER
    mpn = _safe(row.get(config.COLUMN_MPN)) or mpn_from_alt or alt
    vendor = _safe(row.get(config.COLUMN_VENDOR_NAME)) or manufacturer

    # Item Type: Generic se DESCR contiver alguma das palavras-chave; senao Specific.
    desc_upper = description.upper()
    is_generic = any(kw.upper() in desc_upper for kw in config.GENERIC_ITEM_TYPE_KEYWORDS)
    item_type_value = config.VALUE_ITEM_TYPE_GENERIC if is_generic else config.VALUE_ITEM_TYPE

    # Package: extraido do DESCR conforme a regra (generic = codigo SMD; specific = ultimo token).
    package = (_safe(row.get(config.COLUMN_COMPONENT_PACKAGE))
               or _extract_package(description, is_generic)
               or config.DEFAULT_COMPONENT_PACKAGE)

    # Function: deduzida do DESCR via mapa de palavras-chave.
    function = (_safe(row.get(config.COLUMN_COMPONENT_FUNCTION))
                or _extract_function(description)
                or config.DEFAULT_COMPONENT_FUNCTION)

    fields = {
        # --- Valores fixos ---
        config.FIELD_ORIGIN: config.VALUE_ORIGIN,
        config.FIELD_MATERIAL_REASON: config.VALUE_MATERIAL_REASON,
        config.FIELD_TELIT_PLATFORM: config.VALUE_TELIT_PLATFORM,
        config.FIELD_TELIT_PRODUCTS: config.VALUE_TELIT_PRODUCTS,
        config.FIELD_ITEM_TYPE: item_type_value,

        # --- Valores vindos da BOM ---
        config.FIELD_COMP_DESCRIPTION: description,
        config.FIELD_MPN: mpn,
        config.FIELD_ORDER_CODE: mpn,
        config.FIELD_COMPONENT_PACKAGE: package,

        # nFeed: lista de strings simples
        config.FIELD_MANUFACTURER: [manufacturer],
        config.FIELD_COMPONENT_FUNCTION: [function],

        "description": description or f"Solicitacao de ERF para {mpn}",
    }
    return {k: v for k, v in fields.items() if v not in ("", None, [], {})}


def update_issue_fields_ui(issue_key: str, row) -> None:
    page = _active_page()
    session = _api_session_from_browser()
    url = f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/2/issue/{issue_key}"

    payload = {"fields": _build_fields(row)}
    import json
    print(">>> PAYLOAD enviado ao Jira:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    resp = session.put(
        url, json=payload,
        headers={"Content-Type": "application/json"}, timeout=30,
    )
    print(f">>> Resposta {resp.status_code}: {resp.text}")

    if resp.status_code >= 300:
        # Se falhar, tenta descobrir quais campos sao editaveis nesta issue
        meta = session.get(url + "/editmeta", timeout=30)
        if meta.status_code < 300:
            names = {k: v.get("name") for k, v in meta.json().get("fields", {}).items()}
            print(">>> Campos editaveis nesta issue (id -> nome):")
            print(json.dumps(names, indent=2, ensure_ascii=False))
        raise RuntimeError(f"Falha ao atualizar campos ({resp.status_code}): {resp.text}")

    # Recarrega a issue para voce VER os campos preenchidos
    page.goto(f"{config.JIRA_BASE_URL.rstrip('/')}/browse/{issue_key}",
              wait_until="domcontentloaded")
    page.wait_for_timeout(1500)


# ---------------------------------------------------------------------------
# Etapa 4 - definir assignee e mudar o status (Open -> Purchasing)
# ---------------------------------------------------------------------------
def _find_username(session: requests.Session, query: str) -> str | None:
    """Procura um usuario por displayName ou username e devolve o `name` (login).
    Estrategia:
      1. Match EXATO por displayName (case-insensitive).
      2. Match por displayName que CONTENHA todas as palavras de `query`.
      3. Match exato por username/name.
    NUNCA devolve um usuario inativo (active=false).
    Se nenhum candidato bater, devolve None (e a chamada falha explicitamente).
    """
    base = config.JIRA_BASE_URL.rstrip("/")
    q = query.strip()
    q_lower = q.lower()
    tokens = [t for t in q_lower.split() if t]

    all_users: list[dict] = []
    for param in ("username", "query"):
        try:
            r = session.get(f"{base}/rest/api/2/user/search",
                            params={param: q, "maxResults": 50}, timeout=20)
            if r.status_code >= 300:
                continue
            data = r.json()
            if isinstance(data, list):
                all_users.extend(data)
        except Exception:
            pass

    # Dedup por name/key
    seen = set()
    candidates = []
    for u in all_users:
        kid = u.get("name") or u.get("key") or u.get("accountId")
        if kid in seen:
            continue
        seen.add(kid)
        candidates.append(u)

    if not candidates:
        print(f"  [assignee] nenhum candidato retornado para '{query}'.")
        return None

    print(f"  [assignee] candidatos para '{query}':")
    for u in candidates:
        print(f"    - name={u.get('name')!r}  displayName={u.get('displayName')!r}  "
              f"active={u.get('active')}")

    actives = [u for u in candidates if u.get("active", True)]

    # 1) match exato por displayName, preferindo ativos
    for pool in (actives, candidates):
        for u in pool:
            if (u.get("displayName") or "").strip().lower() == q_lower:
                return u.get("name") or u.get("key")

    # 2) displayName contendo todas as palavras da query
    for pool in (actives, candidates):
        for u in pool:
            dn = (u.get("displayName") or "").lower()
            if all(tok in dn for tok in tokens):
                return u.get("name") or u.get("key")

    # 3) match exato por username
    for pool in (actives, candidates):
        for u in pool:
            if (u.get("name") or "").strip().lower() == q_lower:
                return u.get("name") or u.get("key")

    print(f"  [assignee] nenhum candidato bateu com '{query}' -> recusando atribuicao.")
    return None


def set_assignee_ui(issue_key: str, display_name: str) -> None:
    """Define o assignee da issue procurando o usuario por displayName."""
    session = _api_session_from_browser()
    base = config.JIRA_BASE_URL.rstrip("/")
    username = _find_username(session, display_name)
    if not username:
        raise RuntimeError(f"Usuario '{display_name}' nao encontrado no Jira.")
    print(f"  >> Atribuindo {issue_key} a '{username}' (displayName '{display_name}')")
    r = session.put(f"{base}/rest/api/2/issue/{issue_key}/assignee",
                    json={"name": username},
                    headers={"Content-Type": "application/json"}, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Falha ao atribuir assignee ({r.status_code}): {r.text}")

    # Verifica se persistiu (algumas workflows tem post-function que reatribui)
    chk = session.get(f"{base}/rest/api/2/issue/{issue_key}?fields=assignee", timeout=20)
    if chk.status_code < 300:
        cur = (chk.json().get("fields") or {}).get("assignee") or {}
        cur_name = cur.get("name")
        cur_dn = cur.get("displayName")
        if cur_name and cur_name.lower() != username.lower():
            print(f"  [aviso] Apos PUT, assignee aparece como '{cur_dn}' ({cur_name}). "
                  f"Algum gatilho do workflow reatribuiu o ticket.")
        else:
            print(f"  [ok] Assignee confirmado: '{cur_dn}' ({cur_name})")

    # Recarrega a aba do ticket no Edge para voce ver o assignee atualizado
    try:
        page = _active_page()
        page.goto(f"{base}/browse/{issue_key}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
    except Exception as exc:
        print(f"  [aviso] nao foi possivel recarregar a aba do {issue_key}: {exc}")


def transition_issue_ui(issue_key: str, transition_name: str) -> None:
    """Executa uma transicao de status pelo nome (case-insensitive)."""
    session = _api_session_from_browser()
    base = config.JIRA_BASE_URL.rstrip("/")
    url = f"{base}/rest/api/2/issue/{issue_key}/transitions"
    r = session.get(url, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Falha ao listar transicoes ({r.status_code}): {r.text}")
    transitions = r.json().get("transitions", [])
    target = None
    name_l = transition_name.strip().lower()
    for t in transitions:
        if t.get("name", "").strip().lower() == name_l \
                or t.get("to", {}).get("name", "").strip().lower() == name_l:
            target = t
            break
    if not target:
        avail = [(t.get("name"), t.get("to", {}).get("name")) for t in transitions]
        raise RuntimeError(
            f"Transicao '{transition_name}' nao disponivel em {issue_key}. "
            f"Disponiveis (name -> to): {avail}"
        )
    print(f"  >> Transicionando {issue_key} via '{target.get('name')}' "
          f"-> '{target.get('to', {}).get('name')}'")
    r = session.post(url, json={"transition": {"id": target["id"]}},
                     headers={"Content-Type": "application/json"}, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Falha na transicao ({r.status_code}): {r.text}")

    # Recarrega a pagina para voce ver o novo status
    page = _active_page()
    page.goto(f"{base}/browse/{issue_key}", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
