# -*- coding: utf-8 -*-
"""Вшивает файлы из data/uploads в локальную SQLite (колонка file_data BLOB).

Запуск:  python patch_local_files.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from app import db
from app.config import settings
import os

db.init_db()

updir = settings.abs_upload_dir()
print("Папка загрузок:", updir)

rows = db.query("SELECT id, sha256, filename FROM documents WHERE file_data IS NULL")
print(f"Документов без file_data: {len(rows)}")
fixed = 0
missing = 0
for r in rows:
    prefix = (r["sha256"] or "")[:16]
    if not prefix:
        print(f"  ⚠️ id={r['id']} без sha256: {r['filename']}")
        continue
    matches = list(updir.glob(prefix + "_*"))
    if not matches:
        print(f"  ⚠️ id={r['id']} файл не найден: {r['filename']}")
        missing += 1
        continue
    data = matches[0].read_bytes()
    db.execute("UPDATE documents SET file_data = ? WHERE id = ?", (data, r["id"]))
    fixed += 1

print(f"\n✅ Вшито файлов: {fixed}")
print(f"❌ Не найдено файлов: {missing}")
