"""
Gera um PDF sintético em formato "Laudo Evolutivo" com dados fictícios de exames
de sangue. Este é o formato que o parser trata com código dedicado e que funciona
de forma confiável para múltiplas datas em um único PDF.

Formato Laudo Evolutivo reconhecido pelo parser:
  Laudo Evolutivo
  Data da Ficha  DD/MM/YYYY  DD/MM/YYYY  ...
  EXAME  v1  v2  ...  ref unit
"""
import zipfile
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


EXAM_DATES = [
    "15/01/2023",
    "10/07/2023",
    "20/01/2024",
    "15/07/2024",
    "10/01/2025",
]

# (exam_name, [v1, v2, v3, v4, v5], reference_with_unit)
# Values use comma decimal to match the parser's expected format
EXAM_SERIES = [
    ("GLICOSE",             ["95",  "103",  "112",  "108",  "98"],  "70,0-99,0 mg/dL"),
    ("HEMOGLOBINA GLICADA", ["5,4", "5,7",  "6,1",  "5,9",  "5,5"], "<5,7 %"),
    ("COLESTEROL TOTAL",    ["185", "210",  "225",  "198",  "182"], "<200,0 mg/dL"),
    ("LDL-COLESTEROL",      ["109", "128",  "140",  "118",  "102"], "<100,0 mg/dL"),
    ("HDL-COLESTEROL",      ["52",  "48",   "46",   "50",   "55"],  ">40,0 mg/dL"),
    ("TRIGLICERIDES",       ["120", "165",  "190",  "145",  "115"], "<150,0 mg/dL"),
    ("VITAMINA D (25-OH)",  ["28",  "22",   "18",   "35",   "42"],  "30,0-100,0 ng/mL"),
    ("VITAMINA B12",        ["320", "290",  "260",  "380",  "420"], "200-900 pg/mL"),
    ("HEMOGLOBINA",         ["14,2","13,8", "13,5", "14,0", "14,5"],"13,0-17,0 g/dL"),
    ("HEMATOCRITO",         ["42,0","41,0", "40,5", "41,5", "43,0"],"38,5-50,0 %"),
    ("TSH",                 ["2,3", "3,1",  "3,8",  "2,7",  "2,1"], "0,4-4,0 mUI/mL"),
    ("T4 LIVRE",            ["1,1", "1,0",  "0,9",  "1,1",  "1,2"], "0,8-1,9 ng/dL"),
    ("CREATININA",          ["0,9", "0,95", "1,0",  "0,92", "0,88"],"0,6-1,3 mg/dL"),
    ("UREIA",               ["28",  "32",   "35",   "30",   "27"],  "10,0-50,0 mg/dL"),
    ("TGO (AST)",           ["22",  "26",   "30",   "24",   "20"],  "<40,0 U/L"),
    ("TGP (ALT)",           ["18",  "24",   "32",   "22",   "17"],  "<41,0 U/L"),
    ("FERRITINA",           ["85",  "72",   "60",   "78",   "90"],  "30,0-400,0 ng/mL"),
    ("FERRO SERICO",        ["90",  "80",   "70",   "85",   "95"],  "60,0-170,0 mcg/dL"),
]


def make_laudo_evolutivo_pdf(out_path: Path) -> None:
    """Create a single Laudo Evolutivo PDF with all dates and exam series."""
    c = canvas.Canvas(str(out_path), pagesize=A4)
    width, height = A4

    # ── Header ───────────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, height - 1.5 * cm, "A+ Medicina Diagnóstica")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, height - 2.3 * cm, "Laudo Evolutivo")
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, height - 3.0 * cm, "Paciente: João da Silva (Fictício)")

    # ── Date header ───────────────────────────────────────────────────────────
    # Format: "Data da Ficha  DD/MM/YYYY  DD/MM/YYYY  ..."
    date_header = "Data da Ficha  " + "  ".join(EXAM_DATES)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(2 * cm, height - 3.8 * cm, date_header)

    c.line(2 * cm, height - 4.1 * cm, width - 2 * cm, height - 4.1 * cm)

    # ── Exam lines ────────────────────────────────────────────────────────────
    # Format: "EXAM_NAME  v1  v2  v3  v4  v5  reference unit"
    y = height - 4.8 * cm
    c.setFont("Helvetica", 9)

    for name, values, ref in EXAM_SERIES:
        line = f"{name}  " + "  ".join(values) + f"  {ref}"
        c.drawString(2 * cm, y, line)
        y -= 0.65 * cm
        if y < 2 * cm:
            c.showPage()
            y = height - 2 * cm
            c.setFont("Helvetica", 9)

    c.save()


def main():
    out_dir = Path(__file__).parent / "synthetic_data"
    out_dir.mkdir(exist_ok=True)

    pdf_path = out_dir / "exames_evolutivo.pdf"
    make_laudo_evolutivo_pdf(pdf_path)
    print(f"  Criado: {pdf_path.name}")

    # Also pack into a zip for upload via dashboard
    zip_path = out_dir / "exames_sinteticos.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(pdf_path, pdf_path.name)
    print(f"\nZIP criado: {zip_path}")
    return zip_path


if __name__ == "__main__":
    main()
