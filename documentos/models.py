from django.db import models
from django.contrib.auth.models import User
from empresas.models import Empresa


class TipoDocumento(models.Model):
    """Tipos de documentos aceitos no sistema."""
    ICONES = [
        ("file-text", "Fiscal / NF-e"),
        ("license", "Registro / CRLV"),
        ("shield-check", "Vistoria / Laudo"),
        ("file-dollar", "Contrato"),
        ("package", "Lote"),
        ("file", "Geral"),
    ]
    nome = models.CharField(max_length=100)
    icone = models.CharField(max_length=30, choices=ICONES, default="file")
    descricao = models.TextField(blank=True)
    # Padrões de nome de arquivo que auto-classificam este tipo
    padroes_nome = models.TextField(
        blank=True,
        help_text="Padrões separados por vírgula (ex: NF-e, DANFE, nota fiscal)"
    )
    extensoes_permitidas = models.CharField(
        max_length=200, default="pdf,xml,png,jpg,jpeg,xlsx,docx",
        help_text="Extensões separadas por vírgula"
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tipo de Documento"
        verbose_name_plural = "Tipos de Documento"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def get_padroes(self):
        return [p.strip().lower() for p in self.padroes_nome.split(",") if p.strip()]

    def get_extensoes(self):
        return [e.strip().lower() for e in self.extensoes_permitidas.split(",") if e.strip()]


class Lote(models.Model):
    """Lote de veículos — agrupa documentos de uma negociação."""
    STATUS = [
        ("aberto", "Aberto"),
        ("em_andamento", "Em andamento"),
        ("concluido", "Concluído"),
        ("cancelado", "Cancelado"),
    ]
    codigo = models.CharField(max_length=50, unique=True)
    descricao = models.CharField(max_length=200, blank=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="lotes")
    status = models.CharField(max_length=20, choices=STATUS, default="aberto")
    data_abertura = models.DateField(auto_now_add=True)
    data_fechamento = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="lotes_criados")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lote"
        verbose_name_plural = "Lotes"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Lote {self.codigo} — {self.empresa.nome_exibicao}"

    @property
    def total_documentos(self):
        return self.documentos.count()

    @property
    def status_badge_class(self):
        return {
            "aberto": "badge-blue",
            "em_andamento": "badge-amber",
            "concluido": "badge-green",
            "cancelado": "badge-red",
        }.get(self.status, "badge-gray")


class Veiculo(models.Model):
    """Veículo associado a documentos (opcional, para busca por chassi/placa)."""
    lote = models.ForeignKey(Lote, on_delete=models.CASCADE, related_name="veiculos")
    chassi = models.CharField(max_length=17, blank=True)
    placa = models.CharField(max_length=10, blank=True)
    marca = models.CharField(max_length=50, blank=True)
    modelo = models.CharField(max_length=100, blank=True)
    ano_fabricacao = models.IntegerField(null=True, blank=True)
    ano_modelo = models.IntegerField(null=True, blank=True)
    cor = models.CharField(max_length=50, blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Veículo"
        verbose_name_plural = "Veículos"

    def __str__(self):
        partes = [p for p in [self.placa, self.marca, self.modelo] if p]
        return " — ".join(partes) or f"Veículo #{self.pk}"


class Documento(models.Model):
    """Documento armazenado no OneDrive com metadados no banco."""
    STATUS = [
        ("pendente", "Pendente"),
        ("sincronizado", "Sincronizado"),
        ("erro", "Erro no upload"),
    ]

    # Relações
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="documentos")
    lote = models.ForeignKey(Lote, on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos")
    veiculo = models.ForeignKey(Veiculo, on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos")
    tipo = models.ForeignKey(TipoDocumento, on_delete=models.PROTECT, related_name="documentos")

    # Dados do arquivo
    nome_original = models.CharField(max_length=255)
    nome_exibicao = models.CharField(max_length=255, blank=True)
    extensao = models.CharField(max_length=10)
    tamanho_bytes = models.BigIntegerField(default=0)

    # OneDrive
    onedrive_item_id = models.CharField(max_length=500, blank=True)
    onedrive_path = models.CharField(max_length=1000, blank=True)
    onedrive_url = models.URLField(max_length=2000, blank=True)
    onedrive_download_url = models.URLField(max_length=2000, blank=True)
    status_sync = models.CharField(max_length=20, choices=STATUS, default="pendente")
    erro_sync = models.TextField(blank=True)

    # Metadados extras
    descricao = models.TextField(blank=True)
    tags = models.CharField(max_length=500, blank=True, help_text="Tags separadas por vírgula")

    # Controle
    enviado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="documentos_enviados")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "tipo"]),
            models.Index(fields=["lote"]),
            models.Index(fields=["status_sync"]),
        ]

    def __str__(self):
        return f"{self.nome_exibicao or self.nome_original} ({self.empresa.nome_exibicao})"

    @property
    def tamanho_legivel(self):
        b = self.tamanho_bytes
        for unit in ["B", "KB", "MB", "GB"]:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"

    @property
    def icone_extensao(self):
        mapa = {
            "pdf": "file-type-pdf",
            "xml": "file-type-xml",
            "xlsx": "file-spreadsheet",
            "docx": "file-word",
            "png": "photo",
            "jpg": "photo",
            "jpeg": "photo",
        }
        return mapa.get(self.extensao.lower(), "file")

    def get_tags(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]
