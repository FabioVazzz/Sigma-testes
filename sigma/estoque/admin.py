from django.contrib import admin
from .models import Produto, HistoricoMovimentacao, RecomendacaoCompra

admin.site.register(Produto)
admin.site.register(HistoricoMovimentacao)
admin.site.register(RecomendacaoCompra)