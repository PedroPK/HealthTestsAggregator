from src.parser import parse_zip_file

docs = parse_zip_file('Exames de Sangue-20260425T193934Z-3-001.zip')
total_results = sum(len(d.results) for d in docs)
total_errors = sum(len(d.parse_errors) for d in docs)
print(f'Parsed {len(docs)} PDFs, {total_results} exam results, {total_errors} errors')
print()

for doc in docs[:8]:
    print(f'FILE: {doc.source_file}')
    print(f'  Lab: {doc.lab}')
    print(f'  Results: {len(doc.results)}')
    for r in doc.results[:5]:
        print(f'    {r.exam_name}: {r.value} {r.unit or ""} [{r.date}]')
    if doc.parse_errors:
        print(f'  ERRORS: {doc.parse_errors[:2]}')
    print()
