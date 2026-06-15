from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db.models import Q, Count
from django.contrib import messages
from django.utils import timezone

from .models import Documento, TipoDocumento, Lote, Veiculo
from .storage import garantir_estrutura_pasta, fazer_upload, inferir_tipo_documento, obter_url_download, excluir_arquivo
from empresas.models import Empresa, PermissaoEmpresa


def _empresas_do_usuario(user):
    """Retorna QuerySet das empresas que o usuário pode acessar."""
    if user.is_superuser:
        return Empresa.objects.filter(ativo=True)
    ids = PermissaoEmpresa.objects.filter(usuario=user).values_list("empresa_id", flat=True)
    return Empresa.objects.filter(id__in=ids, ativo=True)


def _pode_upload(user, empresa):
    if user.is_superuser:
        return True
    perm = PermissaoEmpresa.objects.filter(usuario=user, empresa=empresa).first()
    return perm and perm.pode_upload


def _pode_excluir(user, empresa):
    if user.is_superuser:
        return True
    perm = PermissaoEmpresa.objects.filter(usuario=user, empresa=empresa).first()
    return perm and perm.pode_excluir


@login_required
def dashboard(request):
    empresas = _empresas_do_usuario(request.user)
    docs = Documento.objects.filter(empresa__in=empresas)

    stats = {
        "total_docs": docs.count(),
        "docs_mes": docs.filter(criado_em__month=timezone.now().month).count(),
        "lotes_abertos": Lote.objects.filter(empresa__in=empresas, status="aberto").count(),
        "erros_sync": docs.filter(status_sync="erro").count(),
    }

    # Documentos recentes
    recentes = docs.select_related("empresa", "tipo", "enviado_por").order_by("-criado_em")[:10]

    # Distribuição por tipo
    por_tipo = (
        docs.values("tipo__nome", "tipo__icone")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )

    return render(request, "dashboard/index.html", {
        "stats": stats,
        "recentes": recentes,
        "por_tipo": list(por_tipo),
        "empresas": empresas,
    })


@login_required
def lista_documentos(request):
    empresas = _empresas_do_usuario(request.user)
    qs = Documento.objects.filter(empresa__in=empresas).select_related(
        "empresa", "tipo", "lote", "veiculo", "enviado_por"
    )

    # Filtros
    q = request.GET.get("q", "").strip()
    empresa_id = request.GET.get("empresa")
    tipo_id = request.GET.get("tipo")
    lote_id = request.GET.get("lote")
    status = request.GET.get("status")

    if q:
        qs = qs.filter(
            Q(nome_original__icontains=q)
            | Q(nome_exibicao__icontains=q)
            | Q(descricao__icontains=q)
            | Q(tags__icontains=q)
            | Q(veiculo__chassi__icontains=q)
            | Q(veiculo__placa__icontains=q)
        )
    if empresa_id:
        qs = qs.filter(empresa_id=empresa_id)
    if tipo_id:
        qs = qs.filter(tipo_id=tipo_id)
    if lote_id:
        qs = qs.filter(lote_id=lote_id)
    if status:
        qs = qs.filter(status_sync=status)

    return render(request, "documentos/lista.html", {
        "documentos": qs.order_by("-criado_em")[:200],
        "empresas": empresas,
        "tipos": TipoDocumento.objects.filter(ativo=True),
        "lotes": Lote.objects.filter(empresa__in=empresas).order_by("-criado_em")[:50],
        "filtros": {"q": q, "empresa_id": empresa_id, "tipo_id": tipo_id, "lote_id": lote_id, "status": status},
        "total": qs.count(),
    })


@login_required
def detalhe_documento(request, pk):
    empresas = _empresas_do_usuario(request.user)
    doc = get_object_or_404(Documento, pk=pk, empresa__in=empresas)
    pode_excluir = _pode_excluir(request.user, doc.empresa)

    # Atualiza URL de download (expira em ~1h)
    if doc.onedrive_item_id and doc.status_sync == "sincronizado":
        try:
            doc.onedrive_download_url = obter_url_download(doc.onedrive_item_id)
            doc.save(update_fields=["onedrive_download_url"])
        except Exception:
            pass

    return render(request, "documentos/detalhe.html", {"doc": doc, "pode_excluir": pode_excluir})


