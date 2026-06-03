"""
Cria issues no Jira a partir de uma linha da BOM e anexa o datasheet.
Usa a sessao do navegador (cookies) - voce ja esta logado no Jira.
"""

from pathlib import Path
from urllib.parse import urlparse
import requests
import browser_cookie3

import config


_SESSION: requests.Session | None = None


def _get_session() -> requests.Session:
    """Cria/recupera uma Session do requests com cookies do navegador."""
    global _SESSION
    if _SESSION is not None:
        return _SESSION

    domain = urlparse(config.JIRA_BASE_URL).hostname
    loader = getattr(browser_cookie3, config.BROWSER_FOR_COOKIES.lower())
    cj = loader(domain_name=domain)

    session = requests.Session()
    session.cookies.update(cj)
    session.headers.update({
        "Accept": "application/json",
        "X-Atlassian-Token": "no-check",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
    })
    _SESSION = session
    return session


def _safe(value):
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() == "nan" else s


def build_issue_fields(row) -> dict:
    """Mapeia colunas da BOM para os campos completos do Jira."""
    part_number = _safe(row.get(config.COLUMN_PART_NUMBER))
    line = _safe(row.get(config.COLUMN_LINE))
    description = _safe(row.get(config.COLUMN_COMP_DESCRIPTION))

    fields = {
        # Valores fixos (definidos em config.py)
        config.FIELD_ORIGIN: config.VALUE_ORIGIN,
        config.FIELD_MATERIAL_REASON: config.VALUE_MATERIAL_REASON,
        config.FIELD_TELIT_PLATFORM: config.VALUE_TELIT_PLATFORM,
        config.FIELD_TELIT_PRODUCTS: config.VALUE_TELIT_PRODUCTS,
        config.FIELD_ITEM_TYPE: config.VALUE_ITEM_TYPE,

        # Valores vindos da BOM
        config.FIELD_PART_NUMBER: part_number,
        config.FIELD_BOM_LINE: line,
        config.FIELD_STATUS_BOM: _safe(row.get(config.COLUMN_STATUS)),
        config.FIELD_COMP_DESCRIPTION: description,
        config.FIELD_MPN: _safe(row.get(config.COLUMN_MPN)),
        config.FIELD_MANUFACTURER: _safe(row.get(config.COLUMN_MANUFACTURER)),
        config.FIELD_VENDOR_NAME: _safe(row.get(config.COLUMN_VENDOR_NAME)),
        config.FIELD_COMPONENT_PACKAGE: _safe(row.get(config.COLUMN_COMPONENT_PACKAGE)),
        config.FIELD_COMPONENT_FUNCTION: _safe(row.get(config.COLUMN_COMPONENT_FUNCTION)),

        "description": description or f"Solicitacao de ERF para {part_number}",
    }
    # Remove campos vazios/None para nao quebrar validacoes do Jira
    return {k: v for k, v in fields.items() if v not in ("", None, [], {})}


def create_minimal_issue(row) -> str:
    """Cria a issue com o minimo necessario (project, issuetype, summary)
    para que ja seja possivel anexar o datasheet antes de preencher
    os demais campos.
    """
    session = _get_session()
    part_number = _safe(row.get(config.COLUMN_PART_NUMBER))
    line = _safe(row.get(config.COLUMN_LINE))
    summary = (
        f"ERF - {part_number} ({line})" if part_number else f"ERF - {line}"
    )

    payload = {
        "fields": {
            "project": {"key": config.JIRA_PROJECT_KEY},
            "issuetype": {"name": config.JIRA_ISSUE_TYPE},
            "summary": summary,
        }
    }
    url = f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/2/issue"
    resp = session.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(
            f"Falha ao criar issue no Jira ({resp.status_code}): {resp.text}"
        )
    return resp.json()["key"]


def update_issue_fields(issue_key: str, row) -> None:
    """Preenche todos os customfields da issue ja criada."""
    session = _get_session()
    payload = {"fields": build_issue_fields(row)}
    url = f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/2/issue/{issue_key}"
    resp = session.put(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(
            f"Falha ao atualizar campos de {issue_key} "
            f"({resp.status_code}): {resp.text}"
        )


def attach_file(issue_key: str, file_path: Path) -> None:
    """Anexa um arquivo a uma issue existente."""
    session = _get_session()
    url = f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/2/issue/{issue_key}/attachments"

    with open(file_path, "rb") as fh:
        files = {"file": (file_path.name, fh, "application/pdf")}
        resp = session.post(url, files=files, timeout=60)

    if resp.status_code >= 300:
        raise RuntimeError(
            f"Falha ao anexar '{file_path.name}' em {issue_key} "
            f"({resp.status_code}): {resp.text}"
        )
