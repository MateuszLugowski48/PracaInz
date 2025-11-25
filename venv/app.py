from flask import Flask, jsonify, render_template
import requests
import time
import json
import os
from datetime import datetime
from config import BASE_URL, HEADERS, LEAGUES

app = Flask(__name__)

# --- CACHE ---
LIVE_CACHE = {}
TEAM_FORM_CACHE = {}
LIVE_CACHE_TIME = 60  # sekundy
TEAM_FORM_CACHE_TIME = 300  # 5 minut

LEAGUES_FILE = "data/leagues.json"

# Wybrane ligi
WANTED_LEAGUES = ["Premier League", "Bundesliga", "Serie A", "La Liga", "Ekstraklasa"]

# --- FUNKCJE ---

def fetch_leagues():
    """Pobiera wybrane ligi z API lub cache"""

    if os.path.exists(LEAGUES_FILE):
        try:
            with open(LEAGUES_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    last_update = data.get("timestamp", 0)
                    if time.time() - last_update < 86400:
                        return data["leagues"]
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Pobieranie z API
    url = f"{BASE_URL}/leagues"
    response = requests.get(url, headers=HEADERS)
    result = response.json()

    leagues_list = []

    for item in result.get("response", []):
        name = item["league"]["name"]
        country = item["country"]["name"]
        league_id = item["league"]["id"]

        # --- FILTROWANIE PREMIER LEAGUE ---
        if name == "Premier League" and country != "England":
            continue  # pomijamy wszystkie nieangielskie Premier League

        # --- NORMALNE FILTROWANIE DLA RESZTY ---
        if name in WANTED_LEAGUES:
            leagues_list.append({"id": league_id, "name": name, "country": country})

    # Zapisz do pliku
    with open(LEAGUES_FILE, "w", encoding="utf-8") as f:
        json.dump({"timestamp": time.time(), "leagues": leagues_list}, f, ensure_ascii=False)

    return leagues_list


@app.route('/')
def home():
    leagues = fetch_leagues()
    return render_template('index.html', leagues=leagues)


# -----------------------
#     POPRAWIONY ENDPOINT
# -----------------------
@app.route('/leagues')
def leagues():
    data = fetch_leagues()
    return jsonify(data)


@app.route('/live')
def live_scores():
    now = time.time()
    if 'live' in LIVE_CACHE and now - LIVE_CACHE['live']['time'] < LIVE_CACHE_TIME:
        return jsonify(LIVE_CACHE['live']['data'])
    
    url = f"{BASE_URL}/fixtures?live=all"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    
    live_list = []
    for match in data.get("response", []):
        fixture = match["fixture"]
        teams = match["teams"]
        goals = match["goals"]
        live_list.append({
            "home": teams["home"]["name"],
            "away": teams["away"]["name"],
            "score": f"{goals['home']} - {goals['away']}",
            "status": fixture["status"]["long"],
            "minute": fixture.get("minute", None)
        })
    
    LIVE_CACHE['live'] = {'time': now, 'data': live_list}
    return jsonify(live_list)


@app.route('/live-events')
def live_events():
    url = f"{BASE_URL}/fixtures?live=all"
    response = requests.get(url, headers=HEADERS)
    data = response.json()

    events_list = []
    for match in data.get("response", []):
        fixture = match["fixture"]
        teams = match["teams"]
        events = match.get("events", [])

        for event in events:
            events_list.append({
                "fixture_id": fixture["id"],
                "home": teams["home"]["name"],
                "away": teams["away"]["name"],
                "time": event["time"]["elapsed"],
                "team": event["team"]["name"],
                "player": event["player"]["name"],
                "type": event["type"],
                "detail": event.get("detail", "")
            })

    return jsonify(events_list)


@app.route('/team-form/<int:team_id>')
def team_form(team_id):
    now = time.time()
    if team_id in TEAM_FORM_CACHE and now - TEAM_FORM_CACHE[team_id]['time'] < TEAM_FORM_CACHE_TIME:
        return jsonify(TEAM_FORM_CACHE[team_id]['data'])

    url = f"{BASE_URL}/fixtures?team={team_id}&last=5"
    response = requests.get(url, headers=HEADERS)
    data = response.json()

    results = []
    for match in data.get("response", []):
        goals = match["goals"]
        home_goals = goals["home"]
        away_goals = goals["away"]
        is_home = match["teams"]["home"]["id"] == team_id

        if is_home:
            if home_goals > away_goals:
                points = 3
            elif home_goals == away_goals:
                points = 1
            else:
                points = 0
        else:
            if away_goals > home_goals:
                points = 3
            elif away_goals == away_goals:
                points = 1
            else:
                points = 0

        results.append({
            "date": match["fixture"]["date"],
            "opponent": match["teams"]["away"]["name"] if is_home else match["teams"]["home"]["name"],
            "result": f"{home_goals}:{away_goals}",
            "points": points
        })

    TEAM_FORM_CACHE[team_id] = {'time': now, 'data': results}
    return jsonify(results)


@app.route('/head-to-head')
def head_to_head_page():
    return render_template('head_to_head.html')


@app.route('/head-to-head/<int:team1_id>/<int:team2_id>')
def head_to_head(team1_id, team2_id):
    print(f"Fetching H2H for {team1_id} vs {team2_id}")

    url = f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"API returned status code: {response.status_code}")
        return jsonify([])

    try:
        data = response.json()
    except json.JSONDecodeError:
        print("API returned empty or invalid JSON")
        return jsonify([])

    print("Raw API response:", data)

    matches = []
    for match in data.get("response", []):
        home_team_id = match["teams"]["home"]["id"]
        away_team_id = match["teams"]["away"]["id"]

        # Sprawdź, czy obie drużyny grały w meczu
        if (home_team_id == team1_id and away_team_id == team2_id) or \
           (home_team_id == team2_id and away_team_id == team1_id):

            # --- FILTROWANIE: Tylko oficjalne mecze ---
            league_id = match["league"]["id"]
            league_name = match["league"]["name"]

            # Ignoruj mecze towarzyskie (np. Friendlies Clubs)
            if "Friendly" in league_name or "Friendlies" in league_name:
                continue

            goals = match["goals"]
            home_goals = goals.get("home")
            away_goals = goals.get("away")

            # Oryginalna data (do sortowania)
            original_date = match["fixture"]["date"]

            # Format daty do wyświetlenia: DD-MM-RRRR
            try:
                dt = datetime.fromisoformat(original_date.replace('Z', '+00:00'))
                formatted_date = dt.strftime("%d-%m-%Y")
            except ValueError:
                formatted_date = original_date  # jeśli format nie pasuje

            # Sprawdź, czy wynik istnieje
            if home_goals is None or away_goals is None:
                score = "Mecz dopiero się odbędzie"
                winner = None  # brak zwycięzcy
            else:
                score = f"{home_goals} - {away_goals}"
                # Znajdź zwycięzcę
                if home_goals > away_goals:
                    winner = "home"
                elif away_goals > home_goals:
                    winner = "away"
                else:
                    winner = "draw"  # remis

            # Zmień "Cup" na "Puchar krajowy"
            if "Cup" in league_name:
                league_display = "Puchar krajowy"
            else:
                league_display = league_name

            matches.append({
                "original_date": original_date,  # do sortowania
                "date": formatted_date,         # do wyświetlenia
                "home": match["teams"]["home"]["name"],
                "away": match["teams"]["away"]["name"],
                "score": score,
                "league_name": league_display,  # nazwa ligi do wyświetlenia
                "winner": winner                # kto wygrał
            })

    # Sortuj mecze od najnowszego do najdawniejszego (po oryginalnej dacie)
    matches.sort(key=lambda x: x["original_date"], reverse=True)

    # Usuń pole 'original_date' przed zwróceniem
    for match in matches:
        del match["original_date"]

    print("Filtered and sorted matches:", matches)
    return jsonify(matches)


