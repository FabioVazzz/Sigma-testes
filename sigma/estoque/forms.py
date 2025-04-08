from django import forms
from .models import Produto

class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = ['codigo', 'nome', 'descricao', 'quantidade', 'localizacao']
        labels = {
            'codigo': 'Código',
            'descricao': 'Descrição',
            'localizacao': 'Localização',
        }
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control'}),
            'localizacao': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo']
        if Produto.objects.filter(codigo=codigo).exists():
            raise forms.ValidationError("Este código já está em uso.")
        return codigo

    def clean_quantidade(self):
        quantidade = self.cleaned_data['quantidade']
        if quantidade < 0:
            raise forms.ValidationError("A quantidade não pode ser negativa.")
        return quantidade