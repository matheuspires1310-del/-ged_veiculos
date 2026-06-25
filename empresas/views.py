import io
import zipfile

import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponse

from .models import Empresa, CategoriaVeiculo
from documentos.models import Lote, Documento, TipoDocumento
from documentos.storage import obter_url_download


def _empresas_do_usuario(user):
    from .models import PermissaoEmpresa
    if user.is_superuser:
        return Empresa.objects.filter(ativo=True)
    ids = PermissaoEmpresa.objects.filter(usuario=user).values_list("empresa_id", flat=True)
    return Empresa.objects.filter(id__in=ids, ativo=True)


@login_required
def lista_empresas(request):
    empresas = _empresas_do_usuario(request.user).select_related("categoria", "matriz").annotate(
        total_docs=Count("documentos"), total_lotes=Count("lotes"),
    )
    return render(request, "empresas/lista.html", {
        "matrizes": empresas.filter(tipo="matriz"),
        "filiais": empresas.filter(tipo="filial"),
        "categorias": CategoriaVeiculo.objects.all(),
    })


@login_required
def detalhe_empresa(request, pk):
    empresas = _empresas_do_usuario(request.user)
    empresa = get_object_or_404(Empresa, pk=pk, id__in=empresas.values_list("id", flat=True))
    lotes = Lote.objects.filter(empresa=empresa).annotate(total_docs=Count("documentos")).order_by("-criado_em")
    docs_recentes = Documento.objects.filter(empresa=empresa).select_related("tipo","lote").order_by("-criado_em")[:20]
    return render(request, "empresas/detalhe.html", {
        "empresa": empresa,
        "lotes": lotes,
        "docs_recentes": docs_recentes,
        "filiais": empresa.filiais.all() if empresa.tipo == "matriz" else [],
    })


@login_required
def lista_lotes(request):
    empresas = _empresas_do_usuario(request.user)
    lotes = Lote.objects.filter(empresa__in=empresas).select_related("empresa","criado_por").annotate(
        total_docs=Count("documentos")
    ).order_by("-criado_em")

    status = request.GET.get("status")
    empresa_id = request.GET.get("empresa")
    if status:
        lotes = lotes.filter(status=status)
    if empresa_id:
        lotes = lotes.filter(empresa_id=empresa_id)

    return render(request, "empresas/lotes.html", {
        "lotes": lotes,
        "empresas": empresas,
        "status_choices": Lote.STATUS,
        "filtros": {"status": status, "empresa_id": empresa_id},
    })


@login_required
def criar_lote(request):
    empresas = _empresas_do_usuario(request.user)
    if request.method == "POST":
        codigo = request.POST.get("codigo", "").strip()
        empresa_id = request.POST.get("empresa")
        descricao = request.POST.get("descricao", "").strip()
        observacoes = request.POST.get("observacoes", "").strip()

        if not codigo or not empresa_id:
            messages.error(request, "Código e empresa são obrigatórios.")
        elif Lote.objects.filter(codigo=codigo).exists():
            messages.error(request, f'Já existe um lote com o código "{codigo}".')
        else:
            empresa = get_object_or_404(Empresa, pk=empresa_id, id__in=empresas.values_list("id", flat=True))
            lote = Lote.objects.create(
                codigo=codigo, empresa=empresa, descricao=descricao,
                observacoes=observacoes, criado_por=request.user,
            )
            messages.success(request, f"Lote {lote.codigo} criado.")
            return redirect("detalhe_lote", pk=lote.pk)

    return render(request, "empresas/criar_lote.html", {"empresas": empresas})


@login_required
def detalhe_lote(request, pk):
    empresas = _empresas_do_usuario(request.user)
    lote = get_object_or_404(Lote, pk=pk, empresa__in=empresas)
    docs = Documento.objects.filter(lote=lote).select_related("tipo","veiculo","enviado_por").order_by("-criado_em")
    veiculos = lote.veiculos.all()

    # 3. CHECKLIST — quais tipos já têm documento neste lote
    todos_tipos = TipoDocumento.objects.filter(ativo=True)
    tipos_com_doc = set(docs.values_list("tipo_id", flat=True))
    docs_por_tipo = docs.values("tipo__nome").annotate(total=Count("id"))
    total_por_tipo = {d["tipo__nome"]: d["total"] for d in docs_por_tipo}

    checklist = []
    for tipo in todos_tipos:
        checklist.append({
            "tipo": tipo.nome,
            "ok": tipo.pk in tipos_com_doc,
            "total": total_por_tipo.get(tipo.nome, 0),
        })

    return render(request, "empresas/detalhe_lote.html", {
        "lote": lote,
        "documentos": docs,
        "veiculos": veiculos,
        "checklist": checklist,
        "docs_por_tipo": tipos_com_doc,
    })


def _nome_seguro(nome):
    """Remove separadores de caminho para uso como entrada de zip."""
    return nome.replace("/", "-").replace("\\", "-").strip() or "documento"


@login_required
def download_lote_zip(request, pk):
    """Baixa todos os documentos sincronizados de um lote em um único ZIP,
    organizado em subpastas por tipo de documento."""
    empresas = _empresas_do_usuario(request.user)
    lote = get_object_or_404(Lote, pk=pk, empresa__in=empresas)
    docs = Documento.objects.filter(lote=lote, status_sync="sincronizado").select_related("tipo")

    if not docs.exists():
        messages.error(request, "Este lote não possui documentos sincronizados para download.")
        return redirect("detalhe_lote", pk=lote.pk)

    buffer = io.BytesIO()
    nomes_usados = set()
    falhas = 0

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc in docs:
            url = doc.onedrive_download_url
            if not url and doc.onedrive_item_id:
                try:
                    url = obter_url_download(doc.onedrive_item_id)
                except Exception:
                    url = ""
            if not url:
                falhas += 1
                continue

            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
            except Exception:
                falhas += 1
                continue

            pasta = _nome_seguro(doc.tipo.nome)
            nome_arquivo = _nome_seguro(doc.nome_exibicao or doc.nome_original)
            caminho = f"{pasta}/{nome_arquivo}"

            if caminho in nomes_usados:
                base, ext = (nome_arquivo.rsplit(".", 1) + [""])[:2]
                contador = 1
                while caminho in nomes_usados:
                    sufixo = f"{base}_{contador}.{ext}" if ext else f"{base}_{contador}"
                    caminho = f"{pasta}/{sufixo}"
                    contador += 1

            nomes_usados.add(caminho)
            zf.writestr(caminho, resp.content)

    if not nomes_usados:
        messages.error(request, "Não foi possível baixar nenhum documento deste lote.")
        return redirect("detalhe_lote", pk=lote.pk)

    if falhas:
        messages.warning(request, f"{falhas} documento(s) não puderam ser incluídos no ZIP.")

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="Lote_{_nome_seguro(lote.codigo)}.zip"'
    return response
