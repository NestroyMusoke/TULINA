# Data provenance

The canonical JSON pack, Excel workbook, stock-card image, and dataset README are imported byte-for-byte into `data/fixtures/`. The importer records SHA-256 digests for the three binary/data assets. It deliberately does not rewrite the legacy dataset ID, workbook formulas, signed capsule payload, hashes, public keys, signatures, nonces, device IDs, or acceptance vectors.

Product-facing copy uses Tulina. Source-internal legacy labels remain only where mutation would invalidate provenance or cryptographic integrity.

Facility identities, products, policy references, and public evidence are research-backed. Inventory, consumption, devices, transfers, disruptions, and crypto test events are synthetic development fixtures dated August 2026. They are not current facility stock. The pack contains no patient data and no private keys.

`stock_card_extraction_v1.json` is a Tulina-authored derivative fixture, not an original source asset. It faithfully transcribes the supplied synthetic `stock_card_scan_demo.png` and includes normalized evidence regions and confidence values for credential-free replay. The runtime first verifies the original image against the importer-recorded SHA-256; it never uses this saved extraction for another image.
