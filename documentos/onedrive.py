"""
Serviço de integração com Microsoft Graph API / OneDrive.

Autenticação via Client Credentials (app-only), ideal para uso em servidor
sem interação do usuário. Configure um App Registration no Azure AD com
permissão Files.ReadWrite.All no Microsoft Graph.

Estrutura de pastas criada automaticamente no OneDrive:
  GED_Veiculos/
    Matriz_A_Leves/
      Filial_A1/
        Lote_001/
          Fiscal/
          Registro/
          Contrato/
          Vistoria/
      Filial_A2/
        ...
    Matriz_B_Pesados/
      ...
"""

import re
import requests
from django.conf import settings


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT_ID}/oauth2/v2.0/token"


def _get_access_token() -> str:
    """Obtém token de acesso via Client Credentials."""
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "client_secret": settings.MICROSOFT_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_access_token()}"}


def _drive_url(path: str) -> str:
    """Monta URL de item no drive configurado."""
    drive_id = settings.MICROSOFT_DRIVE_ID
    if drive_id:
        return f"{GRAPH_BASE}/drives/{drive_id}/{path}"
    return f"{GRAPH_BASE}/me/drive/{path}"


def _slugify(texto: str) -> str:
    """Converte texto para nome seguro de pasta no OneDrive."""
    texto = texto.strip().replace(" ", "_")
    texto = re.sub(r"[^\w\-]", "", texto, flags=re.ASCII)
    return texto[:60]


def _criar_pasta_se_nao_existe(parent_item_id: str, nome_pasta: str) -> str:
    """
    Cria uma pasta dentro de parent_item_id se ainda não existir.
    Retorna o item_id da pasta.
    """
    headers = _headers()

    # Tenta buscar pasta existente
    url_busca = _drive_url(f"items/{parent_item_id}/children")
    resp = requests.get(url_busca, headers=headers, params={"$filter": f"name eq '{nome_pasta}'"}, timeout=10)
    resp.raise_for_status()
    itens = resp.json().get("value", [])
    if itens:
        return itens[0]["id"]

    # Cria a pasta
    url_criar = _drive_url(f"items/{parent_item_id}/children")
    resp = requests.post(url_criar, headers=headers, json={
        "name": nome_pasta,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "fail",
    }, timeout=10)
    if resp.status_code == 409:  # Já existe (race condition)
        return _criar_pasta_se_nao_existe(parent_item_id, nome_pasta)
    resp.raise_for_status()
    return resp.json()["id"]


