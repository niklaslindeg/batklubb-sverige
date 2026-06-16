"""
Flask-server för Båtklubb Sverige.
Kör: python server.py
Öppna: http://localhost:5000
"""

import json
from pathlib import Path
from flask import Flask, jsonify, send_from_directory

app = Flask(__name__, static_folder="static")

DATA_FILE = Path("data/clubs.json")
STOCKHOLM_FILE = Path("data/stockholm_clubs.json")


def load_clubs() -> list[dict]:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/clubs")
def api_clubs():
    clubs = load_clubs()
    # Filtrera bort klubbar utan koordinater för kartan
    with_coords = [c for c in clubs if "lat" in c and "lon" in c]
    without_coords = [c for c in clubs if "lat" not in c or "lon" not in c]
    return jsonify({
        "total": len(clubs),
        "mapped": len(with_coords),
        "unmapped": len(without_coords),
        "clubs": clubs,
    })


@app.route("/stockholm")
def stockholm():
    return send_from_directory("static", "stockholm.html")


@app.route("/api/stockholm")
def api_stockholm():
    from flask import request
    if not STOCKHOLM_FILE.exists():
        return jsonify([])
    clubs = json.loads(STOCKHOLM_FILE.read_text(encoding="utf-8"))
    q = request.args.get("q", "").lower().strip()
    district = request.args.get("district", "").strip()
    if q:
        clubs = [c for c in clubs if q in c.get("name", "").lower() or q in c.get("district", "").lower() or q in c.get("address", "").lower()]
    if district and district != "all":
        clubs = [c for c in clubs if c.get("district") == district]
    return jsonify(clubs)


@app.route("/data/<path:filename>")
def serve_data(filename):
    return send_from_directory("data", filename)


@app.route("/api/clubs/search")
def api_search():
    from flask import request
    query = request.args.get("q", "").lower().strip()
    clubs = load_clubs()
    if query:
        clubs = [
            c for c in clubs
            if query in c.get("name", "").lower()
            or query in c.get("city", "").lower()
            or query in c.get("address", "").lower()
        ]
    return jsonify(clubs)


if __name__ == "__main__":
    if not DATA_FILE.exists():
        print("OBS: data/clubs.json saknas. Kör 'python scraper.py' först.")
        print("Startar ändå med tom datamängd...\n")
    print("Server startar på http://localhost:5000")
    app.run(debug=True, port=5000)