@app.route('/head-to-head-stats/<int:team1_id>/<int:team2_id>')
def head_to_head_stats(team1_id, team2_id):
    print(f"Fetching H2H stats for {team1_id} vs {team2_id}")

    # Pobierz dane z head_to_head (bez sortowania)
    url = f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        return jsonify({})

    try:
        data = response.json()
    except json.JSONDecodeError:
        return jsonify({})

    matches = []
    for match in data.get("response", []):
        home_team_id = match["teams"]["home"]["id"]
        away_team_id = match["teams"]["away"]["id"]

        # Sprawdź, czy obie drużyny grały w meczu
        if (home_team_id == team1_id and away_team_id == team2_id) or \
           (home_team_id == team2_id and away_team_id == team1_id):

            # Filtruj tylko oficjalne mecze
            league_name = match["league"]["name"]
            if "Friendly" in league_name or "Friendlies" in league_name:
                continue

            goals = match["goals"]
            home_goals = goals.get("home")
            away_goals = goals.get("away")

            if home_goals is None or away_goals is None:
                continue  # pomijaj mecze bez wyniku

            matches.append({
                "home_goals": home_goals,
                "away_goals": away_goals,
                "home_id": home_team_id,
                "away_id": away_team_id
            })

    # --- Analiza danych ---
    team1_wins = 0
    team2_wins = 0
    draws = 0
    team1_goals = 0
    team2_goals = 0

    for match in matches:
        if match["home_id"] == team1_id:
            if match["home_goals"] > match["away_goals"]:
                team1_wins += 1
            elif match["home_goals"] < match["away_goals"]:
                team2_wins += 1
            else:
                draws += 1

            team1_goals += match["home_goals"]
            team2_goals += match["away_goals"]

        elif match["home_id"] == team2_id:
            if match["home_goals"] > match["away_goals"]:
                team2_wins += 1
            elif match["home_goals"] < match["away_goals"]:
                team1_wins += 1
            else:
                draws += 1

            team2_goals += match["home_goals"]
            team1_goals += match["away_goals"]

    total_matches = len(matches)

    stats = {
        "total_matches": total_matches,
        "team1_wins": team1_wins,
        "team2_wins": team2_wins,
        "draws": draws,
        "team1_avg_goals": round(team1_goals / total_matches, 2) if total_matches > 0 else 0,
        "team2_avg_goals": round(team2_goals / total_matches, 2) if total_matches > 0 else 0,
        "total_goals": team1_goals + team2_goals
    }

    return jsonify(stats)


@app.route('/head-to-head-extended')
def head_to_head_extended_page():
    return render_template('head_to_head_extended.html')


# ---------------------------------------
#   POPRAWIONY ENDPOINT — KLUCZOWA ZMIANA
# ---------------------------------------
@app.route('/teams/<int:league_id>')
def get_teams(league_id):
    url = f"{BASE_URL}/teams?league={league_id}&season=2025"
    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        return jsonify([])

    try:
        data = response.json()
    except json.JSONDecodeError:
        return jsonify([])

    teams = []
    for item in data.get("response", []):
        team = item["team"]
        teams.append({"id": team["id"], "name": team["name"]})

    return jsonify(teams)


if __name__ == "__main__":
    app.run(debug=True)