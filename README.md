# DJI OSMO Pocket Firmware Extraction Tool

**Test folder for extract_firmware_complete.py**

---

## Contents

- `extract_firmware_complete.py` - Main extraction script
- `run_extraction.sh` - Bash wrapper
- `V01.10.00.30_OSMO_Pocket/` - Test extraction results
- `CORRECCIONES_IMPLEMENTADAS.md` - Implementation notes

---

## Quick Start

```bash
python3 extract_firmware_complete.py /path/to/firmware.bin
```

---

## Output

```
firmware_name/
├── lz4_payload.bin
├── firmware_decompressed.bin (162 MB)
└── squashfs-extracted/ (697 files)
```

---

**Author:** sharklatan | **Version:**| **License:** MIT
