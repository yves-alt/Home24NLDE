import csv
import io
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


def generate_csv_bytes(
    headers: list,
    data_rows: list,
    translation_map: dict,
) -> bytes:
    """Return UTF-8 BOM CSV bytes with translations applied.

    headers: column names in order.
    data_rows: list of row dicts with original values.
    translation_map: {row_idx (0-based): {col_name: dutch_value}}
    """
    clean_headers = [h for h in headers if h]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=clean_headers, extrasaction="ignore")
    writer.writeheader()

    for row_idx, row_dict in enumerate(data_rows):
        col_trans = translation_map.get(row_idx, {})
        out_row = {}
        for h in clean_headers:
            if h in col_trans:
                out_row[h] = col_trans[h]
            else:
                val = row_dict.get(h)
                out_row[h] = str(val) if val is not None else ""
        writer.writerow(out_row)

    return ("﻿" + buf.getvalue()).encode("utf-8")
