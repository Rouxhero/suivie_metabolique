import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

# Générée par prepare_data.py
DB_FILE = Path(__file__).parent / "openfoodfacts" / "foods.db"
FIELDS = "code, product_name, brands, kcal_100g, proteins_100g, carbohydrates_100g, fat_100g"

app = FastAPI()


def connect():
    db = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def fts_query(q):
    # "pate noisette" -> "pate"* "noisette"* : chaque mot doit apparaître, en préfixe
    return " ".join(f'"{word.replace(chr(34), "")}"*' for word in q.split())


@app.get("/api/items")
def get_items(q: str = "", offset: int = 0, limit: int = Query(50, le=500)):
    with closing(connect()) as db:
        if q.strip():
            where = "WHERE id IN (SELECT rowid FROM foods_fts WHERE foods_fts MATCH ?)"
            params = [fts_query(q)]
        else:
            where, params = "", []
        total = db.execute(f"SELECT COUNT(*) FROM foods {where}", params).fetchone()[0]
        rows = db.execute(
            f"SELECT {FIELDS} FROM foods {where} ORDER BY id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


@app.get("/", response_class=HTMLResponse)
def index():
    return """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Aliments Open Food Facts</title>
<style>
  body { font-family: sans-serif; margin: 2rem; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border-bottom: 1px solid #ddd; padding: .4rem .6rem; text-align: left; }
  td.num { text-align: right; }
</style>
</head>
<body>
<h1>Aliments</h1>
<input id="q" placeholder="Rechercher un aliment..." size="40">
<button id="prev">&larr;</button> <button id="next">&rarr;</button>
<span id="info"></span>
<table>
  <thead><tr><th>Code</th><th>Nom</th><th>Marque</th><th>kcal</th><th>Protéines</th><th>Glucides</th><th>Lipides</th></tr></thead>
  <tbody id="rows"></tbody>
</table>
<script>
const LIMIT = 50;
let offset = 0, total = 0;

async function load() {
  const q = document.getElementById("q").value;
  const res = await fetch(`/api/items?q=${encodeURIComponent(q)}&offset=${offset}&limit=${LIMIT}`);
  const data = await res.json();
  total = data.total;
  document.getElementById("info").textContent =
    `${offset + 1}-${Math.min(offset + LIMIT, total)} sur ${total}`;
  const tbody = document.getElementById("rows");
  tbody.replaceChildren(...data.items.map(i => {
    const tr = document.createElement("tr");
    for (const [key, num] of [["code"], ["product_name"], ["brands"], ["kcal_100g", 1],
                              ["proteins_100g", 1], ["carbohydrates_100g", 1], ["fat_100g", 1]]) {
      const td = document.createElement("td");
      td.textContent = i[key];
      if (num) td.className = "num";
      tr.appendChild(td);
    }
    return tr;
  }));
}

document.getElementById("q").addEventListener("change", () => { offset = 0; load(); });
document.getElementById("prev").onclick = () => { offset = Math.max(0, offset - LIMIT); load(); };
document.getElementById("next").onclick = () => { if (offset + LIMIT < total) { offset += LIMIT; load(); } };
load();
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8123)
