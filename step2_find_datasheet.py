import pandas as pd
from pathlib import Path

bom_file = r"input\BOM.xlsx"
sheet_name = "RTD900-Main_DVT_cs2400b_2026052"

status_column = "R&D Remarks"
part_number_column = "Alternative"
line_column = "Designator"

datasheet_root = Path(r"datasheets")

def normalize_text(text: str) -> str:
    return (
        str(text).lower()
        .replace("-", "")
        .replace("_", "")
        .replace("/", "")
        .replace(" ", "")
        .strip()
    )

def find_datasheet(part_number: str, root: Path):
    normalized_pn = normalize_text(part_number)
    pdf_files = list(root.rglob("*.pdf"))

    exact_matches = []
    contains_matches = []

    for file in pdf_files:
        normalized_name = normalize_text(file.stem)
        if normalized_name == normalized_pn:
            exact_matches.append(file)
        elif normalized_pn in normalized_name:
            contains_matches.append(file)

    if exact_matches:
        return exact_matches[0]
    if contains_matches:
        return contains_matches[0]
    return None

if __name__ == "__main__":
    df = pd.read_excel(bom_file, sheet_name=sheet_name, engine="openpyxl")
    df[status_column] = df[status_column].fillna("").astype(str).str.strip().str.lower()
    filtered = df[df[status_column].str.contains("need erf", na=False)].copy()

    for _, row in filtered.iterrows():
        line = row[line_column]
        part_number = row[part_number_column]

        datasheet = find_datasheet(part_number, datasheet_root)

        print("-" * 60)
        print(f"Linha: {line}")
        print(f"Part Number: {part_number}")
        if datasheet:
            print(f"Datasheet encontrado: {datasheet}")
        else:
            print("Datasheet não encontrado")
