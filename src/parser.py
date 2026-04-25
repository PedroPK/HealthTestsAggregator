"""
PDF parser for Brazilian blood test reports.

Supports:
  - A+ Medicina Diagnóstica: Laudo Evolutivo (evolutionary multi-date table)
  - A+ Medicina Diagnóstica: individual results (block format per exam)
  - Laboratório Marcelo Magalhães: individual results (block format per exam)
  - Tabular hemograma format (EXAM_NAME : VALUE UNIT REF)
"""

import re
import zipfile
import io
from pathlib import Path
from datetime import date
from typing import Optional

import pdfplumber

from src.models import ExamResult, ParsedDocument


# ---------------------------------------------------------------------------
# Lab detection
# ---------------------------------------------------------------------------

def _detect_lab(text: str, filename: str = "") -> str:
    t = (text[:500] + " " + filename).lower()
    if re.search(r"marcelo\s*magalh", t):
        return "Laboratório Marcelo Magalhães"
    if re.search(r"a\+\s*medicina|laborat[oó]rio\s*a\+|amaissaude", t):
        return "A+ Medicina Diagnóstica"
    return "Laboratório Desconhecido"



# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _parse_date_dmy(s: str) -> Optional[date]:
    """Parse DD/MM/YYYY."""
    m = re.match(r"(\d{2})[/\-\.](\d{2})[/\-\.](\d{4})", s.strip())
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def _parse_date_ymd(s: str) -> Optional[date]:
    """Parse YYYY.MM.DD or YYYY/MM/DD or YYYY MM DD."""
    m = re.match(r"(\d{4})[/\-\.\s](\d{2})[/\-\.\s](\d{2})", s.strip())
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def _extract_date_from_filename(filename: str) -> Optional[date]:
    """Extract date from common filename patterns like 2017.12.28 or 2018 09 29."""
    m = re.search(r"(\d{4})[.\-\s](\d{2})[.\-\s](\d{2})", filename)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def _extract_ficha_date(text: str) -> Optional[date]:
    """Extract exam date from 'Data da Ficha: DD/MM/YYYY' or 'Data: DD/MM/YYYY' headers."""
    m = re.search(r"Data\s+da\s+Ficha[:\s]+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if m:
        return _parse_date_dmy(m.group(1))
    m = re.search(r"\bData:\s+(\d{2}/\d{2}/\d{4})", text)
    if m:
        return _parse_date_dmy(m.group(1))
    # "DD/MM/YYYY" on first page header (e.g. "01/06/2024")
    m = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", text)
    if m:
        return _parse_date_dmy(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Laudo Evolutivo text-based parser
# ---------------------------------------------------------------------------

# Value token: number (with comma decimal), 4 dashes (absent), <N, >N, qualitative
_VALUE_TOK = re.compile(
    r"^(-{4}|[<>]?\d[\d,\.]*|Negativa|Negativo|Positiva|Positivo|Reagente|"
    r"N[ãa]o\s*Reagente|ausente|presente)$",
    re.IGNORECASE,
)

# Lines to skip in Laudo Evolutivo
_SKIP_EVO = re.compile(
    r"^(Resultado$|Resultados anteriores$|atual$|Valores de referência$|"
    r"Nº Ficha\b|Data da F ?icha\b|Laudo Evolutivo$|Imprimir\b|Fechar$|"
    r"Eletroquimioluminescencia|C\/ jejum|S\/ jejum|"
    r"Nota:|OBS\.|Liberado em:|RECEBIDO|LIBERADO|Assinatura|"
    r"http|ttp:/|www\.|.asp|Página:|Praça|Av |Rua |"
    r"atual\s+Valores de|Resultado\s+Resultados anteriores|"
    r"Ver resultado tradicional|Ver laudo|Valores de referência\s*$|"
    r"Responsável Técnico|RESPONSÁVEL TÉCNICO)",
    re.IGNORECASE,
)


def _is_skip_evo(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if _SKIP_EVO.search(s):
        return True
    # Header lines like "28/12/2017 a+ Medicina..." or "09/08/12 a+ Medicina..."
    if re.match(r"^\d{2}/\d{2}/\d{2,4}\s+\w", s):
        return True
    # Lines like "Ficha: 8050360071 Cliente: ..."
    if re.match(r"^Ficha:\s*\d", s):
        return True
    return False


def _has_values(line: str) -> bool:
    """Return True if line contains at least one value-like token."""
    for tok in line.split():
        if _VALUE_TOK.match(tok):
            return True
    return False


def _extract_unit(ref: str) -> Optional[str]:
    """Extract unit from a reference range string."""
    if not ref:
        return None
    unit_re = re.compile(
        r"\b(g/dL|mg/dL|mEq/L|UI/L|U/L|UI/mL|U/mL|mUI/L|mUI/mL|ng/dL|nmol/L|"
        r"microg/dL|µg/dL|mcg/dL|pg/mL|fL|%|milhões/mm3|/mm3|g/L|mm/h|mg/L|"
        r"pmol/L|ng/mL|µIU/mL|UI/dL|mmol/L|mOsm/kg|mg/g|U/dL|µmol/L)\b",
        re.IGNORECASE,
    )
    matches = list(unit_re.finditer(ref))
    return matches[-1].group(0) if matches else None


def _parse_laudo_evolutivo(full_text: str, lab: str, filename: str) -> list[ExamResult]:
    """
    Parse Laudo Evolutivo (evolutionary multi-date) format.

    Text structure:
        Data da F icha  DD/MM/YYYY  DD/MM/YYYY  ...
        ExamName v1 v2 ... vN  ref unit
        ExamName v1 v2 ... vN  ref unit
        ...
    """
    results: list[ExamResult] = []
    lines = full_text.split("\n")
    n_lines = len(lines)

    current_dates: list[Optional[date]] = []
    N = 0
    pending_name = ""
    last_batch_start = -1  # index in results[] where last batch started
    last_batch_values_only = False  # True when last data line had value_start==0

    for idx, raw_line in enumerate(lines):
        stripped = raw_line.strip()

        # ---- Detect "Data da F icha" header ----
        hdr = re.match(r"Data da F ?icha\s+(.*)", stripped, re.IGNORECASE)
        if hdr:
            current_dates = []
            for dm in re.finditer(r"\b(\d{2})/(\d{2})/(\d{4})\b", hdr.group(1)):
                try:
                    d = date(int(dm.group(3)), int(dm.group(2)), int(dm.group(1)))
                    current_dates.append(d)
                except ValueError:
                    pass
            N = len(current_dates)
            pending_name = ""
            last_batch_start = -1
            continue

        if not current_dates:
            continue
        if _is_skip_evo(stripped):
            continue

        # ---- Try to parse as data line ----
        tokens = stripped.split()
        if not tokens:
            continue

        # Find where values start
        value_start = None
        for j, tok in enumerate(tokens):
            if _VALUE_TOK.match(tok):
                value_start = j
                break

        if value_start is not None:
            # Extract exam name prefix (tokens before first value)
            name_prefix = " ".join(tokens[:value_start]).strip()
            remaining = tokens[value_start:]

            # Collect up to N values
            values: list[str] = []
            ref_idx = 0
            for j, tok in enumerate(remaining):
                if len(values) >= N:
                    ref_idx = j
                    break
                if _VALUE_TOK.match(tok):
                    values.append(tok)
                    ref_idx = j + 1
                else:
                    ref_idx = j
                    break

            reference = " ".join(remaining[ref_idx:]).strip()
            unit = _extract_unit(reference)

            # Resolve full exam name (prefix + accumulated pending)
            full_name = (pending_name + " " + name_prefix).strip()
            full_name = re.sub(r"\s*[-]+\s*$", "", full_name).strip()
            pending_name = ""

            # Skip junk names
            if not full_name or len(full_name) < 3 or len(full_name) > 80:
                last_batch_values_only = (value_start == 0)
                continue
            if _JUNK_EXAM_NAME_RE.search(full_name):
                last_batch_values_only = (value_start == 0)
                continue

            last_batch_values_only = (value_start == 0)
            batch_start = len(results)

            for i, val in enumerate(values):
                if re.match(r"^-+$", val):
                    continue  # absent value
                if i >= len(current_dates) or not current_dates[i]:
                    continue
                clean_val = val.replace(",", ".")
                results.append(ExamResult(
                    exam_name=full_name,
                    value=clean_val,
                    unit=unit,
                    reference_range=reference if reference else None,
                    date=current_dates[i],
                    lab=lab,
                    source_file=filename,
                ))

            if len(results) > batch_start:
                last_batch_start = batch_start

        else:
            # Pure text line — determine if it's a prefix or suffix
            # Lookahead: is the next non-skip line a data line?
            next_has_values = False
            for ahead in range(idx + 1, min(idx + 6, n_lines)):
                s2 = lines[ahead].strip()
                if not s2 or _is_skip_evo(s2):
                    continue
                if re.match(r"Data da F ?icha\b", s2, re.IGNORECASE):
                    break
                next_has_values = _has_values(s2)
                break

            # Decide: suffix for last batch, or prefix for next exam?
            # If last data line was values-only (value_start==0), this is a suffix.
            # Otherwise, if next line has values, this is a prefix.
            is_suffix = last_batch_values_only and last_batch_start >= 0 and len(results) > last_batch_start
            if is_suffix:
                for j in range(last_batch_start, len(results)):
                    r = results[j]
                    results[j] = ExamResult(
                        exam_name=(r.exam_name + " " + stripped).strip(),
                        value=r.value,
                        unit=r.unit,
                        reference_range=r.reference_range,
                        date=r.date,
                        lab=r.lab,
                        source_file=r.source_file,
                    )
                last_batch_start = -1
            elif next_has_values:
                # It's a prefix for the next exam
                pending_name = (pending_name + " " + stripped).strip()
                last_batch_start = -1
            else:
                # Pure text with no adjacent values: treat as pending prefix
                # (Avoids incorrectly merging unrelated exam names as suffixes)
                pending_name = (pending_name + " " + stripped).strip()
                last_batch_start = -1

    # Post-filter: remove entries with junk exam names (e.g. from suffix appending)
    results = [
        r for r in results
        if r.exam_name
        and 2 < len(r.exam_name) <= 80
        and not _JUNK_EXAM_NAME_RE.search(r.exam_name)
    ]
    return results


# ---------------------------------------------------------------------------
# Individual block format parser (A+ and Marcelo Magalhães)
# ---------------------------------------------------------------------------

# Sentinel for "RESULTADO VALORES DE REFERÊNCIA" / "RESULTADO VALOR DE REFERÊNCIA"
_RESULTADO_RE = re.compile(
    r"RESULTADO\s+VALOR(?:ES)?\s+(?:DE\s+)?REFERÊNCIA", re.IGNORECASE
)

# Lines that signal the end of a result block
_BLOCK_END_RE = re.compile(
    r"^(Liberado em|LIBERADO EM|Resp\.|RECEBIDO|Assinatura|CRBM|CRM:|"
    r"Padrão de referência|Ficha No\.|www\.|Nota:|OBS\.|Amostra)",
    re.IGNORECASE,
)

# Known section/meta lines to skip
_BLOCK_META_RE = re.compile(
    r"^(Método:|Imunoensaio|Eletroquimio|Ensaio eletro|Cálculo|"
    r"VALORES DE REFERÊNCIA|RESULTADO|"
    r"[-=]{5,}|%\s*/mm3|CARACTERES|SÉRIE BRANCA|PLAQUETAS\s*[=]{3,}|"
    r"HEMOGRAMA|normais$|não foram|com confirmação|impedância|"
    r"nas equações|Normalizada para|Padrão de referência|"
    r"Fórmula de |Fleury S/A|Resultado\s+Resultados|atual\s+Valores de)",
    re.IGNORECASE,
)

# Junk exam name patterns (for post-extraction validation)
_JUNK_EXAM_NAME_RE = re.compile(
    r"Anvisa|CRBM\d|CRF\s*\d|\bEmitido em\b|Responsável Técnico|"
    r"Fleury S/A|\bamaissaude\b|resultados_exames|impresso em|"
    r"\bCRM\b|Aspecto,\s*urina|Pré-púberes|\bFicha:|"
    r"nas equações|Os intervalos de referência|laudo evolutivo proporciona|"
    r"Ver resultado tradicional|atual\s+Valores de|"
    r"Resultado\s+Resultados anteriores|Resultado\s+Valores de|"
    r"\bAdultos:",
    re.IGNORECASE,
)

# Pattern: EXAM_NAME : VALUE UNIT  REF  (tabular hemograma format)
_TABULAR_RE = re.compile(
    r"^([A-ZÁÉÍÓÚÀÈÌÒÙÃÕ][A-ZÁÉÍÓÚÀÈÌÒÙÃÕÂÊÎÔÛÇ\s,\-\(\)]{2,60?}?)\s*:\s*"
    r"([<>]?\d[\d,\.]*)\s+"
    r"([\w/%\.]+)"
    r"(?:\s+(.+))?$",
)

# Pattern: EXAM_NAME  VALUE  REF  (no colon, hemograma total)
_TABULAR_NO_COLON_RE = re.compile(
    r"^([A-ZÁÉÍÓÚÀÈÌÒÙÃÕ][A-ZÁÉÍÓÚÀÈÌÒÙÃÕÂÊÎÔÛÇ\s,\-\(\)]{2,60?}?)\s{2,}"
    r"([\d\.]+(?:\.\d+)?)\s+"
    r"(\d[\d\.\s]+a\s+\d[\d\.]+)$",
)


def _parse_block_format(full_text: str, lab: str, filename: str,
                        exam_date: Optional[date]) -> list[ExamResult]:
    """
    Parse individual exam block format.

    Each exam looks like:
        EXAM NAME[, descriptor]
        [Método: ...]
        RESULTADO VALORES DE REFERÊNCIA
        VALUE UNIT  ...ref...
        [Liberado em: ...]
    """
    if not exam_date:
        return []

    results: list[ExamResult] = []
    lines = full_text.split("\n")
    n = len(lines)

    i = 0
    while i < n:
        if _RESULTADO_RE.search(lines[i]):
            # Find exam name: scan backwards for the last substantial line
            exam_name = ""
            for back in range(i - 1, max(i - 8, -1), -1):
                candidate = lines[back].strip()
                if not candidate:
                    continue
                # Skip meta/method lines
                if _BLOCK_META_RE.search(candidate):
                    continue
                # Skip page headers like "DD/MM/YYYY a+ Medicina..." or "Cliente:"
                if re.match(r"^\d{2}/\d{2}/\d{4}\s+\w", candidate):
                    continue
                if re.match(r"^(Cliente:|Data de Nasc|Médico:|Ficha:|Praça|Av |Rua )", candidate, re.IGNORECASE):
                    continue
                # Skip lines containing URL or "Cliente:" anywhere (page headers/watermarks)
                if re.search(r"https?://|www\.", candidate, re.IGNORECASE):
                    continue
                if re.search(r"Cliente:", candidate, re.IGNORECASE):
                    continue
                # Found the exam name
                exam_name = candidate
                # Strip trailing separator decorators like "====" or "----"
                exam_name = re.sub(r"\s*[=\-]{3,}\s*$", "", exam_name).strip()
                # Strip trailing ", soro" or ", sangue total" etc.
                exam_name = re.sub(r",\s*(soro|sangue total|plasma|urina|sangue).*$", "", exam_name, flags=re.IGNORECASE).strip()
                # Strip trailing method indicator like "(FSH)"
                exam_name = re.sub(r"\s*\(.*?\)\s*$", lambda m: m.group(0) if not re.search(r"\d", m.group(0)) else "", exam_name).strip()
                break

            if not exam_name or len(exam_name) < 3 or len(exam_name) > 120:
                i += 1
                continue
            if _JUNK_EXAM_NAME_RE.search(exam_name):
                i += 1
                continue
            # Skip if looks like a page header starting with short date (D/M/YYYY or D/M/YY)
            if re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}', exam_name):
                i += 1
                continue
            # Skip if name contains embedded values+dashes (e.g. Laudo Evolutivo header row)
            if re.search(r'\d.*-{4}|-{4}.*\d', exam_name):
                i += 1
                continue

            # Find value: scan forward for first numeric line
            value = ""
            unit = None
            reference = ""
            for fwd in range(i + 1, min(i + 10, n)):
                candidate = lines[fwd].strip()
                if not candidate:
                    continue
                if _BLOCK_END_RE.search(candidate):
                    break
                if _BLOCK_META_RE.search(candidate):
                    continue
                if _RESULTADO_RE.search(candidate):
                    break

                # Try to match VALUE UNIT or VALUE at start of line
                vm = re.match(r"^([<>]?\d[\d,\.]*)\s*([\w/%\.µμ]+)?\s*(.*)?$", candidate)
                if vm:
                    value = vm.group(1).replace(",", ".")
                    unit = vm.group(2) or None
                    reference = (vm.group(3) or "").strip()
                    break

                # Some exams have value embedded mid-line (e.g., DHEA-S)
                em = re.search(r"\b(\d[\d,\.]+)\s+([\w/%\.]+)\s*$", candidate)
                if em:
                    value = em.group(1).replace(",", ".")
                    unit = em.group(2)
                    break

            if value and exam_name:
                results.append(ExamResult(
                    exam_name=exam_name,
                    value=value,
                    unit=unit,
                    reference_range=reference if reference else None,
                    date=exam_date,
                    lab=lab,
                    source_file=filename,
                ))

        i += 1

    return results


def _parse_tabular_hemograma(full_text: str, lab: str, filename: str,
                              exam_date: Optional[date]) -> list[ExamResult]:
    """
    Parse tabular hemograma format:
        ERITRÓCITOS : 4,38 milhões/mm3  4,32 a 5,67
        LEUCÓCITOS  5.660  3.650 a 8.120
        Neutrófilos : 70,5  3.990  1.590 a 4.770
    """
    if not exam_date:
        return []

    results: list[ExamResult] = []
    for line in full_text.split("\n"):
        stripped = line.strip()

        # Try colon format
        m = _TABULAR_RE.match(stripped)
        if m:
            exam_name = m.group(1).strip().rstrip(":")
            value = m.group(2).replace(",", ".")
            unit = m.group(3)
            reference = (m.group(4) or "").strip()
            # Skip if exam_name looks like a label
            if re.match(r"^(RESULTADO|VALORES|MÉTODO|MATERIAL|MÉDICO|PACIENTE|LIBERADO)", exam_name, re.IGNORECASE):
                continue
            results.append(ExamResult(
                exam_name=exam_name,
                value=value,
                unit=unit,
                reference_range=reference if reference else None,
                date=exam_date,
                lab=lab,
                source_file=filename,
            ))
            continue

        # Try no-colon format (e.g., LEUCÓCITOS 5.660 3.650 a 8.120)
        m2 = _TABULAR_NO_COLON_RE.match(stripped)
        if m2:
            exam_name = m2.group(1).strip()
            value = m2.group(2).replace(",", ".")
            reference = m2.group(3).strip()
            if re.match(r"^(RESULTADO|VALORES|MÉTODO|PACIENTE)", exam_name, re.IGNORECASE):
                continue
            results.append(ExamResult(
                exam_name=exam_name,
                value=value,
                unit=None,
                reference_range=reference if reference else None,
                date=exam_date,
                lab=lab,
                source_file=filename,
            ))

    return results


# ---------------------------------------------------------------------------
# Main parsing entry point
# ---------------------------------------------------------------------------

def parse_pdf_bytes(pdf_bytes: bytes, filename: str) -> ParsedDocument:
    """Extract exam results from a PDF file given as raw bytes."""
    doc = ParsedDocument(source_file=filename, lab="")
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages_text: list[str] = []
            for page in pdf.pages:
                pages_text.append(page.extract_text() or "")

        full_text = "\n".join(pages_text)
        doc.lab = _detect_lab(full_text, filename)

        is_evolutionary = bool(
            re.search(r"laudo\s+evolutivo", full_text, re.IGNORECASE)
        ) and bool(re.search(r"Data da F ?icha", full_text, re.IGNORECASE))

        is_individual = bool(_RESULTADO_RE.search(full_text))

        if is_evolutionary:
            doc.results.extend(_parse_laudo_evolutivo(full_text, doc.lab, filename))

        if is_individual:
            exam_date = _extract_ficha_date(full_text) or _extract_date_from_filename(filename)
            block_results = _parse_block_format(full_text, doc.lab, filename, exam_date)
            tabular_results = _parse_tabular_hemograma(full_text, doc.lab, filename, exam_date)
            # Merge, preferring block results; add tabular only if not already captured
            existing = {(r.exam_name.upper(), str(r.date)) for r in doc.results + block_results}
            doc.results.extend(block_results)
            for r in tabular_results:
                key = (r.exam_name.upper(), str(r.date))
                if key not in existing:
                    doc.results.append(r)
                    existing.add(key)

        if not doc.results:
            # Last resort: try block and tabular on any PDF
            exam_date = _extract_ficha_date(full_text) or _extract_date_from_filename(filename)
            doc.results.extend(_parse_block_format(full_text, doc.lab, filename, exam_date))
            doc.results.extend(_parse_tabular_hemograma(full_text, doc.lab, filename, exam_date))

    except Exception as e:
        doc.parse_errors.append(str(e))

    return doc


def parse_pdf_file(path: "str | Path") -> ParsedDocument:
    path = Path(path)
    return parse_pdf_bytes(path.read_bytes(), path.name)


def parse_zip_file(path: "str | Path") -> list[ParsedDocument]:
    """Extract and parse all PDFs inside a ZIP archive."""
    path = Path(path)
    documents = []
    with zipfile.ZipFile(path, "r") as zf:
        for info in zf.infolist():
            if info.filename.lower().endswith(".pdf"):
                pdf_bytes = zf.read(info.filename)
                filename = Path(info.filename).name
                doc = parse_pdf_bytes(pdf_bytes, filename)
                documents.append(doc)
    return documents


def parse_input(path: "str | Path") -> list[ParsedDocument]:
    """Auto-detect file type and parse accordingly."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        return parse_zip_file(path)
    elif path.suffix.lower() == ".pdf":
        return [parse_pdf_file(path)]
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")
