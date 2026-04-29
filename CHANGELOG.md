# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [0.2.0] — 2026-04-29

### Adicionado
- **`config/reference_ranges.yaml`**: arquivo de parametrização com valores de referência para 55+ tipos de exame, organizado por categoria médica (lipidograma, hemograma, função hepática, tireoidiana, eletrólitos, vitaminas, hormônios etc.)
- **`src/reference.py`**: módulo de leitura e lookup dos valores de referência; suporta tipos `range`, `max_only`, `min_only` e `qualitative`; suporte a aliases para mapear nomes alternativos de PDFs ao mesmo exame
- **`update_references.py`**: script interativo de linha de comando para adicionar, editar e remover valores de referência sem editar o YAML manualmente
- **Aba "🔬 Análise por Exame" no dashboard**: nova aba que exibe, para o exame selecionado:
  - Gráfico de linha + pontos de todas as amostras históricas
  - Faixas coloridas (zonas) quando configuradas (ex: Normal / Pré-diabético / Diabético para glicose)
  - Linhas de mínimo/máximo tracejadas quando sem zonas
  - Card de informação com o valor de referência e observação
  - Tabela expansiva com todos os registros do exame selecionado
  - Indicador `✓` ou `○` no seletor de exame conforme referência configurada ou não

### Dependências
- Adicionado `pyyaml>=6.0.0` ao `requirements.txt`

---

## [0.1.2] — 2026-04-25

### Adicionado
- **Barra de progresso no dashboard**: ao clicar em Processar, exibe barra de progresso nativa do Streamlit com percentual e nome do arquivo sendo processado em tempo real
- **Barra de progresso na CLI**: comando `process` exibe barra `tqdm` ao processar ZIPs, com percentual, velocidade e nome do arquivo atual
- **Suíte de testes de regressão** em `tests/test_parser.py` cobrindo três cenários críticos:
  - Todas as páginas de um PDF são lidas (proteção contra consumo prematuro do iterador `pdf.pages`)
  - Todos os PDFs de um ZIP são processados (sem saltos silenciosos)
  - Todos os pontos de dados por (exame, data) são preservados no DataFrame final

### Dependências
- Adicionado `tqdm>=4.66.0` ao `requirements.txt`

---

## [0.1.1] — 2026-04-25

### Adicionado
- Suíte de testes com `pytest` em `tests/test_aggregator.py` cobrindo normalização de nomes de exames
- Seção **Testes** no README

### Corrigido
- Nomes de exames com hifens Unicode (U+2010 `‐`, U+2011 `‑`, U+2013 `–`, U+2014 `—`, entre outros) agora são normalizados para hífen ASCII (`-`) antes da deduplicação, eliminando duplicatas como `25 HIDROXI-VITAMINA D` vs `25 HIDROXI‐VITAMINA D`
- Legenda do gráfico de Evolução por Exame no dashboard: movida para abaixo do gráfico, com texto e fundo de alto contraste
- Eixos do gráfico (datas e escala) com cor de texto visível (`#111111`) em vez de herdar a cor do tema

---

## [0.1.0] — inicial

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
