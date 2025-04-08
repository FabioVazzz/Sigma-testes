from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Sum, F
from datetime import datetime, timedelta
from .models import Produto, HistoricoMovimentacao, RecomendacaoCompra
from .forms import ProdutoForm
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from .pdf import gerar_pdf_recomendacoes

# Helpers para verificação de grupos
def is_suprimentos(user):
    return user.groups.filter(name='Suprimentos').exists()

def is_compras(user):
    return user.groups.filter(name='Compras').exists()

# Views existentes (mantidas intactas)
def inicio(request):
    """View para a página inicial do sistema"""
    return render(request, 'estoque/inicio.html')

def adicionar_produto(request):
    """View para adicionar um novo produto"""
    if request.method == 'POST':
        form = ProdutoForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Produto adicionado com sucesso!')
                return redirect('estoque:lista_produtos')
            except Exception as e:
                messages.error(request, f'Erro ao salvar produto: {str(e)}')
        else:
            messages.error(request, 'Por favor, corrija os erros no formulário.')
    else:
        form = ProdutoForm()
    return render(request, 'estoque/adicionar_produto.html', {'form': form})

def editar_produto(request, id):
    """View para editar um produto existente"""
    produto = get_object_or_404(Produto, id=id)
    if request.method == 'POST':
        form = ProdutoForm(request.POST, instance=produto)
        if form.is_valid():
            form.save()
            return redirect('estoque:lista_produtos')
    else:
        form = ProdutoForm(instance=produto)
    return render(request, 'estoque/adicionar_produto.html', {'form': form})

def remover_produto(request, id):
    """View para remover um produto"""
    produto = get_object_or_404(Produto, id=id)
    if request.method == 'POST':
        produto.delete()
        return redirect('estoque:lista_produtos')
    return render(request, 'estoque/confirmar_remocao.html', {'produto': produto})

def lista_produtos(request):
    """View para listar produtos com busca"""
    search_term = request.GET.get('q', '')
    produtos = Produto.objects.all()
    if search_term:
        produtos = produtos.filter(
            Q(nome__icontains=search_term) | 
            Q(codigo__icontains=search_term) |
            Q(descricao__icontains=search_term)
        ).order_by('nome')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'estoque/partials/linhas_produtos.html', {'produtos': produtos})
    return render(request, 'estoque/lista_produtos.html', {'produtos': produtos})

def dashboard(request):
    """
    View para o dashboard de estoque com:
    - Valor total em estoque
    - Valor inativo (itens parados há +1 ano)
    - Quantidade de itens ativos/inativos
    """
    PRECO_PADRAO = 100.00  # Substitua por um campo real se necessário

    valor_total = Produto.objects.aggregate(
        total=Sum(F('quantidade') * PRECO_PADRAO)
    )['total'] or 0

    valor_inativo = Produto.objects.filter(
        parado_mais_um_ano=True
    ).aggregate(
        total=Sum(F('quantidade') * PRECO_PADRAO)
    )['total'] or 0

    qtd_ativos = Produto.objects.filter(parado_mais_um_ano=False).count()
    qtd_inativos = Produto.objects.filter(parado_mais_um_ano=True).count()

    context = {
        'valor_total': valor_total,
        'valor_inativo': valor_inativo,
        'qtd_ativos': qtd_ativos,
        'qtd_inativos': qtd_inativos,
    }
    return render(request, 'estoque/dashboard.html', context)

# --- NOVAS VIEWS PARA RECOMENDAÇÃO DE COMPRAS ---


