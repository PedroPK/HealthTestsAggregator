from src.parser import parse_zip_file

docs = parse_zip_file('Exames de Sangue-20260425T193934Z-3-001.zip')
junk_patterns = ['anvisa', 'emitido', 'crm', 'resultado valores', 'atual valores']
for doc in docs:
    for r in doc.results:
        name_lower = r.exam_name.lower()
        if any(p in name_lower for p in junk_patterns):
            print(f"{r.exam_name!r}")
            print(f"  -> {r.source_file}")
            print()
