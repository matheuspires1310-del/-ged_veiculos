from django.contrib import admin
from .models import TipoDocumento, Lote, Veiculo, Documento


@admin.register(TipoDocumento)
class TipoDocumentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "icone", "extensoes_permitidas", "ativo")
    list_editable = ("ativo",)


class VeiculoInline(admin.TabularInline):
    model = Veiculo
    fields = ("chassi", "placa", "marca", "modelo", "ano_fabricacao", "cor")
    extra = 0


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ("codigo", "empresa", "status", "total_documentos", "data_abertura", "criado_por")
    list_filter = ("status", "empresa")
    search_fields = ("codigo", "descricao")
    raw_id_fields = ("empresa",)
    inlines = [VeiculoInline]


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("nome_exibicao", "empresa", "tipo", "lote", "status_sync", "criado_em", "enviado_por")
    list_filter = ("status_sync", "tipo", "empresa")
    search_fields = ("nome_original", "nome_exibicao", "tags", "veiculo__chassi", "veiculo__placa")
    raw_id_fields = ("empresa", "lote", "veiculo")
    readonly_fields = ("onedrive_item_id", "onedrive_path", "onedrive_url", "onedrive_download_url",
                       "status_sync", "erro_sync", "criado_em", "atualizado_em")
    fieldsets = (
        ("Arquivo", {"fields": ("nome_original", "nome_exibicao", "extensao", "tamanho_bytes")}),
        ("Classificação", {"fields": ("empresa", "tipo", "lote", "veiculo")}),
        ("Metadados", {"fields": ("descricao", "tags")}),
        ("OneDrive", {"fields": ("onedrive_item_id", "onedrive_path", "onedrive_url", "status_sync", "erro_sync"), "classes": ("collapse",)}),
        ("Controle", {"fields": ("enviado_por", "criado_em", "atualizado_em"), "classes": ("collapse",)}),
    )
