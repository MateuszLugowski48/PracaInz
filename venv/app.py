from flask import Flask, jsonify, render_template, request
import requests
import time
import json
import os
from datetime import datetime
from config import BASE_URL, HEADERS

app = Flask(__name__)

# --- CACHE ---
LIVE_CACHE = {}
TEAM_FORM_CACHE = {}
SEARCH_CACHE = {}
STANDINGS_CACHE = {}
FIXTURES_CACHE = {}

LIVE_CACHE_TIME = 60 
TEAM_FORM_CACHE_TIME = 300 
LONG_CACHE_TIME = 3600 

# --- SŁOWNIK DO WYSZUKIWARKI ---
POLISH_LEAGUE_MAP = {
    "liga mistrzów": "Champions League", "liga mistrzow": "Champions League",
    "liga europy": "Europa League", "liga konferencji": "Conference League",
    "ekstraklasa": "Ekstraklasa", "premier league": "Premier League",
    "la liga": "La Liga", "serie a": "Serie A", "bundesliga": "Bundesliga",
    "ligue 1": "Ligue 1", "puchar polski": "Puchar Polski",
    "mistrzostwa świata": "World Cup", "euro": "Euro Championship"
}

def get_current_season():
    now = datetime.now()
    if now.month >= 8: return now.year
    else: return now.year - 1

# --- ROUTES ---

@app.route('/')
def home(): return render_template('index.html')

@app.route('/standings-page')
def standings_page(): return render_template('standings.html')

@app.route('/form-tracker-page')
def form_tracker_page(): return render_template('form_tracker.html')

@app.route('/head-to-head')
def head_to_head_page(): return render_template('head_to_head.html')

