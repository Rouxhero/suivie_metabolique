"""Télécharge le dump CSV d'Open Food Facts et le convertit en base SQLite.

Usage :
    python prepare_data.py             # télécharge (si absent) puis convertit
    python prepare_data.py --download  # force un nouveau téléchargement
"""
import csv
import gzip
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

URL = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"
DATA_DIR = Path(__file__).parent / "openfoodfacts"
CSV_FILE = DATA_DIR / "en.openfoodfacts.org.products.csv.gz"
DB_FILE = DATA_DIR / "foods.db"

# colonne CSV -> colonne SQLite
COLUMNS = {
    "code": "code",
    "product_name": "product_name",
    "brands": "brands",
    "energy-kcal_100g": "kcal_100g",
    "proteins_100g": "proteins_100g",
    "carbohydrates_100g": "carbohydrates_100g",
    "fat_100g": "fat_100g",
}
NUMERIC = {"kcal_100g", "proteins_100g", "carbohydrates_100g", "fat_100g"}


def download():
    DATA_DIR.mkdir(exist_ok=True)
    tmp = CSV_FILE.with_suffix(".part")
    print(f"Téléchargement de {URL}")
    with urllib.request.urlopen(URL) as response, open(tmp, "wb") as out:
        total = int(response.headers.get("Content-Length", 0))
        done = 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r{done / 1e6:.0f} / {total / 1e6:.0f} Mo ({done * 100 // total} %)", end="", flush=True)
    print()
    tmp.rename(CSV_FILE)


def to_float(value):
    try:
        return float(value)
    except ValueError:
        return None


def read_foods():
    csv.field_size_limit(sys.maxsize)
    with gzip.open(CSV_FILE, "rt", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file, delimiter="\t"):
            # On garde uniquement les aliments qui ont un nom et des calories
            if not row["product_name"] or not row["energy-kcal_100g"]:
                continue
            values = []
            for csv_col, db_col in COLUMNS.items():
                value = row[csv_col]
                values.append(to_float(value) if db_col in NUMERIC else value)
            yield values


def convert():
    print(f"Conversion vers {DB_FILE}")
    start = time.time()
    tmp = DB_FILE.with_suffix(".part")
    tmp.unlink(missing_ok=True)

    db = sqlite3.connect(tmp)
    db.executescript("""
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        CREATE TABLE foods (
            id INTEGER PRIMARY KEY,
            code TEXT,
            product_name TEXT,
            brands TEXT,
            kcal_100g REAL,
            proteins_100g REAL,
            carbohydrates_100g REAL,
            fat_100g REAL
        );
    """)
    db.executemany(
        f"INSERT INTO foods ({', '.join(COLUMNS.values())}) VALUES ({', '.join('?' * len(COLUMNS))})",
        read_foods(),
    )
    count = db.execute("SELECT COUNT(*) FROM foods").fetchone()[0]
    print(f"{count} aliments insérés en {time.time() - start:.0f} s, création des index...")

    db.executescript("""
        CREATE INDEX foods_code ON foods(code);
        -- Index plein texte pour la recherche par nom / marque (insensible aux accents)
        CREATE VIRTUAL TABLE foods_fts USING fts5(
            product_name, brands,
            content = 'foods', content_rowid = 'id',
            tokenize = 'unicode61 remove_diacritics 2'
        );
        INSERT INTO foods_fts(foods_fts) VALUES ('rebuild');
    """)
    db.commit()
    db.execute("VACUUM")
    db.close()

    tmp.rename(DB_FILE)
    print(f"Base prête en {time.time() - start:.0f} s ({DB_FILE.stat().st_size / 1e6:.0f} Mo)")


if __name__ == "__main__":
    if "--download" in sys.argv or not CSV_FILE.exists():
        download()
    convert()
