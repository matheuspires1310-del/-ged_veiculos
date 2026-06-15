from django.contrib import admin
from .models import CategoriaVeiculo, Empresa, PermissaoEmpresa


@admin.register(CategoriaVeiculo)
class CategoriaVeiculoAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "cor_hex")
    list_editable = ("cor_hex",)


class FilialInline(admin.TabularInline):
    model = Empresa
    fk_name = "matriz"
    fields = ("razao_social", "nome_fantasia", "cnpj", "cidade", "uf", "ativo")
    extra = 0


class PermissaoInline(admin.TabularInline):
    model = PermissaoEmpresa
    extra = 0


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nome_exibicao", "cnpj", "tipo", "categoria", "cidade", "uf", "ativo")
    list_filter = ("tipo", "categoria", "ativo", "uf")
    search_fields = ("razao_social", "nome_fantasia", "cnpj")
    raw_id_fields = ("matriz",)
    inlines = [FilialInline, PermissaoInline]

    def get_inlines(self, request, obj=None):
        if obj and obj.tipo == "filial":
            return [PermissaoInline]
        return [FilialInline, PermissaoInline]