@app.route('/live')
def live_scores():
    now = time.time()
    if 'live' in LIVE_CACHE and now - LIVE_CACHE['live']['time'] < 15: 
        return jsonify(LIVE_CACHE['live']['data'])
    url = f"{BASE_URL}/fixtures?live=all"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    live_list = []
    for match in data.get("response", []):
        live_list.append({
            "home": match["teams"]["home"]["name"],
            "away": match["teams"]["away"]["name"],
            "score": f"{match['goals']['home']} - {match['goals']['away']}",
            "status": match["fixture"]["status"]["long"],
            "minute": match["fixture"].get("minute", None)
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
        for event in match.get("events", []):
            events_list.append({
                "fixture_id": match["fixture"]["id"],
                "home": match["teams"]["home"]["name"],
                "away": match["teams"]["away"]["name"],
                "time": event["time"]["elapsed"],
                "player": event["player"]["name"],
                "type": event["type"],
                "detail": event.get("detail", "")
            })
    return jsonify(events_list)

@app.route('/search-teams')
def search_teams():
    query = request.args.get('q', '')
    if len(query) < 3: return jsonify([])
    cache_key = f"team_{query}"
    if cache_key in SEARCH_CACHE: return jsonify(SEARCH_CACHE[cache_key])
    url = f"{BASE_URL}/teams?search={query}"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    teams = []
    for item in data.get("response", []):
        team = item["team"]
        teams.append({"id": team["id"], "name": team["name"], "logo": team["logo"], "country": team["country"]})
    SEARCH_CACHE[cache_key] = teams
    return jsonify(teams)

@app.route('/search-leagues')
def search_leagues():
    user_query = request.args.get('q', '').lower()
    if len(user_query) < 3: return jsonify([])
    
    api_query = user_query
    for pl_name, en_name in POLISH_LEAGUE_MAP.items():
        if pl_name in user_query:
            api_query = en_name
            break
            
    cache_key = f"league_{api_query}"
    if cache_key in SEARCH_CACHE: return jsonify(SEARCH_CACHE[cache_key])

    url = f"{BASE_URL}/leagues?search={api_query}"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    leagues = []
    for item in data.get("response", []):
        league = item["league"]
        country = item["country"]
        leagues.append({
            "id": league["id"], "name": league["name"],
            "logo": league["logo"], "country": country["name"]
        })
    SEARCH_CACHE[cache_key] = leagues
    return jsonify(leagues)

@app.route('/team-form/<int:team_id>')
def team_form(team_id):
    now = time.time()
    if team_id in TEAM_FORM_CACHE and now - TEAM_FORM_CACHE[team_id]['time'] < TEAM_FORM_CACHE_TIME:
        return jsonify(TEAM_FORM_CACHE[team_id]['data'])

    url_fixtures = f"{BASE_URL}/fixtures?team={team_id}&last=20"
    response_fixtures = requests.get(url_fixtures, headers=HEADERS)
    data_fixtures = response_fixtures.json()

    all_matches = []
    league_matches_for_chart = []
    europe_matches_for_chart = []
    european_keywords = ["Champions League", "Europa League", "Conference League"]
    current_league_id = None

    for match in data_fixtures.get("response", []):
        league_name = match["league"]["name"]
        league_id = match["league"]["id"]
        goals = match["goals"]
        if goals["home"] is None: continue
        
        is_home = match["teams"]["home"]["id"] == team_id
        my_goals = goals["home"] if is_home else goals["away"]
        opp_goals = goals["away"] if is_home else goals["home"]
        if my_goals > opp_goals: points = 3
        elif my_goals == opp_goals: points = 1
        else: points = 0

        dt = datetime.fromisoformat(match["fixture"]["date"].replace('Z', '+00:00'))
        
        match_data = {
            "original_date": match["fixture"]["date"], "date": dt.strftime("%d.%m.%Y"),
            "opponent": match["teams"]["away"]["name"] if is_home else match["teams"]["home"]["name"],
            "logo": match["teams"]["away"]["logo"] if is_home else match["teams"]["home"]["logo"],
            "result_score": f"{goals['home']}:{goals['away']}", "points": points,
            "league_name": league_name, "rank": None
        }
        all_matches.append(match_data)

        if any(k in league_name for k in european_keywords): europe_matches_for_chart.append(match_data)
        elif "Cup" not in league_name and "Friend" not in league_name:
            league_matches_for_chart.append(match_data)
            if current_league_id is None: current_league_id = league_id

    current_rank = 10
    if current_league_id:
        try:
            season = get_current_season()
            res_standings = requests.get(f"{BASE_URL}/standings?league={current_league_id}&season={season}", headers=HEADERS).json()
            standings = res_standings['response'][0]['league']['standings'][0]
            for row in standings:
                if row['team']['id'] == team_id: current_rank = row['rank']; break
        except: pass

    league_chart = league_matches_for_chart[:10][::-1]
    europe_chart = europe_matches_for_chart[:10][::-1]
    simulated_rank = current_rank
    for i in range(len(league_chart) - 1, -1, -1):
        m = league_chart[i]; m['rank'] = simulated_rank
        if m['points'] == 3: simulated_rank = min(20, simulated_rank + 1)
        elif m['points'] == 0: simulated_rank = max(1, simulated_rank - 1)

    table_matches = sorted(all_matches, key=lambda x: x['original_date'], reverse=True)
    response_data = {"league_chart": league_chart, "europe_chart": europe_chart, "table_matches": table_matches}
    TEAM_FORM_CACHE[team_id] = {'time': now, 'data': response_data}
    return jsonify(response_data)

@app.route('/head-to-head/<int:team1_id>/<int:team2_id>')
def head_to_head(team1_id, team2_id):
    url = f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200: return jsonify([])
    matches = []
    data = response.json()
    for match in data.get("response", []):
        if "Friendly" in match["league"]["name"]: continue
        goals = match["goals"]
        if goals["home"] is None: continue
        home_win = goals["home"] > goals["away"]
        away_win = goals["away"] > goals["home"]
        winner = "home" if home_win else ("away" if away_win else "draw")
        dt = datetime.fromisoformat(match["fixture"]["date"].replace('Z', '+00:00'))
        matches.append({
            "original_date": match["fixture"]["date"], "date": dt.strftime("%d.%m.%Y"),
            "home": match["teams"]["home"]["name"], "away": match["teams"]["away"]["name"],
            "score": f"{goals['home']} - {goals['away']}", "league_name": match["league"]["name"], "winner": winner
        })
    matches.sort(key=lambda x: x["original_date"], reverse=True)
    return jsonify(matches)

@app.route('/head-to-head-stats/<int:team1_id>/<int:team2_id>')
def head_to_head_stats(team1_id, team2_id):
    url = f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200: return jsonify({})
    data = response.json()
    t1_wins, t2_wins, draws, t1_goals, t2_goals = 0,0,0,0,0
    count = 0
    for match in data.get("response", []):
        if "Friendly" in match["league"]["name"]: continue
        if match["goals"]["home"] is None: continue
        count += 1
        hg, ag = match["goals"]["home"], match["goals"]["away"]
        if match["teams"]["home"]["id"] == team1_id:
            t1_goals+=hg; t2_goals+=ag
            if hg>ag: t1_wins+=1
            elif hg<ag: t2_wins+=1
            else: draws+=1
        else:
            t2_goals+=hg; t1_goals+=ag
            if hg>ag: t2_wins+=1
            elif hg<ag: t1_wins+=1
            else: draws+=1
    return jsonify({"total_matches": count, "team1_wins": t1_wins, "team2_wins": t2_wins, "draws": draws, "team1_avg_goals": round(t1_goals/count, 2) if count else 0, "team2_avg_goals": round(t2_goals/count, 2) if count else 0, "total_goals": t1_goals+t2_goals})

@app.route('/standings/<int:league_id>')
def get_standings(league_id):
    season = request.args.get('season', default=get_current_season(), type=int)
    cache_key = f"{league_id}_{season}"
    now = time.time()
    if cache_key in STANDINGS_CACHE and now - STANDINGS_CACHE[cache_key]['time'] < LONG_CACHE_TIME:
        return jsonify(STANDINGS_CACHE[cache_key]['data'])
    
    url = f"{BASE_URL}/standings?league={league_id}&season={season}"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    formatted_standings = []
    try:
        standings_groups = data["response"][0]["league"]["standings"]
        for group in standings_groups:
            group_data = []
            for row in group:
                group_data.append({
                    "rank": row["rank"], "team": row["team"]["name"], "logo": row["team"]["logo"],
                    "points": row["points"], "goalsDiff": row["goalsDiff"], "form": row["form"],
                    "played": row["all"]["played"], "win": row["all"]["win"], "draw": row["all"]["draw"],
                    "lose": row["all"]["lose"], "description": row.get("description"), "group_name": row.get("group")
                })
            formatted_standings.append(group_data)
    except: pass
    STANDINGS_CACHE[cache_key] = {'time': now, 'data': formatted_standings}
    return jsonify(formatted_standings)

@app.route('/fixtures-by-league/<int:league_id>')
def get_fixtures_by_league(league_id):
    season = request.args.get('season', default=get_current_season(), type=int)
    cache_key = f"fixtures_{league_id}_{season}"
    now = time.time()
    if cache_key in FIXTURES_CACHE and now - FIXTURES_CACHE[cache_key]['time'] < LONG_CACHE_TIME:
        return jsonify(FIXTURES_CACHE[cache_key]['data'])
    
    url = f"{BASE_URL}/fixtures?league={league_id}&season={season}"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    matches = []
    for match in data.get("response", []):
        goals = match["goals"]
        score = match["score"]
        penalty = score.get("penalty", {})
        dt = datetime.fromisoformat(match["fixture"]["date"].replace('Z', '+00:00'))
        matches.append({
            "date": dt.strftime("%d.%m.%Y"), "timestamp": match["fixture"]["timestamp"],
            "round": match["league"]["round"],
            "home": match["teams"]["home"]["name"], "home_id": match["teams"]["home"]["id"],
            "home_logo": match["teams"]["home"]["logo"], "home_winner": match["teams"]["home"].get("winner"),
            "away": match["teams"]["away"]["name"], "away_id": match["teams"]["away"]["id"],
            "away_logo": match["teams"]["away"]["logo"], "away_winner": match["teams"]["away"].get("winner"),
            "score": f"{goals['home']} - {goals['away']}" if goals['home'] is not None else "-:-",
            "penalty": f"{penalty.get('home')}-{penalty.get('away')}" if penalty.get('home') is not None else None,
            "status": match["fixture"]["status"]["short"]
        })
    matches.sort(key=lambda x: x["timestamp"], reverse=True)
    FIXTURES_CACHE[cache_key] = {'time': now, 'data': matches}
    return jsonify(matches)

if __name__ == "__main__":
    app.run(debug=True)