def gerar_recomendacoes(request):
    """View para gerar recomendações de compra (RF6)"""
    if not request.user.has_perm('estoque.add_recomendacaocompra'):
        messages.error(request, 'Você não tem permissão para executar esta ação.')
        return redirect('estoque:inicio')

    # 1. Itens com estoque baixo
    produtos_estoque_baixo = Produto.objects.filter(
        quantidade__lt=5  # Ajuste o limite conforme necessário
    ).annotate(
        quantidade_recomendada=5 - F('quantidade')
    )

    # 2. Itens com alto histórico de saída (últimos 3 meses)
    tres_meses_atras = datetime.now() - timedelta(days=90)
    
    produtos_consumo = HistoricoMovimentacao.objects.filter(
        tipo='SAIDA',
        data__gte=tres_meses_atras
    ).values('produto').annotate(
        total_saidas=Sum('quantidade')
    ).order_by('-total_saidas')[:10]

    # Criar recomendações
    for produto in produtos_estoque_baixo:
        RecomendacaoCompra.objects.create(
            produto=produto,
            quantidade_recomendada=produto.quantidade_recomendada,
            motivo='ESTOQUE_BAIXO',
            criado_por=request.user
        )

    for item in produtos_consumo:
        produto = Produto.objects.get(id=item['produto'])
        RecomendacaoCompra.objects.create(
            produto=produto,
            quantidade_recomendada=item['total_saidas'],
            motivo='HISTORICO',
            criado_por=request.user
        )

    messages.success(request, 'Recomendações geradas com sucesso!')
    return redirect('estoque:lista_recomendacoes')


def lista_recomendacoes(request):
    """View para listar e editar recomendações (RF7)"""
    if request.method == 'POST':
        # Processar edições/aprovações
        for key, value in request.POST.items():
            if key.startswith('quantidade_'):
                rec_id = key.split('_')[1]
                recomendacao = get_object_or_404(RecomendacaoCompra, id=rec_id)
                recomendacao.quantidade_recomendada = value
                recomendacao.save()
            
            elif key.startswith('aprovar_'):
                rec_id = key.split('_')[1]
                recomendacao = get_object_or_404(RecomendacaoCompra, id=rec_id)
                recomendacao.status = 'APROVADA'
                recomendacao.save()
            
            elif key.startswith('rejeitar_'):
                rec_id = key.split('_')[1]
                recomendacao = get_object_or_404(RecomendacaoCompra, id=rec_id)
                recomendacao.status = 'REJEITADA'
                recomendacao.save()

        messages.success(request, 'Alterações salvas com sucesso!')
        return redirect('estoque:lista_recomendacoes')

    recomendacoes = RecomendacaoCompra.objects.filter(status='PENDENTE')
    return render(request, 'estoque/lista_recomendacoes.html', {'recomendacoes': recomendacoes})


def aprovar_compras(request):
    # Filtra recomendações com status PENDENTE ou APROVADA
    recomendacoes = RecomendacaoCompra.objects.filter(status__in=['PENDENTE', 'APROVADA'])
    
    return render(request, 'estoque/aprovar_compras.html', {
        'recomendacoes': recomendacoes,
        'titulo': 'Recomendações de Compra'
    })

def exportar_pdf(request):
    """Gera PDF com recomendações aprovadas (RF8)"""
    recomendacoes = RecomendacaoCompra.objects.filter(status='APROVADA')
    
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Cabeçalho
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, "Recomendações de Compra Aprovadas")
    p.setFont("Helvetica", 12)
    p.drawString(100, 730, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    # Conteúdo
    y = 700
    for rec in recomendacoes:
        p.setFillColor(colors.blue if rec.motivo == 'HISTORICO' else colors.red)
        p.drawString(100, y, f"{rec.produto.nome} - {rec.quantidade_recomendada} unidades")
        p.setFillColor(colors.black)
        p.drawString(300, y, f"Motivo: {rec.get_motivo_display()}")
        y -= 20
    
    p.showPage()
    p.save()
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="recomendacoes_aprovadas.pdf"'
    return response

def exportar_pdf(request):
    recomendacoes = RecomendacaoCompra.objects.filter(status='APROVADA')
    pdf = gerar_pdf_recomendacoes(recomendacoes)
    
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="recomendacoes.pdf"'
    return response