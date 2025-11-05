#!/usr/bin/env python3
"""
DJI OSMO POCKET FIRMWARE EXTRACTION TOOL
=========================================
Complete firmware extraction automation.

Workflow:
  1. Identify LZ4 payload using binwalk
  2. Extract LZ4 payload
  3. Decompress LZ4
  4. Identify Squashfs filesystem
  5. Extract Squashfs
  6. Generate extraction reports

Usage:
  python3 extract_firmware_complete.py <firmware.bin>
  
Output:
  <firmware_name>/
    ├── <firmware.bin> (original)
    ├── lz4_payload.bin
    ├── firmware_decompressed.bin
    ├── _firmware_decompressed.bin.extracted/
    │   ├── squashfs-extracted/  (FINAL FILESYSTEM)
    │   └── [other extracted files]
    └── EXTRACTION_REPORT.md

Dependencies:
  - binwalk
  - lz4
  - squashfs-tools (unsquashfs)

---
Author: sharklatan
Version: 2.0 (Multi-version unsquashfs support)
License: MIT

Special Thanks:
  - binwalk developers (https://github.com/ReFirmLabs/binwalk)
  - squashfs-tools contributors (https://github.com/plougher/squashfs-tools)
  - lz4 developers (https://github.com/lz4/lz4)
  - DJI reverse engineering community
"""

import os
import sys
import subprocess
import shutil
import struct
from pathlib import Path
from datetime import datetime

