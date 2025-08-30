from flask import Flask, request, jsonify
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import pandas as pd
import os

app = Flask(__name__)
CORS(app)

# ---------- Data loading ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "ufc_fight_data.csv")

# Load once at startup (safer types + tolerant date parsing)
df = pd.read_csv(CSV_PATH, encoding="latin1", low_memory=False)
df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")

# ---------- Helpers ----------
def convert_values(d):
    """Convert numpy / NaN to JSON-safe Python types."""
    out = {}
    for k, v in d.items():
        if pd.isna(v):
            out[k] = None
        elif hasattr(v, "item"):
            out[k] = v.item()
        else:
            out[k] = v
    return out

def format_count(n):
    try:
        n = int(n)
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.0f}K"
        return str(n)
    except (ValueError, TypeError):
        return "N/A"

def get_fighter_stats(name, side):
    """Return one row of stats for a fighter from the given side (fighter_1 or fighter_2)."""
    cols = [c for c in df.columns if c.startswith(f"{side}_")]
    rows = df[df[side] == name]
    if rows.empty:
        return None
    row = rows.iloc[0]
    stats = {c.replace(f"{side}_", ""): row[c] for c in cols}
    stats["side"] = side
    return {"name": name, **convert_values(stats)}

def get_last_5_fights(name):
    mask = (df["fighter_1"] == name) | (df["fighter_2"] == name)
    recent = df[mask].sort_values("event_date", ascending=False).head(5)

    def fmt(row):
        opponent = row["fighter_2"] if row["fighter_1"] == name else row["fighter_1"]
        result = "Win" if row["fighter_1"] == name else "Loss"
        return {"opponent": opponent, "result": result}

    return [fmt(r) for _, r in recent.iterrows()]

def get_ufc_record(name):
    wins = losses = ko = sub = dec = 0
    fights = df[(df["fighter_1"] == name) | (df["fighter_2"] == name)]
    for _, row in fights.iterrows():
        method = str(row.get("method_main", "")).lower()
        winner = row["fighter_1"]  # assumption: fighter_1 is winner in dataset
        if name == winner:
            wins += 1
            if "ko" in method:
                ko += 1
            elif "sub" in method:
                sub += 1
            elif "dec" in method:
                dec += 1
        else:
            losses += 1
    return {
        "UFC Record": f"{wins}-{losses}",
        "Wins by KO": ko,
        "Wins by Submission": sub,
        "Wins by Decision": dec,
    }

def organize_stats(stats):
    name = stats["name"]
    side = stats.get("side", "fighter_1")

    # prefer normalized "ig" key; fallback to side-specific column if present
    ig_count = stats.get("ig")
    if ig_count is None:
        side_key = f"{side}_ig"
        try:
            ig_count = df.loc[df[side] == name, side_key].values[0]
        except Exception:
            ig_count = None

    return {
        "name": name,
        "Bio": {
            "Age": stats.get("current_age"),
            "Born": stats.get("born"),
            "Height": stats.get("height"),
            "Reach": stats.get("reach"),
            "Stance": stats.get("stance"),
            "Gym": stats.get("gym"),
            "IG Count": format_count(ig_count),
        },
        "Record": {
            "Overall Record": f"{stats.get('wins', 0)}-{stats.get('losses', 0)}-{stats.get('draws', 0)}"
        },
        "UFC Record": get_ufc_record(name),
        "Striking": [
            {"label": "Significant Strikes Landed per Minute", "value": stats.get("SLpM")},
            {"label": "Significant Striking Accuracy", "value": stats.get("Str_Acc")},
            {"label": "Significant Strikes Absorbed per Minute", "value": stats.get("SApM")},
            {"label": "Significant Strike Defence", "value": stats.get("Str_Def")},
        ],
        "Grappling": [
            {"label": "Average Takedowns Landed per 15 minutes", "value": stats.get("TD_Avg")},
            {"label": "Takedown Accuracy", "value": stats.get("TD_Acc")},
            {"label": "Takedown Defense", "value": stats.get("TD_Def")},
            {"label": "Average Submissions Attempted per 15 minutes", "value": stats.get("Sub_Avg")},
        ],
        "Last 5 Fights": get_last_5_fights(name),
    }

# ---------- Routes ----------
@app.get("/health")
def health():
    return jsonify(ok=True), 200

@app.get("/matchup")
def matchup_page():
    # templates/matchup.html must exist
    return render_template("matchup.html")

@app.post("/get_stats")
def get_stats():
    data = request.get_json(force=True) or {}
    fighter1 = data.get("fighter1")
    fighter2 = data.get("fighter2")

    stats1 = get_fighter_stats(fighter1, "fighter_1") or get_fighter_stats(fighter1, "fighter_2")
    stats2 = get_fighter_stats(fighter2, "fighter_1") or get_fighter_stats(fighter2, "fighter_2")

    if not stats1 or not stats2:
        return jsonify({"error": "One or both fighters not found"}), 404

    return jsonify({"fighter1": organize_stats(stats1), "fighter2": organize_stats(stats2)})

# For local dev only (App Platform uses gunicorn run command)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
