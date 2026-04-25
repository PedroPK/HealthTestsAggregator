# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [Não lançado]

### Adicionado
- Suporte ao formato de hemograma tabular (`NOME_EXAME : VALOR UNIDADE REF`)
- Detecção automática de laboratório por nome de arquivo e conteúdo do PDF
- Extração de data a partir do nome do arquivo (padrões `YYYY.MM.DD`, `YYYY-MM-DD`)
- Extração de data pelo cabeçalho `Data da Ficha: DD/MM/YYYY`
- Dashboard Streamlit com upload de arquivo, filtros e gráficos Plotly interativos
- Exportação para Excel com tabela pivô (exames × datas) via `openpyxl`
- Deduplicação de resultados por par `(exam_name, date)` no agregador
- Coluna `value_numeric` no DataFrame para facilitar análises numéricas
- Relatório PDF formatado gerado com `reportlab`
- Suporte a arquivos `.zip` contendo múltiplos PDFs
- CLI com subcomandos `process` e `dashboard` via `argparse`
- Avisos de erros de parsing por arquivo na saída do CLI

### Estrutura
- `src/models.py` — dataclasses `ExamResult` e `ParsedDocument`
- `src/parser.py` — parsing de PDFs com `pdfplumber`
- `src/aggregator.py` — consolidação e pivô com `pandas`
- `src/pdf_exporter.py` — geração de PDF com `reportlab`
- `src/dashboard.py` — dashboard interativo com `streamlit`
- `main.py` — ponto de entrada CLI
