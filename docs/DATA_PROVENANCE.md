# Data provenance

The canonical JSON pack, Excel workbook, stock-card image, and dataset README are imported byte-for-byte into `data/fixtures/`. The importer records SHA-256 digests for the three binary/data assets. It deliberately does not rewrite the legacy dataset ID, workbook formulas, signed capsule payload, hashes, public keys, signatures, nonces, device IDs, or acceptance vectors.

Product-facing copy uses Tulina. Source-internal legacy labels remain only where mutation would invalidate provenance or cryptographic integrity.

Facility identities, products, policy references, and public evidence are research-backed. Inventory, consumption, devices, transfers, disruptions, and crypto test events are synthetic development fixtures dated August 2026. They are not current facility stock. The pack contains no patient data and no private keys.
