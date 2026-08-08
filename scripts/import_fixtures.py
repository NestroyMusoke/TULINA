"""Copy the canonical source pack without mutating signed fixture records."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"C:\Users\X1 Yoga\Documents\Codex\2026-08-08\do\outputs\mobius_relay_dataset_v2")
DEST = ROOT / "data" / "fixtures"


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    source_json = SOURCE / "MOBIUS_Relay_Data_Pack_v2.json"
    target_json = DEST / "tulina_source_pack_v2.json"
    shutil.copyfile(source_json, target_json)
    source_workbook = SOURCE / "MOBIUS_Relay_Demo_Dataset_v2.xlsx"
    target_workbook = DEST / "tulina_source_workbook_v2.xlsx"
    shutil.copyfile(source_workbook, target_workbook)
    source_image = SOURCE / "stock_card_scan_demo.png"
    target_image = DEST / "stock_card_scan_demo.png"
    shutil.copyfile(source_image, target_image)
    shutil.copyfile(SOURCE / "MOBIUS_Relay_Dataset_README.md", DEST / "SOURCE_README.md")
    payload = json.loads(target_json.read_text(encoding="utf-8-sig"))
    manifest = {
        "source_filename": source_json.name,
        "imported_as": target_json.name,
        "files": {
            target_json.name: hashlib.sha256(target_json.read_bytes()).hexdigest(),
            target_workbook.name: hashlib.sha256(target_workbook.read_bytes()).hexdigest(),
            target_image.name: hashlib.sha256(target_image.read_bytes()).hexdigest(),
        },
        "dataset_id": payload["metadata"]["dataset_id"],
        "source_version": payload["metadata"]["version"],
        "display_product": "Tulina",
        "translation_rule": "Legacy names are never rewritten inside signed or hashed fixtures.",
        "contains_patient_data": payload["metadata"]["contains_patient_data"],
        "contains_private_keys": payload["metadata"]["contains_private_keys"],
    }
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(manifest['files'])} canonical assets without mutation")


if __name__ == "__main__":
    main()
