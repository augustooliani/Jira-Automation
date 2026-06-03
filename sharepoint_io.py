"""Download/upload de arquivos do SharePoint Online reaproveitando a mesma
sessao autenticada do Edge (perfil .edge_profile) usada para o Jira.

Estrategia:
  1. Navega ate a URL do arquivo no Edge para garantir cookies de SSO
     (FedAuth, rtFa) emitidos pelo Microsoft Online para o tenant.
  2. Constroi uma requests.Session com esses cookies e fala com a REST API
     do SharePoint:
        GET  {site}/_api/web/GetFileByServerRelativeUrl('<path>')/$value
        POST {site}/_api/contextinfo                (pega X-RequestDigest)
        POST {site}/_api/web/GetFileByServerRelativeUrl('<path>')/$value
  3. Faz download para um arquivo local temporario; depois de editado,
     re-faz upload sobrescrevendo a versao no SharePoint.

Suporta URLs no formato:
  https://<tenant>.sharepoint.com/:x:/r/sites/<site>/<lib>/<sub>/<file>.xlsx?...
  https://<tenant>.sharepoint.com/sites/<site>/<lib>/<sub>/<file>.xlsx
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse, unquote, quote
import re
import requests
import urllib3

from step3_create_jira_ui import start_browser, _active_page

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------------------
# Parsing da URL
# ---------------------------------------------------------------------------
def parse_sharepoint_url(url: str) -> tuple[str, str, str, str]:
    """Devolve (host_url, site_url, server_relative_path, file_name).

    Ex.:
      url = 'https://telit365.sharepoint.com/:x:/r/sites/Telit365MBX-Shen.../Shared%20Documents/.../BOM.xlsx?d=...'
      -> host_url = 'https://telit365.sharepoint.com'
      -> site_url = 'https://telit365.sharepoint.com/sites/Telit365MBX-Shen...'
      -> server_relative_path = '/sites/Telit365MBX-Shen.../Shared Documents/.../BOM.xlsx'
      -> file_name = 'BOM.xlsx'
    """
    p = urlparse(url)
    host_url = f"{p.scheme}://{p.netloc}"
    path = unquote(p.path)

    # Remove o prefixo de "share view" se houver: /:x:/r/  /:x:/g/  /:w:/r/  /:b:/r/  etc.
    path = re.sub(r"^/:[a-z]:/[a-z]/", "/", path)

    # Server-relative path comeca com '/'
    if not path.startswith("/"):
        path = "/" + path

    # Site url = host + '/sites/<nome>'
    m = re.match(r"^(/sites/[^/]+)/", path)
    if m:
        site_rel = m.group(1)
    else:
        # arquivo direto na raiz do tenant (raro) -> trata como site '/'
        site_rel = ""

    site_url = host_url + site_rel
    file_name = path.rsplit("/", 1)[-1]
    return host_url, site_url, path, file_name


# ---------------------------------------------------------------------------
# Sessao autenticada via cookies do Edge
# ---------------------------------------------------------------------------
def _ensure_sharepoint_cookies(host_url: str) -> requests.Session:
    """Abre o host no Edge (perfil persistente) para garantir cookies de SSO
    e devolve uma requests.Session com esses cookies.

    Usa uma ABA SEPARADA (que e fechada ao final) para nao perder as abas
    dos tickets do Jira ja abertas.
    """
    # Garante navegador iniciado
    start_browser()
    from step3_create_jira_ui import _ctx  # contexto Playwright

    sp_tab = _ctx.new_page()
    try:
        try:
            sp_tab.goto(host_url, wait_until="domcontentloaded", timeout=30000)
            sp_tab.wait_for_timeout(1500)
        except Exception:
            pass

        s = requests.Session()
        parsed_host = urlparse(host_url).netloc
        for c in _ctx.cookies():
            domain = (c.get("domain") or "").lstrip(".")
            # Aceita cookies do host exato e do dominio pai (sharepoint.com)
            if domain == parsed_host or parsed_host.endswith(domain):
                s.cookies.set(c["name"], c["value"], domain=c.get("domain"))
        s.headers.update({
            "Accept": "application/json;odata=verbose",
            "User-Agent": "Mozilla/5.0 BOMAutomation",
        })
        s.verify = False
        return s
    finally:
        try:
            sp_tab.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Download / upload
# ---------------------------------------------------------------------------
def download_bom(share_url: str, dest_path: Path) -> Path:
    """Baixa o arquivo do SharePoint para `dest_path`. Devolve o Path final."""
    host_url, site_url, file_path, file_name = parse_sharepoint_url(share_url)
    print(f"[SharePoint] host    : {host_url}")
    print(f"[SharePoint] site    : {site_url}")
    print(f"[SharePoint] arquivo : {file_path}")

    s = _ensure_sharepoint_cookies(host_url)
    encoded = quote(file_path, safe="")
    api_url = f"{site_url}/_api/web/GetFileByServerRelativeUrl('{encoded}')/$value"

    r = s.get(api_url, headers={"Accept": "application/octet-stream"},
              timeout=60, allow_redirects=True)
    if r.status_code >= 300:
        raise RuntimeError(
            f"Falha ao baixar do SharePoint ({r.status_code}).\n"
            f"URL: {api_url}\nResposta: {r.text[:500]}"
        )

    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(r.content)
    print(f"[SharePoint] BOM baixada para: {dest_path}  ({len(r.content)} bytes)")
    return dest_path


def upload_bom(share_url: str, src_path: Path) -> None:
    """Sobrescreve o arquivo no SharePoint com o conteudo de `src_path`."""
    src_path = Path(src_path)
    if not src_path.exists():
        raise FileNotFoundError(src_path)

    host_url, site_url, file_path, file_name = parse_sharepoint_url(share_url)
    s = _ensure_sharepoint_cookies(host_url)

    # 1) Pega o X-RequestDigest necessario para qualquer POST de escrita
    ctx = s.post(f"{site_url}/_api/contextinfo",
                 headers={"Accept": "application/json;odata=verbose"}, timeout=30)
    if ctx.status_code >= 300:
        raise RuntimeError(f"Falha ao obter contextinfo ({ctx.status_code}): {ctx.text[:500]}")
    try:
        digest = ctx.json()["d"]["GetContextWebInformation"]["FormDigestValue"]
    except Exception as exc:
        raise RuntimeError(f"Resposta inesperada de contextinfo: {ctx.text[:500]}") from exc

    encoded = quote(file_path, safe="")
    api_url = f"{site_url}/_api/web/GetFileByServerRelativeUrl('{encoded}')/$value"

    data = src_path.read_bytes()
    print(f"[SharePoint] enviando {len(data)} bytes para {file_path} ...")
    r = s.post(api_url, data=data, headers={
        "X-RequestDigest": digest,
        "X-HTTP-Method": "PUT",       # SharePoint REST: PUT via tunneling
        "Content-Type": "application/octet-stream",
        "Accept": "application/json;odata=verbose",
    }, timeout=120)
    if r.status_code >= 300:
        raise RuntimeError(
            f"Falha ao subir para o SharePoint ({r.status_code}).\n"
            f"URL: {api_url}\nResposta: {r.text[:500]}"
        )
    print("[SharePoint] upload concluido.")
