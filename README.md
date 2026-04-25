# HealthTests Aggregator

Ferramenta CLI e dashboard interativo para consolidar e visualizar histórico de exames de sangue a partir de PDFs de laboratório.

## Funcionalidades

- **Parsing automático** de PDFs de múltiplos laboratórios brasileiros
- **Consolidação** de resultados em DataFrame unificado com deduplicação
- **Exportação** para PDF formatado e planilha Excel (tabela pivô)
- **Dashboard interativo** (Streamlit + Plotly) para visualização de tendências ao longo do tempo
- Suporte a arquivos `.zip` contendo múltiplos PDFs

## Laboratórios suportados

| Laboratório | Formatos |
|---|---|
| A+ Medicina Diagnóstica | Laudo Evolutivo (tabela multi-data), laudos individuais por exame |
| Laboratório Marcelo Magalhães | Laudos individuais por exame |
| Hemograma tabular | Formato `NOME_EXAME : VALOR UNIDADE REF` |

## Instalação

**Requisitos:** Python 3.10+

```bash
pip install -r requirements.txt
```

### Dependências

| Pacote | Uso |
|---|---|
| `pdfplumber` | Extração de texto de PDFs |
| `pandas` | Manipulação e deduplicação de dados |
| `reportlab` | Geração de relatórios PDF |
| `plotly` | Gráficos interativos |
| `streamlit` | Dashboard web |
| `openpyxl` | Exportação Excel |

## Uso

### CLI — Processar exames

```bash
# Processar um arquivo ZIP com PDFs
python main.py process "Exames de Sangue.zip"

# Especificar arquivo de saída
python main.py process "Exames de Sangue.zip" --output output/meu_relatorio.pdf
```

O comando gera dois arquivos em `output/`:
- `historico_exames.pdf` — relatório formatado
- `historico_exames.xlsx` — tabela pivô (exames × datas)

### Dashboard interativo

```bash
python main.py dashboard
```

Abre o dashboard Streamlit no navegador. Permite:
- Fazer upload de arquivo ZIP ou PDFs individuais
- Filtrar exames por nome
- Visualizar gráficos de evolução temporal
- Baixar relatório PDF gerado na interface

## Estrutura do projeto

```
HealthTestsAggregator/
├── main.py                 # Ponto de entrada CLI
├── requirements.txt
├── input/                  # Pasta sugerida para arquivos de entrada
├── output/                 # Saídas geradas (PDF, Excel)
└── src/
    ├── models.py           # Dataclasses ExamResult e ParsedDocument
    ├── parser.py           # Extração e parsing de PDFs
    ├── aggregator.py       # Consolidação em DataFrame e tabela pivô
    ├── pdf_exporter.py     # Geração de relatório PDF
    └── dashboard.py        # Dashboard Streamlit
```

## Esquema de dados

### `ExamResult`

| Campo | Tipo | Descrição |
|---|---|---|
| `exam_name` | `str` | Nome do exame (normalizado para maiúsculas) |
| `value` | `str` | Valor bruto como string |
| `unit` | `str \| None` | Unidade de medida |
| `reference_range` | `str \| None` | Intervalo de referência |
| `date` | `date` | Data da coleta |
| `lab` | `str` | Nome do laboratório |
| `source_file` | `str` | Nome do arquivo PDF de origem |

### DataFrame consolidado

```
exam_name | date | value_raw | value_numeric | unit | reference_range | lab | source_file
```

Deduplicação: para o mesmo par `(exam_name, date)`, mantém a última ocorrência encontrada.

Normalização do `exam_name`: uppercase, espaços colapsados, hifens Unicode convertidos para `-` ASCII antes da comparação.

## Testes

```bash
pip install pytest
python -m pytest tests/ -v
```

| Arquivo | Cobre |
|---|---|
| `tests/test_aggregator.py` | Deduplicação com hifens Unicode, dedup case-insensitive, exames distintos não colapsados |
