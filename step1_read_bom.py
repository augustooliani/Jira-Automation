import pandas as pd

bom_file = r"input\BOM.xlsx"
sheet_name = "RTD900-Main_DVT_cs2400b_2026052"

# Troque estes nomes pelos nomes reais da sua BOM
status_column = "R&D Remarks"
part_number_column = "Alternative"
line_column = "Designator"

df = pd.read_excel(bom_file, sheet_name=sheet_name, engine="openpyxl")

# Normaliza a coluna de status para evitar erro com maiúsculas/minúsculas
df[status_column] = df[status_column].fillna("").astype(str).str.strip().str.lower()

# Filtra linhas contendo "need erf"
filtered = df[df[status_column].str.contains("need erf", na=False)].copy()

print(f"Total de linhas com need erf: {len(filtered)}")
print(filtered[[line_column, part_number_column, status_column]].head(20))