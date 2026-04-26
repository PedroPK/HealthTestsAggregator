"""
CLI entry point for HealthTests Aggregator.

Usage examples:
    python main.py process "Exames de Sangue.zip"
    python main.py process "Exames de Sangue.zip" --output output/report.pdf
    python main.py dashboard
"""

import sys
import argparse
from pathlib import Path


def cmd_process(args):
    import zipfile
    from pathlib import Path as _Path
    from tqdm import tqdm
    from src.parser import parse_input, parse_pdf_bytes
    from src.aggregator import build_dataframe, pivot_table
    from src.pdf_exporter import generate_pdf_report

    input_path = _Path(args.input)
    print(f"Processando: {args.input}")

    if input_path.suffix.lower() == ".zip":
        documents = []
        with zipfile.ZipFile(input_path, "r") as zf:
            pdf_entries = [
                info for info in zf.infolist()
                if info.filename.lower().endswith(".pdf")
            ]
            with tqdm(pdf_entries, desc="Processando PDFs", unit="arquivo", dynamic_ncols=True) as pbar:
                for info in pbar:
                    filename = _Path(info.filename).name
                    pbar.set_postfix_str(filename, refresh=True)
                    pdf_bytes = zf.read(info.filename)
                    doc = parse_pdf_bytes(pdf_bytes, filename)
                    documents.append(doc)
    else:
        documents = parse_input(input_path)

    total = sum(len(d.results) for d in documents)
    print(f"✓ {len(documents)} arquivo(s) processado(s) · {total} registros")

    for doc in documents:
        if doc.parse_errors:
            print(f"  ⚠ {doc.source_file}: {len(doc.parse_errors)} erro(s)")

    df = build_dataframe(documents)

    if df.empty:
        print("Nenhum dado extraído. Verifique se os PDFs contêm texto pesquisável.")
        return

    print(f"\nExames encontrados ({df['exam_name'].nunique()}):")
    for exam in sorted(df["exam_name"].unique()):
        count = len(df[df["exam_name"] == exam])
        print(f"  {exam} ({count} registros)")

    # Export PDF
    output = Path(args.output) if args.output else Path("output") / "historico_exames.pdf"
    generate_pdf_report(df, output)
    print(f"\n✓ PDF gerado: {output}")

    # Export Excel
    excel_out = output.with_suffix(".xlsx")
    pivot = pivot_table(df)
    pivot.to_excel(excel_out, sheet_name="Histórico")
    print(f"✓ Excel gerado: {excel_out}")


def cmd_dashboard(args):
    import subprocess
    dashboard_path = Path(__file__).parent / "src" / "dashboard.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(dashboard_path)])


def main():
    parser = argparse.ArgumentParser(
        description="HealthTests Aggregator — consolida histórico de exames de sangue"
    )
    sub = parser.add_subparsers(dest="command")

    # process command
    p_process = sub.add_parser("process", help="Processar PDF(s) ou ZIP")
    p_process.add_argument("input", help="Caminho para PDF ou ZIP")
    p_process.add_argument("--output", "-o", help="Arquivo de saída PDF (opcional)")
    p_process.set_defaults(func=cmd_process)

    # dashboard command
    p_dash = sub.add_parser("dashboard", help="Abrir dashboard interativo")
    p_dash.set_defaults(func=cmd_dashboard)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
