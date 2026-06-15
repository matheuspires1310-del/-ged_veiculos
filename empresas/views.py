from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count

from .models import Empresa, CategoriaVeiculo
from documentos.models import Lote, Documento


def _empresas_do_usuario(user):
    from .models import PermissaoEmpresa
    if user.is_superuser:
        return Empresa.objects.filter(ativo=True)
    ids = PermissaoEmpresa.objects.filter(usuario=user).values_list("empresa_id", flat=True)
    return Empresa.objects.filter(id__in=ids, ativo=True)


@login_required
def lista_empresas(request):
    empresas = _empresas_do_usuario(request.user).select_related("categoria", "matriz").annotate(
        total_docs=Count("documentos"),
        total_lotes=Count("lotes"),
    )
    matrizes = empresas.filter(tipo="matriz")
    filiais = empresas.filter(tipo="filial")
    return render(request, "empresas/lista.html", {
        "matrizes": matrizes,
        "filiais": filiais,
        "categorias": CategoriaVeiculo.objects.all(),
    })


@login_required
def detalhe_empresa(request, pk):
    empresas = _empresas_do_usuario(request.user)
    empresa = get_object_or_404(Empresa, pk=pk, id__in=empresas.values_list("id", flat=True))
    lotes = Lote.objects.filter(empresa=empresa).annotate(total_docs=Count("documentos")).order_by("-criado_em")
    docs_recentes = Documento.objects.filter(empresa=empresa).select_related("tipo", "lote").order_by("-criado_em")[:20]

    return render(request, "empresas/detalhe.html", {
        "empresa": empresa,
        "lotes": lotes,
        "docs_recentes": docs_recentes,
        "filiais": empresa.filiais.all() if empresa.tipo == "matriz" else [],
    })


@login_required
def lista_lotes(request):
    empresas = _empresas_do_usuario(request.user)
    lotes = Lote.objects.filter(empresa__in=empresas).select_related("empresa", "criado_por").annotate(
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
                codigo=codigo,
                empresa=empresa,
                descricao=descricao,
                observacoes=observacoes,
                criado_por=request.user,
            )
            messages.success(request, f"Lote {lote.codigo} criado.")
            return redirect("detalhe_lote", pk=lote.pk)

    return render(request, "empresas/criar_lote.html", {"empresas": empresas})


@login_required
def detalhe_lote(request, pk):
    empresas = _empresas_do_usuario(request.user)
    lote = get_object_or_404(Lote, pk=pk, empresa__in=empresas)
    docs = Documento.objects.filter(lote=lote).select_related("tipo", "veiculo", "enviado_por").order_by("-criado_em")
    veiculos = lote.veiculos.all()

    return render(request, "empresas/detalhe_lote.html", {
        "lote": lote,
        "documentos": docs,
        "veiculos": veiculos,
    })