@login_required
def upload_documento(request):
    empresas = _empresas_do_usuario(request.user)

    if request.method == "GET":
        empresa_id = request.GET.get("empresa")
        lote_id = request.GET.get("lote")
        return render(request, "documentos/upload.html", {
            "empresas": empresas,
            "tipos": TipoDocumento.objects.filter(ativo=True),
            "lotes": Lote.objects.filter(empresa__in=empresas, status__in=["aberto", "em_andamento"]).order_by("-criado_em"),
            "empresa_id_pre": empresa_id,
            "lote_id_pre": lote_id,
        })

    # POST — processa upload
    arquivo = request.FILES.get("arquivo")
    empresa_id = request.POST.get("empresa")
    tipo_id = request.POST.get("tipo")
    lote_id = request.POST.get("lote") or None
    nome_exibicao = request.POST.get("nome_exibicao", "").strip()
    descricao = request.POST.get("descricao", "").strip()
    tags = request.POST.get("tags", "").strip()
    chassi = request.POST.get("chassi", "").strip()
    placa = request.POST.get("placa", "").strip()

    if not arquivo or not empresa_id or not tipo_id:
        messages.error(request, "Arquivo, empresa e tipo de documento são obrigatórios.")
        return redirect("upload_documento")

    empresa = get_object_or_404(Empresa, pk=empresa_id, id__in=empresas.values_list("id", flat=True))
    if not _pode_upload(request.user, empresa):
        return HttpResponseForbidden("Sem permissão para upload nesta empresa.")

    tipo = get_object_or_404(TipoDocumento, pk=tipo_id, ativo=True)
    lote = get_object_or_404(Lote, pk=lote_id, empresa__in=empresas) if lote_id else None

    # Extensão
    nome_original = arquivo.name
    ext = nome_original.rsplit(".", 1)[-1].lower() if "." in nome_original else ""
    if ext not in tipo.get_extensoes():
        messages.error(request, f"Extensão .{ext} não permitida para {tipo.nome}.")
        return redirect("upload_documento")

    # Veiculo (se chassi ou placa informados)
    veiculo = None
    if lote and (chassi or placa):
        veiculo, _ = Veiculo.objects.get_or_create(
            lote=lote,
            chassi=chassi or "",
            placa=placa or "",
            defaults={"marca": request.POST.get("marca", ""), "modelo": request.POST.get("modelo", "")}
        )

    # Cria registro pendente
    doc = Documento.objects.create(
        empresa=empresa,
        lote=lote,
        veiculo=veiculo,
        tipo=tipo,
        nome_original=nome_original,
        nome_exibicao=nome_exibicao or nome_original,
        extensao=ext,
        tamanho_bytes=arquivo.size,
        descricao=descricao,
        tags=tags,
        enviado_por=request.user,
        status_sync="pendente",
    )

    # Faz upload para OneDrive
    try:
        pasta_id, caminho = garantir_estrutura_pasta(empresa, lote, tipo)
        resultado = fazer_upload(arquivo.read(), nome_original, pasta_id)

        doc.onedrive_item_id = resultado.get("id", "")
        doc.onedrive_path = caminho + "/" + nome_original
        doc.onedrive_url = resultado.get("webUrl", "")
        doc.onedrive_download_url = resultado.get("@microsoft.graph.downloadUrl", "")
        doc.status_sync = "sincronizado"
        doc.save()

        messages.success(request, f'Documento "{doc.nome_exibicao}" enviado com sucesso.')
    except Exception as e:
        doc.status_sync = "erro"
        doc.erro_sync = str(e)
        doc.save()
        messages.error(request, f"Erro ao enviar para o OneDrive: {e}")

    return redirect("lista_documentos")


@login_required
@require_POST
def excluir_documento(request, pk):
    empresas = _empresas_do_usuario(request.user)
    doc = get_object_or_404(Documento, pk=pk, empresa__in=empresas)

    if not _pode_excluir(request.user, doc.empresa):
        return HttpResponseForbidden()

    if doc.onedrive_item_id:
        try:
            excluir_arquivo(doc.onedrive_item_id)
        except Exception as e:
            messages.warning(request, f"Removido do banco, mas erro ao excluir no OneDrive: {e}")

    doc.delete()
    messages.success(request, "Documento excluído.")
    return redirect("lista_documentos")


@login_required
def inferir_tipo_ajax(request):
    """Endpoint AJAX: sugere tipo de documento pelo nome do arquivo."""
    nome = request.GET.get("nome", "")
    tipos = TipoDocumento.objects.filter(ativo=True)
    tipo = inferir_tipo_documento(nome, tipos)
    if tipo:
        return JsonResponse({"id": tipo.pk, "nome": tipo.nome})
    return JsonResponse({"id": None, "nome": None})


@login_required
def lotes_por_empresa_ajax(request):
    """Endpoint AJAX: retorna lotes de uma empresa."""
    empresa_id = request.GET.get("empresa_id")
    empresas = _empresas_do_usuario(request.user)
    lotes = Lote.objects.filter(
        empresa_id=empresa_id,
        empresa__in=empresas,
        status__in=["aberto", "em_andamento"]
    ).values("id", "codigo", "descricao")
    return JsonResponse({"lotes": list(lotes)})
