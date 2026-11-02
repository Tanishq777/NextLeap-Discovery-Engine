"""
restore_golden_19.py — Instantly restores the exact golden 19-record, 10-area, 26.3% baseline.
"""
import shutil
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "data", "golden_19_backup")

if not os.path.exists(BACKUP_DIR):
    print("Error: Backup directory not found!")
    sys.exit(1)

shutil.copyfile(os.path.join(BACKUP_DIR, "discovery_engine.db"), os.path.join(BASE_DIR, "data", "discovery_engine.db"))
shutil.copyfile(os.path.join(BACKUP_DIR, "bundle.json"), os.path.join(BASE_DIR, "data", "bundle.json"))
shutil.copyfile(os.path.join(BACKUP_DIR, "bundle.json"), os.path.join(BASE_DIR, "api", "bundle.json"))
shutil.copyfile(os.path.join(BACKUP_DIR, "bundle.json"), os.path.join(BASE_DIR, "api", "data", "bundle.json"))
shutil.copyfile(os.path.join(BACKUP_DIR, "bundle.json"), os.path.join(BASE_DIR, "bundle.json"))
shutil.copyfile(os.path.join(BACKUP_DIR, "raw_items.csv"), os.path.join(BASE_DIR, "data", "raw_items.csv"))
shutil.copyfile(os.path.join(BACKUP_DIR, "tagged_items.json"), os.path.join(BASE_DIR, "data", "tagged_items.json"))
shutil.copyfile(os.path.join(BACKUP_DIR, "opportunity_areas.csv"), os.path.join(BASE_DIR, "data", "opportunity_areas.csv"))

print("Successfully restored Golden 19 Baseline (19 signals, 10 areas, 26.3% abandonment rate).")
