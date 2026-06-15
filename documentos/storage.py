"""
Serviço de armazenamento de arquivos via Supabase Storage.
"""

import re
import unicodedata
import requests
from django.conf import settings

SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_SECRET_KEY
BUCKET = "documentos"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}


def _slugify(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = texto.strip().lower().replace(" ", "_")
    texto = re.sub(r"[^\w\-]", "", texto)
    return texto[:60] or "sem_nome"


def _limpar_nome_arquivo(nome: str) -> str:
    """Remove acentos, espaços e caracteres inválidos do nome do arquivo."""
    # Separa extensão
    if "." in nome:
        base, ext = nome.rsplit(".", 1)
    else:
        base, ext = nome, ""

    # Normaliza
    base = unicodedata.normalize("NFKD", base)
    base = base.encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"[^\w\-]", "", base)
    base = base or "documento"

    return f"{base}.{ext}" if ext else base


def _montar_caminho(empresa, lote=None, tipo_doc=None, nome_arquivo="") -> str:
    partes = [_slugify(empresa.nome_exibicao)]
    if lote:
        partes.append(f"lote_{_slugify(lote.codigo)}")
    if tipo_doc:
        partes.append(_slugify(tipo_doc.nome))
    partes.append(nome_arquivo)
    return "/".join(partes)


def garantir_estrutura_pasta(empresa, lote=None, tipo_doc=None):
    partes = [_slugify(empresa.nome_exibicao)]
    if lote:
        partes.append(f"lote_{_slugify(lote.codigo)}")
    if tipo_doc:
        partes.append(_slugify(tipo_doc.nome))
    caminho = "/".join(partes)
    return caminho, caminho


def fazer_upload(arquivo_bytes: bytes, nome_arquivo: str, pasta: str) -> dict:
    nome_limpo = _limpar_nome_arquivo(nome_arquivo)
    caminho_completo = f"{pasta}/{nome_limpo}"

    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{caminho_completo}"
    resp = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/octet-stream", "x-upsert": "true"},
        data=arquivo_bytes,
        timeout=120,
    )
    resp.raise_for_status()

    url_publica = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{caminho_completo}"
    return {
        "id": caminho_completo,
        "webUrl": url_publica,
        "@microsoft.graph.downloadUrl": url_publica,
    }


def obter_url_download(item_id: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{item_id}"


def excluir_arquivo(item_id: str) -> bool:
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{item_id}"
    resp = requests.delete(url, headers=HEADERS, timeout=10)
    return resp.status_code in (200, 204)


def inferir_tipo_documento(nome_arquivo: str, tipos_disponiveis) -> object | None:
    nome_lower = nome_arquivo.lower()
    for tipo in tipos_disponiveis:
        for padrao in tipo.get_padroes():
            if padrao in nome_lower:
                return tipo
    return None