class FirmwareExtractor:
    def __init__(self, firmware_path):
        self.firmware_path = Path(firmware_path)
        self.firmware_name = self.firmware_path.stem
        self.work_dir = self.firmware_path.parent / self.firmware_name
        self.log = []
        
        if not self.firmware_path.exists():
            self.error(f"Firmware no encontrado: {firmware_path}")
            sys.exit(1)
    
    def log_msg(self, msg, level="INFO"):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {msg}"
        print(log_entry)
        self.log.append(log_entry)
    
    def error(self, msg):
        """Log error message"""
        self.log_msg(msg, "ERROR")
    
    def success(self, msg):
        """Log success message"""
        self.log_msg(msg, "SUCCESS")
    
    def run_cmd(self, cmd, description=""):
        """Execute shell command"""
        if description:
            self.log_msg(f"Executing: {description}")
        
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                self.error(f"Failed to execute: {cmd}")
                if result.stderr:
                    self.error(f"Error: {result.stderr}")
                return False
            if result.stdout:
                self.log_msg(result.stdout.strip())
            return True
        except subprocess.TimeoutExpired:
            self.error(f"Timeout executing: {cmd}")
            return False
        except Exception as e:
            self.error(f"Exception: {e}")
            return False
    
    def check_dependencies(self):
        """Verify required tools are available"""
        self.log_msg("Checking dependencies...")
        
        tools = ["binwalk", "lz4", "unsquashfs"]
        
        missing = []
        for tool in tools:
            # Use 'which' to verify tool exists
            result = subprocess.run(f"which {tool}", shell=True, capture_output=True, timeout=5)
            if result.returncode != 0:
                missing.append(tool)
            else:
                self.log_msg(f"  ✓ {tool} found")
        
        if missing:
            self.error(f"Missing tools: {', '.join(missing)}")
            self.error("On Ubuntu/Debian: sudo apt-get install -y binwalk squashfs-tools lz4")
            return False
        
        self.success("All dependencies available")
        return True
    
    def setup_workspace(self):
        """Create working directory"""
        self.log_msg(f"Setting up workspace: {self.work_dir}")
        
        if self.work_dir.exists():
            self.log_msg(f"Directory already exists, using existing")
        else:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            self.success(f"Directory created: {self.work_dir}")
    
    def find_lz4_offset(self):
        """Use binwalk to find LZ4 offset"""
        self.log_msg("Searching for LZ4 with binwalk...")
        
        try:
            result = subprocess.run(
                f"binwalk -B {self.firmware_path}",
                shell=True, capture_output=True, text=True, timeout=60
            )
            
            for line in result.stdout.split('\n'):
                if 'LZ4' in line or 'lz4' in line:
                    # Parse offset (format: "DECIMAL       HEXADECIMAL     DESCRIPTION")
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        offset = int(parts[0])
                        self.success(f"LZ4 found @ offset {offset} (0x{offset:X})")
                        return offset
        except Exception as e:
            self.error(f"Error searching for LZ4: {e}")
        
        # Fallback: default offset for OSMO Pocket
        self.log_msg("Using default offset: 0x17A (378)")
        return 0x17A
    
    def extract_lz4_payload(self, offset):
        """Extract LZ4 payload"""
        self.log_msg(f"Extracting LZ4 payload @ offset 0x{offset:X}...")
        
        lz4_file = self.work_dir / "lz4_payload.bin"
        
        try:
            with open(self.firmware_path, 'rb') as f:
                f.seek(offset)
                lz4_data = f.read()
            
            with open(lz4_file, 'wb') as f:
                f.write(lz4_data)
            
            size_mb = len(lz4_data) / (1024 * 1024)
            self.success(f"LZ4 extracted: {lz4_file} ({size_mb:.2f} MB)")
            return lz4_file
        except Exception as e:
            self.error(f"Error extracting LZ4: {e}")
            return None
    
    def decompress_lz4(self, lz4_file):
        """Decompress LZ4 file"""
        self.log_msg("Decompressing LZ4...")
        
        output_file = self.work_dir / "firmware_decompressed.bin"
        
        cmd = f"lz4 -d -f {lz4_file} {output_file}"
        if self.run_cmd(cmd, "Decompress LZ4"):
            size_mb = output_file.stat().st_size / (1024 * 1024)
            self.success(f"LZ4 decompressed: {output_file} ({size_mb:.2f} MB)")
            return output_file
        
        return None
    
    def find_squashfs_offset(self, decompressed_file):
        """Find Squashfs offset"""
        self.log_msg("Searching for Squashfs in decompressed firmware...")
        
        try:
            result = subprocess.run(
                f"binwalk -B {decompressed_file}",
                shell=True, capture_output=True, text=True, timeout=60
            )
            
            for line in result.stdout.split('\n'):
                if 'squashfs' in line.lower():
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        offset = int(parts[0])
                        self.success(f"Squashfs found @ offset {offset} (0x{offset:X})")
                        return offset
        except Exception as e:
            self.error(f"Error searching for Squashfs: {e}")
        
        return None
    
    def extract_binwalk(self, firmware_file):
        """Run binwalk extraction"""
        self.log_msg("Running binwalk extraction...")
        
        extract_dir = self.work_dir / f"_{firmware_file.name}.extracted"
        
        cmd = f"cd {self.work_dir} && binwalk -e {firmware_file.name}"
        if self.run_cmd(cmd, "Binwalk extraction"):
            if extract_dir.exists():
                self.success(f"Binwalk extract completed: {extract_dir}")
                return extract_dir
        
        return None
    
    def get_unsquashfs_version(self):
        """Get unsquashfs version"""
        try:
            result = subprocess.run(
                "unsquashfs -version",
                shell=True, capture_output=True, text=True, timeout=5
            )
            output = result.stdout + result.stderr
            
            # Typical format: "unsquashfs version 4.4"
            for line in output.split('\n'):
                if 'version' in line.lower():
                    # Extract version number
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part.replace('.', '').isdigit():
                            version_str = part
                            try:
                                major, minor = map(int, version_str.split('.')[:2])
                                return (major, minor)
                            except:
                                pass
            
            # Default: assume old version
            self.log_msg("Could not detect unsquashfs version, using compatible mode")
            return (4, 4)
        except Exception as e:
            self.error(f"Error detecting unsquashfs version: {e}")
            return (4, 4)
    
    def extract_squashfs(self, extract_dir):
        """Extract Squashfs using unsquashfs"""
        self.log_msg("Searching and extracting Squashfs...")
        
        # Find .squashfs file
        squashfs_files = list(extract_dir.glob("*.squashfs"))
        
        if not squashfs_files:
            self.error("No .squashfs file found")
            return None
        
        squashfs_file = squashfs_files[0]
        output_dir = extract_dir / "squashfs-extracted"
        
        self.log_msg(f"Extracting {squashfs_file.name}...")
        
        # Detect unsquashfs version
        version = self.get_unsquashfs_version()
        self.log_msg(f"Detected unsquashfs version: {version[0]}.{version[1]}")
        
        # Select command based on version
        # Versions >= 4.5 support -no-exit-code
        # Versions >= 4.4 support -ignore-errors
        # Versions < 4.4 do not support either option
        
        if version >= (4, 5):
            self.log_msg("Using -no-exit-code option (modern version)")
            cmd = f"cd {extract_dir} && unsquashfs -no-exit-code -d squashfs-extracted {squashfs_file.name}"
        elif version >= (4, 4):
            self.log_msg("Using -ignore-errors option (version 4.4)")
            cmd = f"cd {extract_dir} && unsquashfs -ignore-errors -d squashfs-extracted {squashfs_file.name}"
        else:
            self.log_msg("Old unsquashfs version, no error options available")
            cmd = f"cd {extract_dir} && unsquashfs -d squashfs-extracted {squashfs_file.name} 2>/dev/null || true"
        
        if self.run_cmd(cmd, "Squashfs extraction"):
            if output_dir.exists():
                file_count = sum(1 for _ in output_dir.rglob('*') if _.is_file())
                self.success(f"Squashfs extracted: {output_dir} ({file_count} files)")
                return output_dir
        
        return None
    
    def list_dji_components(self, squashfs_dir):
        """List DJI components found"""
        self.log_msg("Searching for DJI components...")
        
        dji_bins = list(squashfs_dir.glob("usr/bin/dji_*"))
        dji_libs = list(squashfs_dir.glob("usr/lib/libdji*.so*"))
        
        components = {
            "binarios": [],
            "librerias": []
        }
        
        for binary in dji_bins:
            components["binarios"].append(binary.name)
        
        for lib in dji_libs:
            components["librerias"].append(lib.name)
        
        if components["binarios"]:
            self.success(f"Found {len(components['binarios'])} DJI binaries")
            for b in components["binarios"]:
                self.log_msg(f"  - {b}")
        
        if components["librerias"]:
            self.success(f"Found {len(components['librerias'])} DJI libraries")
            for lib in components["librerias"]:
                self.log_msg(f"  - {lib}")
        
        return components
    
    def generate_report(self, components, squashfs_dir, extract_dir):
        """Generate extraction report"""
        self.log_msg("Generating report...")
        
        report_file = self.work_dir / "EXTRACTION_REPORT.md"
        
        # Count files
        total_files = sum(1 for _ in squashfs_dir.rglob('*') if _.is_file())
        total_dirs = sum(1 for _ in squashfs_dir.rglob('*') if _.is_dir())
        
        report = f"""# Extraction Report - {self.firmware_name}

**Date**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Summary

| Parameter | Value |
|-----------|-------|
| Original Firmware | {self.firmware_path.name} |
| Original Size | {self.firmware_path.stat().st_size / (1024*1024):.2f} MB |
| Working Directory | {self.work_dir} |
| Extracted Files | {total_files} |
| Directories | {total_dirs} |

## Extraction Structure

```
{self.work_dir.name}/
├── {self.firmware_path.name} (original)
├── lz4_payload.bin (extracted payload)
├── firmware_decompressed.bin (decompressed)
└── _firmware_decompressed.bin.extracted/
    ├── squashfs-extracted/ (FILESYSTEM - {total_files} files)
    └── [other extracted files]
```

## DJI Components Found

### Binaries ({len(components['binarios'])})
"""
        
        for binary in components['binarios']:
            report += f"- `{binary}`\n"
        
        report += f"\n### Libraries ({len(components['librerias'])})\n"
        
        for lib in components['librerias']:
            report += f"- `{lib}`\n"
        
        report += f"""
## Extraction Process

1. ✅ LZ4 Search
2. ✅ Payload Extraction
3. ✅ LZ4 Decompression
4. ✅ Binwalk Extraction
5. ✅ Squashfs Extraction
6. ✅ Component Analysis

## Execution Logs

"""
        
        for log_entry in self.log:
            report += f"```\n{log_entry}\n```\n"
        
        report += f"""
## Next Steps

```bash
# Analyze DJI binaries
cd {self.work_dir}/_firmware_decompressed.bin.extracted/squashfs-extracted

# List binaries
file usr/bin/dji_*

# Extract strings from components
strings usr/bin/dji_camsrv | head -100

# Disassembly (requires radare2)
r2 -a arm -b 64 usr/bin/dji_visual
```

---
*Automatically generated by extract_firmware_complete.py*
"""
        
        with open(report_file, 'w') as f:
            f.write(report)
        
        self.success(f"Report generated: {report_file}")
    
    def run(self):
        """Run complete extraction process"""
        self.log_msg("="*80)
        self.log_msg(f"DJI FIRMWARE EXTRACTOR - {self.firmware_name}")
        self.log_msg("="*80)
        
        # 1. Check dependencies
        if not self.check_dependencies():
            return False
        
        # 2. Setup workspace
        self.setup_workspace()
        
        # 3. Find LZ4
        lz4_offset = self.find_lz4_offset()
        
        # 4. Extract LZ4 payload
        lz4_file = self.extract_lz4_payload(lz4_offset)
        if not lz4_file:
            return False
        
        # 5. Decompress LZ4
        decompressed_file = self.decompress_lz4(lz4_file)
        if not decompressed_file:
            return False
        
        # 6. Binwalk extract
        extract_dir = self.extract_binwalk(decompressed_file)
        if not extract_dir:
            return False
        
        # 7. Extract Squashfs
        squashfs_dir = self.extract_squashfs(extract_dir)
        if not squashfs_dir:
            return False
        
        # 8. List components
        components = self.list_dji_components(squashfs_dir)
        
        # 9. Generate report
        self.generate_report(components, squashfs_dir, extract_dir)
        
        self.log_msg("="*80)
        self.success("EXTRACTION COMPLETED SUCCESSFULLY")
        self.log_msg("="*80)
        
        return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUsage:")
        print("  python3 extract_firmware_complete.py /path/to/firmware.bin")
        sys.exit(1)
    
    firmware_path = sys.argv[1]
    
    extractor = FirmwareExtractor(firmware_path)
    success = extractor.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
