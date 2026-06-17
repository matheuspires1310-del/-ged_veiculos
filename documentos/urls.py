from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("documentos/", views.lista_documentos, name="lista_documentos"),
    path("documentos/upload/", views.upload_documento, name="upload_documento"),
    path("documentos/<int:pk>/", views.detalhe_documento, name="detalhe_documento"),
    path("documentos/<int:pk>/editar/", views.editar_documento, name="editar_documento"),
    path("documentos/<int:pk>/excluir/", views.excluir_documento, name="excluir_documento"),
    path("api/inferir-tipo/", views.inferir_tipo_ajax, name="inferir_tipo_ajax"),
    path("api/lotes/", views.lotes_por_empresa_ajax, name="lotes_por_empresa_ajax"),
]
