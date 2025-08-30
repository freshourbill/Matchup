from flask import Flask, request, jsonify
import pandas as pd
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Load UFC fight data
df = pd.read_csv('ufc_fight_data.csv', encoding='latin1')
df['event_date'] = pd.to_datetime(df['event_date'])

# Convert values to native Python types
def convert_values(d):
    return {k: (str(v) if pd.isnull(v) else v.item() if hasattr(v, 'item') else v) for k, v in d.items()}

# Format IG Count
def format_count(n):
    try:
        n = int(n)
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        elif n >= 1_000:
            return f"{n / 1_000:.0f}K"
        else:
            return str(n)
    except (ValueError, TypeError):
        return "N/A"


# Get stats for a given fighter on either side
def get_fighter_stats(name, side):
    cols = [col for col in df.columns if col.startswith(f'{side}_')]
    fighter_rows = df[df[f'{side}'] == name]

    if fighter_rows.empty:
        return None

    row = fighter_rows.iloc[0]
    stats = {col.replace(f'{side}_', ''): row[col] for col in cols}
    stats['side'] = side  # remember which side this fighter was found on
    return {'name': name, **convert_values(stats)}

# Get last 5 fights for a given fighter
def get_last_5_fights(name):
    mask = (df['fighter_1'] == name) | (df['fighter_2'] == name)
    recent_fights = df[mask].sort_values('event_date', ascending=False).head(5)

    def format_fight(row):
        opponent = row['fighter_2'] if row['fighter_1'] == name else row['fighter_1']
        result = 'Win' if row['fighter_1'] == name else 'Loss'
        return {
            'opponent': opponent,
            'result': result
        }

    return [format_fight(row) for _, row in recent_fights.iterrows()]

# Get UFC Record based on assumption fighter_1 is always winner
def get_ufc_record(name):
    wins = 0
    losses = 0
    ko = 0
    sub = 0
    dec = 0

    fighter_fights = df[(df['fighter_1'] == name) | (df['fighter_2'] == name)]

    for _, row in fighter_fights.iterrows():
        method = str(row.get("method_main", "")).lower()
        winner = row["fighter_1"]

        if name == winner:
            wins += 1
            if "ko" in method:
                ko += 1
            elif "sub" in method:
                sub += 1
            elif "dec" in method:
                dec += 1
        elif name == row["fighter_1"] or name == row["fighter_2"]:
            losses += 1

    return {
        "UFC Record": f"{wins}-{losses}",
        "Wins by KO": ko,
        "Wins by Submission": sub,
        "Wins by Decision": dec
    }

# Organize stats into ordered lists for frontend
def organize_stats(stats):
    name = stats['name']
    side = stats.get('side', 'fighter_1')  # fallback to 'fighter_1'

    # Try direct 'ig', else fallback to raw column name
    ig_count = stats.get("ig")
    if not ig_count:
        ig_key = f"{side}_ig"
        ig_count = df[df[side] == name][ig_key].values[0] if ig_key in df.columns and not df[df[side] == name].empty else "N/A"

    return {
        "name": name,
        "Bio": {
            "Age": stats.get("current_age"),
	    "Born" : stats.get("born"),
            "Height": stats.get("height"),
            "Reach": stats.get("reach"),
            "Stance": stats.get("stance"),
            "Gym": stats.get("gym"),
            "IG Count": format_count(stats.get("ig"))

        },
        "Record": {
            "Overall Record": f"{stats.get('wins', 0)}-{stats.get('losses', 0)}-{stats.get('draws', 0)}"
        },
        "UFC Record": get_ufc_record(name),
        "Striking": [
            {"label": "Significant Strikes Landed per Minute", "value": stats.get("SLpM")},
            {"label": "Significant Striking Accuracy", "value": stats.get("Str_Acc")},
            {"label": "Significant Strikes Absorbed per Minute", "value": stats.get("SApM")},
            {"label": "Significant Strike Defence", "value": stats.get("Str_Def")}
        ],
        "Grappling": [
            {"label": "Average Takedowns Landed per 15 minutes", "value": stats.get("TD_Avg")},
            {"label": "Takedown Accuracy", "value": stats.get("TD_Acc")},
            {"label": "Takedown Defense", "value": stats.get("TD_Def")},
            {"label": "Average Submissions Attempted per 15 minutes", "value": stats.get("Sub_Avg")}
        ],
        "Last 5 Fights": get_last_5_fights(name)
    }

# API endpoint
@app.route('/get_stats', methods=['POST'])
def get_stats():
    data = request.get_json()
    fighter1 = data.get('fighter1')
    fighter2 = data.get('fighter2')

    stats1 = get_fighter_stats(fighter1, 'fighter_1') or get_fighter_stats(fighter1, 'fighter_2')
    stats2 = get_fighter_stats(fighter2, 'fighter_1') or get_fighter_stats(fighter2, 'fighter_2')

    if not stats1 or not stats2:
        return jsonify({'error': 'One or both fighters not found'}), 404

    return jsonify({
        'fighter1': organize_stats(stats1),
        'fighter2': organize_stats(stats2)
    })

if __name__ == '__main__':
    app.run(debug=True)
