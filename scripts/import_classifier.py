"""Import classifier types as reference data, preserving source rows; no inferred routing."""
import json, sys, hashlib
from pathlib import Path
import openpyxl

source=Path(sys.argv[1])
book=openpyxl.load_workbook(source,data_only=True,read_only=True)
sheet=book['Лист1']
rows=[]; seen=set()
for row in sheet.iter_rows():
    if len(row)<11 or not isinstance(row[10].value,str) or not row[10].value.strip(): continue
    index=row[10].row
    if index<4: continue
    values=[c.value for c in row]
    if not isinstance(values[0],(int,float)): continue
    code=str(int(sum((values[i] or 0)*factor for i,factor in enumerate([1000000,10000,100,1]))))
    if code in seen: code+='-'+str(index)
    seen.add(code)
    rows.append({'code':code,'title':values[10].strip(),'traits':[str(v).strip() for v in values[6:9] if v is not None],'source':{'file':source.name,'sheet':sheet.title,'row':index,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}})
out=Path(__file__).resolve().parents[1]/'content'/'classifier.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Imported {len(rows)} types into {out}')