def garantir_estrutura_pasta(empresa, lote=None, tipo_doc=None) -> tuple[str, str]:
    """
    Garante que a estrutura de pastas existe no OneDrive para a combinação
    empresa + lote + tipo de documento. Cria as pastas que faltam.

    Retorna (item_id_pasta_destino, caminho_legivel).
    """
    headers = _headers()

    # Pasta raiz do GED
    root_name = settings.ONEDRIVE_ROOT_FOLDER
    resp = requests.get(_drive_url("root/children"), headers=headers,
                        params={"$filter": f"name eq '{root_name}'"}, timeout=10)
    resp.raise_for_status()
    raiz_itens = resp.json().get("value", [])
    if raiz_itens:
        raiz_id = raiz_itens[0]["id"]
    else:
        resp2 = requests.post(_drive_url("root/children"), headers=headers, json={
            "name": root_name, "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        }, timeout=10)
        resp2.raise_for_status()
        raiz_id = resp2.json()["id"]

    caminho = root_name

    # Nível Matriz
    empresa_efetiva = empresa.matriz if empresa.tipo == "filial" else empresa
    nome_matriz = _slugify(f"{empresa_efetiva.nome_exibicao}")
    matriz_id = _criar_pasta_se_nao_existe(raiz_id, nome_matriz)
    caminho += f"/{nome_matriz}"

    # Nível Filial (se for filial)
    pasta_atual_id = matriz_id
    if empresa.tipo == "filial":
        nome_filial = _slugify(empresa.nome_exibicao)
        pasta_atual_id = _criar_pasta_se_nao_existe(matriz_id, nome_filial)
        caminho += f"/{nome_filial}"

    # Nível Lote
    if lote:
        nome_lote = _slugify(f"Lote_{lote.codigo}")
        pasta_atual_id = _criar_pasta_se_nao_existe(pasta_atual_id, nome_lote)
        caminho += f"/{nome_lote}"

    # Nível Tipo de Documento
    if tipo_doc:
        nome_tipo = _slugify(tipo_doc.nome)
        pasta_atual_id = _criar_pasta_se_nao_existe(pasta_atual_id, nome_tipo)
        caminho += f"/{nome_tipo}"

    return pasta_atual_id, caminho


def fazer_upload(arquivo_bytes: bytes, nome_arquivo: str, pasta_item_id: str) -> dict:
    """
    Faz upload de um arquivo para uma pasta no OneDrive.
    Para arquivos até 4MB usa upload simples; acima usa upload em sessão.

    Retorna dict com id, webUrl, @microsoft.graph.downloadUrl.
    """
    MAX_SIMPLES = 4 * 1024 * 1024  # 4MB

    if len(arquivo_bytes) <= MAX_SIMPLES:
        return _upload_simples(arquivo_bytes, nome_arquivo, pasta_item_id)
    return _upload_sessao(arquivo_bytes, nome_arquivo, pasta_item_id)


def _upload_simples(arquivo_bytes: bytes, nome_arquivo: str, pasta_item_id: str) -> dict:
    url = _drive_url(f"items/{pasta_item_id}:/{nome_arquivo}:/content")
    resp = requests.put(url, headers={**_headers(), "Content-Type": "application/octet-stream"},
                        data=arquivo_bytes, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _upload_sessao(arquivo_bytes: bytes, nome_arquivo: str, pasta_item_id: str) -> dict:
    """Upload em sessão para arquivos grandes (>4MB)."""
    url_sessao = _drive_url(f"items/{pasta_item_id}:/{nome_arquivo}:/createUploadSession")
    resp = requests.post(url_sessao, headers=_headers(), json={
        "item": {"@microsoft.graph.conflictBehavior": "rename", "name": nome_arquivo}
    }, timeout=10)
    resp.raise_for_status()
    upload_url = resp.json()["uploadUrl"]

    CHUNK = 5 * 1024 * 1024  # 5MB por chunk
    total = len(arquivo_bytes)
    offset = 0
    resultado = {}

    while offset < total:
        fim = min(offset + CHUNK, total)
        chunk = arquivo_bytes[offset:fim]
        headers_chunk = {
            "Content-Length": str(len(chunk)),
            "Content-Range": f"bytes {offset}-{fim - 1}/{total}",
        }
        resp = requests.put(upload_url, headers=headers_chunk, data=chunk, timeout=120)
        if resp.status_code in (200, 201):
            resultado = resp.json()
        elif resp.status_code != 202:
            resp.raise_for_status()
        offset = fim

    return resultado


def obter_url_download(item_id: str) -> str:
    """Retorna URL temporária de download (válida por ~1 hora)."""
    resp = requests.get(_drive_url(f"items/{item_id}"), headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json().get("@microsoft.graph.downloadUrl", "")


def excluir_arquivo(item_id: str) -> bool:
    """Remove um arquivo do OneDrive."""
    resp = requests.delete(_drive_url(f"items/{item_id}"), headers=_headers(), timeout=10)
    return resp.status_code == 204


def inferir_tipo_documento(nome_arquivo: str, tipos_disponiveis) -> object | None:
    """
    Tenta inferir o tipo de documento pelo nome do arquivo.
    Percorre os padrões cadastrados em cada TipoDocumento.
    """
    nome_lower = nome_arquivo.lower()
    for tipo in tipos_disponiveis:
        for padrao in tipo.get_padroes():
            if padrao in nome_lower:
                return tipo
    return None
