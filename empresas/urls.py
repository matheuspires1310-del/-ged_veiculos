from django.urls import path
from . import views

urlpatterns = [
    path("", views.lista_empresas, name="lista_empresas"),
    path("<int:pk>/", views.detalhe_empresa, name="detalhe_empresa"),
    path("lotes/", views.lista_lotes, name="lista_lotes"),
    path("lotes/novo/", views.criar_lote, name="criar_lote"),
    path("lotes/<int:pk>/", views.detalhe_lote, name="detalhe_lote"),
]
