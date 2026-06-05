import csv
from pathlib import Path
from datetime import datetime


def export_csv(
    rows: list[dict],
    source_filename: str,
    output_dir: str = "data/exports",
) -> str:
    source_name = Path(source_filename).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_name = f"NL-{source_name}_{timestamp}.csv"
    output_path = Path(output_dir) / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        output_path.write_text("", encoding="utf-8-sig")
        return str(output_path)

    fieldnames = list(rows[0].keys())

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return str(output_path)
