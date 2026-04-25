import pdfplumber, io, zipfile
from pathlib import Path

zip_path = 'Exames de Sangue-20260425T193934Z-3-001.zip'

# Pick specific files to inspect
targets = [
    '2025.11.23 Laudo Evolutivo e Resultados de Exames de Sangue - Laboratório Marcelo Magalhães.pdf',
    'a+ Medicina Diagnóstica - Ficha_ 8050131496 - 2012.07.08.pdf',
    '2023.04.27 - Resultados Exames de Sangue - Laboratório A+ Ficha 8150373534.pdf',
    '2018 09 29 - Laboratorio A+ - Laudo Atual - 8050393062.pdf',
]

with zipfile.ZipFile(zip_path) as zf:
    names = {Path(n).name: n for n in zf.namelist() if n.endswith('.pdf')}
    for target in targets:
        if target not in names:
            print(f'NOT FOUND: {target}')
            continue
        name = names[target]
        print('='*70)
        print('FILE:', target)
        print('='*70)
        data = zf.read(name)
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, page in enumerate(pdf.pages[:3]):
                print(f'--- PAGE {i+1} ---')
                text = page.extract_text()
                if text:
                    print(text[:3000])
        print()
