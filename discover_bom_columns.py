"""Imprime as colunas reais da BOM."""
import pandas as pd
import config

df = pd.read_excel(config.BOM_FILE, sheet_name=config.BOM_SHEET, engine="openpyxl")
print("Colunas da planilha:")
for c in df.columns:
    print(f"  - {c!r}")

print("\nPrimeira linha 'need erf' (para conferir valores):")
mask = df[config.COLUMN_STATUS].fillna("").astype(str).str.lower().str.contains("need erf")
if mask.any():
    print(df[mask].iloc[0].to_dict())
