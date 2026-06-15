from django.db import models
from django.contrib.auth.models import User


class CategoriaVeiculo(models.Model):
    """Categoria de veículo que cada matriz representa."""
    TIPOS = [
        ("leve", "Veículos Leves"),
        ("pesado", "Veículos Pesados"),
        ("moto", "Motos e Especiais"),
        ("outro", "Outro"),
    ]
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPOS, unique=True)
    descricao = models.TextField(blank=True)
    cor_hex = models.CharField(max_length=7, default="#378ADD", help_text="Cor para identificação visual")

    class Meta:
        verbose_name = "Categoria de Veículo"
        verbose_name_plural = "Categorias de Veículos"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Empresa(models.Model):
    """Representa uma matriz (CNPJ próprio, categoria de veículo)."""
    TIPO = [("matriz", "Matriz"), ("filial", "Filial")]

    tipo = models.CharField(max_length=10, choices=TIPO, default="matriz")
    razao_social = models.CharField(max_length=200)
    nome_fantasia = models.CharField(max_length=100, blank=True)
    cnpj = models.CharField(max_length=18, unique=True)
    categoria = models.ForeignKey(
        CategoriaVeiculo, on_delete=models.PROTECT,
        null=True, blank=True, related_name="empresas"
    )
    matriz = models.ForeignKey(
        "self", on_delete=models.PROTECT,
        null=True, blank=True, related_name="filiais",
        help_text="Preenchido apenas para filiais"
    )
    cidade = models.CharField(max_length=100, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["razao_social"]

    def __str__(self):
        return f"{self.nome_fantasia or self.razao_social} ({self.cnpj})"

    @property
    def nome_exibicao(self):
        return self.nome_fantasia or self.razao_social

    @property
    def categoria_efetiva(self):
        """Filiais herdam a categoria da matriz."""
        if self.tipo == "filial" and self.matriz:
            return self.matriz.categoria
        return self.categoria


class PermissaoEmpresa(models.Model):
    """Controla quais usuários têm acesso a quais empresas."""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="permissoes")
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="permissoes")
    pode_upload = models.BooleanField(default=True)
    pode_excluir = models.BooleanField(default=False)

    class Meta:
        unique_together = ("usuario", "empresa")
        verbose_name = "Permissão de Empresa"

    def __str__(self):
        return f"{self.usuario.username} → {self.empresa.nome_exibicao}"
