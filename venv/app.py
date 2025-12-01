from flask import Flask, jsonify, render_template, request
import requests
import time
import json
import os
from datetime import datetime
from config import BASE_URL, HEADERS
import math

app = Flask(__name__)

# --- CACHE ---
LIVE_CACHE = {}
TEAM_FORM_CACHE = {}
SEARCH_CACHE = {}
STANDINGS_CACHE = {}
FIXTURES_CACHE = {}
MATCH_CACHE = {}
TEAM_PROFILE_CACHE = {}
PLAYER_CACHE = {}
SCORERS_CACHE = {}
REFEREE_CACHE = {}
REFEREE_LIST_CACHE = {}
ODDS_CACHE = {}
PREDICTIONS_CACHE = {}

LIVE_CACHE_TIME = 60 
TEAM_FORM_CACHE_TIME = 300 
LONG_CACHE_TIME = 3600 

# --- SŁOWNIK TŁUMACZEŃ DLA WYSZUKIWARKI LIG ---
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

# --- DYNAMICZNE WCZYTYWANIE ID LIG Z PLIKU JSON ---
def get_search_league_ids():
    """
    Pobiera listę ID lig z pliku data/leagues.json.
    Dzięki temu lista lig do przeszukania nie jest wpisana na sztywno w kodzie.
    """
    try:
        # Ścieżka do pliku w folderze data obok app.py
        json_path = os.path.join(os.path.dirname(__file__), 'data', 'leagues.json')
        
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                data = json.load(f)
                # Zwracamy listę samych ID
                return [l['id'] for l in data.get('leagues', [])]
    except Exception as e:
        print(f"Błąd odczytu leagues.json: {e}")
    
    # Zapasowe ID (gdyby plik json nie istniał) - Top 5 + Ekstraklasa
    return [2, 39, 140, 78, 135, 61, 106]

# --- ROUTES ---

@app.route('/')
def home(): return render_template('index.html')

@app.route('/standings-page')
def standings_page(): return render_template('standings.html')

@app.route('/form-tracker-page')
def form_tracker_page(): return render_template('form_tracker.html')

@app.route('/head-to-head')
def head_to_head_page(): return render_template('head_to_head.html')

@app.route('/team-search')
def team_search_page(): return render_template('team_search.html')

@app.route('/player-search')
def player_search_page(): return render_template('player_search.html')

@app.route('/player-h2h')
def player_h2h_page(): return render_template('player_h2h.html')

@app.route('/referee-search')
def referee_search_page(): return render_template('referee_search.html')

@app.route('/stats-center')
def stats_center_page(): return render_template('stats_center.html')

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
            "id": match["fixture"]["id"],
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

# --- WYSZUKIWANIE PIŁKARZY ---
@app.route('/search-players')
def search_players():
    query = request.args.get('q', '')
    if len(query) < 3: return jsonify([])
    
    cache_key = f"player_search_{query}"
    if cache_key in SEARCH_CACHE: return jsonify(SEARCH_CACHE[cache_key])

    season = get_current_season()
    players_map = {} 

    # 1. Pobierz dynamicznie listę ID lig z pliku JSON
    league_ids = get_search_league_ids()

    # 2. Pętla po ligach (bo API wymaga parametru 'league')
    for league_id in league_ids:
        try:
            url = f"{BASE_URL}/players?search={query}&season={season}&league={league_id}"
            response = requests.get(url, headers=HEADERS)
            data = response.json()
            
            for item in data.get("response", []):
                p = item["player"]
                # Unikamy duplikatów (ten sam gracz w lidze i LM)
                if p["id"] not in players_map:
                    stats = item["statistics"][0] if item["statistics"] else {}
                    team_name = stats.get("team", {}).get("name", "Brak klubu")
                    
                    players_map[p["id"]] = {
                        "id": p["id"],
                        "name": p["name"],
                        "photo": p["photo"],
                        "age": p["age"],
                        "nationality": p["nationality"],
                        "team": team_name
                    }
            
            # Optymalizacja: Jeśli mamy już 5 wyników, nie odpytuj kolejnych lig
            if len(players_map) >= 5:
                break
        except:
            continue
    
    result_list = list(players_map.values())
    SEARCH_CACHE[cache_key] = result_list
    return jsonify(result_list)

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
            "id": match["fixture"]["id"],
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
            "id": match["fixture"]["id"],
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
                    "rank": row["rank"], 
                    "team": row["team"]["name"], 
                    "team_id": row["team"]["id"],
                    "logo": row["team"]["logo"],
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
            "id": match["fixture"]["id"],
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


@app.route('/match/<int:fixture_id>')
def match_page(fixture_id):
    return render_template('match_stats.html', fixture_id=fixture_id)

@app.route('/api/match-details/<int:fixture_id>')
def get_match_details(fixture_id):
    now = time.time()
    if fixture_id in MATCH_CACHE:
        cached = MATCH_CACHE[fixture_id]
        is_live = cached['data']['fixture']['status']['short'] in ['1H', 'HT', '2H', 'ET', 'P']
        validity = 15 if is_live else 300
        if now - cached['time'] < validity:
            return jsonify(cached['data'])

    url = f"{BASE_URL}/fixtures?id={fixture_id}"
    response = requests.get(url, headers=HEADERS)
    data = response.json()
    
    if data.get("response"):
        result = data["response"][0]
        MATCH_CACHE[fixture_id] = {'time': now, 'data': result}
        return jsonify(result)
    return jsonify({})

# --- TEAM PROFILE ROUTES ---

@app.route('/team/<int:team_id>')
def team_profile(team_id):
    return render_template('team_profile.html', team_id=team_id)

@app.route('/api/team-profile-data/<int:team_id>')
def get_team_profile_data(team_id):
    now = time.time()
    # Cache na 1 godzinę
    if team_id in TEAM_PROFILE_CACHE and now - TEAM_PROFILE_CACHE[team_id]['time'] < 3600:
        return jsonify(TEAM_PROFILE_CACHE[team_id]['data'])

    try:
        headers = HEADERS
        season = get_current_season()
        
        res_info = requests.get(f"{BASE_URL}/teams?id={team_id}", headers=headers).json()
        team_info = res_info['response'][0]['team'] if res_info.get('response') else {}
        venue_info = res_info['response'][0]['venue'] if res_info.get('response') else {}

        res_last = requests.get(f"{BASE_URL}/fixtures?team={team_id}&last=10&season={season}", headers=headers).json()
        last_matches_raw = res_last.get('response', [])
        
        res_next = requests.get(f"{BASE_URL}/fixtures?team={team_id}&next=10&season={season}", headers=headers).json()

        coach = {}
        coach_found = False

        if last_matches_raw:
            matches_to_check = last_matches_raw[:3]
            for match_item in matches_to_check:
                if coach_found: break
                fixture_id = match_item['fixture']['id']
                try:
                    res_details = requests.get(f"{BASE_URL}/fixtures?id={fixture_id}", headers=headers).json()
                    if res_details.get('response'):
                        lineups = res_details['response'][0].get('lineups', [])
                        for lineup in lineups:
                            if lineup['team']['id'] == team_id and lineup.get('coach') and lineup['coach'].get('name'):
                                c_data = lineup['coach']
                                coach = {
                                    "id": c_data.get('id'), "name": c_data.get('name'),
                                    "firstname": c_data.get('name'), "lastname": "", "photo": c_data.get('photo')
                                }
                                coach_found = True
                                break
                except Exception as e: print(f"Błąd pobierania trenera: {e}")

        if not coach_found:
            res_coach = requests.get(f"{BASE_URL}/coachs?team={team_id}", headers=headers).json()
            if res_coach.get('response'): coach = res_coach['response'][0]

        res_squad = requests.get(f"{BASE_URL}/players/squads?team={team_id}", headers=headers).json()
        squad = res_squad['response'][0]['players'] if res_squad.get('response') else []

        def format_matches(match_list):
            formatted = []
            for m in match_list:
                dt = datetime.fromisoformat(m["fixture"]["date"].replace('Z', '+00:00'))
                goals = m['goals']
                score = f"{goals['home']}-{goals['away']}" if goals['home'] is not None else "-:-"
                formatted.append({
                    "id": m["fixture"]["id"], "date": dt.strftime("%d.%m.%Y"), "time": dt.strftime("%H:%M"),
                    "league": m["league"]["name"], "home": m["teams"]["home"]["name"],
                    "home_logo": m["teams"]["home"]["logo"], "away": m["teams"]["away"]["name"],
                    "away_logo": m["teams"]["away"]["logo"], "score": score,
                    "is_finished": m["fixture"]["status"]["short"] in ['FT', 'AET', 'PEN']
                })
            return formatted

        data = {
            "info": team_info, "venue": venue_info, "coach": coach, "squad": squad,
            "last_matches": format_matches(last_matches_raw),
            "next_matches": format_matches(res_next.get('response', []))
        }
        TEAM_PROFILE_CACHE[team_id] = {'time': now, 'data': data}
        return jsonify(data)
    except Exception as e:
        print(f"Error fetching team data: {e}")
        return jsonify({})

# --- PLAYER PROFILE ROUTES ---

@app.route('/player/<int:player_id>')
def player_profile(player_id):
    return render_template('player_profile.html', player_id=player_id)

@app.route('/api/player-data/<int:player_id>')
def get_player_data(player_id):
    # Pobieramy sezon z parametrów URL (?season=2022), domyślnie bieżący
    requested_season = request.args.get('season', default=get_current_season(), type=int)
    
    now = time.time()
    # Klucz cache musi teraz zawierać ID gracza ORAZ sezon
    cache_key = f"{player_id}_{requested_season}"
    
    if cache_key in PLAYER_CACHE and now - PLAYER_CACHE[cache_key]['time'] < 3600:
        return jsonify(PLAYER_CACHE[cache_key]['data'])

    try:
        headers = HEADERS
        # Używamy wybranego sezonu w zapytaniu do API
        url_stats = f"{BASE_URL}/players?id={player_id}&season={requested_season}"
        res_stats = requests.get(url_stats, headers=headers).json()
        
        player_info = {}
        statistics = []
        
        if res_stats.get('response'):
            data = res_stats['response'][0]
            player_info = data['player']
            statistics = data['statistics']

        # Transfery są niezależne od sezonu (zawsze pobieramy całą historię)
        url_transfers = f"{BASE_URL}/transfers?player={player_id}"
        res_transfers = requests.get(url_transfers, headers=headers).json()
        transfers = res_transfers['response'][0]['transfers'] if res_transfers.get('response') else []

        result = {
            "player": player_info,
            "statistics": statistics,
            "transfers": transfers,
            "season": requested_season # Zwracamy też info, jaki to był sezon
        }

        PLAYER_CACHE[cache_key] = {'time': now, 'data': result}
        return jsonify(result)

    except Exception as e:
        print(f"Error fetching player data: {e}")
        return jsonify({})
    
# --- TOP SCORERS ROUTE ---

@app.route('/api/top-scorers/<int:league_id>')
def get_top_scorers(league_id):
    season = request.args.get('season', default=get_current_season(), type=int)
    cache_key = f"{league_id}_{season}"
    now = time.time()
    if cache_key in SCORERS_CACHE and now - SCORERS_CACHE[cache_key]['time'] < 3600:
        return jsonify(SCORERS_CACHE[cache_key]['data'])

    try:
        res = requests.get(f"{BASE_URL}/players/topscorers?league={league_id}&season={season}", headers=HEADERS).json()
        scorers = []
        for item in res.get("response", [])[:10]:
            p, s = item['player'], item['statistics'][0]
            scorers.append({
                "rank": len(scorers) + 1, 
                "id": p['id'], 
                "name": p['name'], 
                "photo": p['photo'],
                "team": s['team']['name'], 
                "team_logo": s['team']['logo'],
                
                # --- POPRAWKA: Dodajemy pole 'value' ---
                "value": s['goals']['total'] or 0,  # To pole jest wymagane przez stats_center.html
                
                "goals": s['goals']['total'] or 0,
                "assists": s['goals']['assists'] or 0, 
                "matches": s['games']['appearences'] or 0
            })
        SCORERS_CACHE[cache_key] = {'time': now, 'data': scorers}
        return jsonify(scorers)
    except Exception as e:
        print(f"Błąd scorers: {e}")
        return jsonify([])
    

@app.route('/api/top-assists/<int:league_id>')
def get_top_assists(league_id):
    season = request.args.get('season', default=get_current_season(), type=int)
    cache_key = f"assists_{league_id}_{season}"
    now = time.time()
    
    if cache_key in SCORERS_CACHE and now - SCORERS_CACHE[cache_key]['time'] < 3600:
        return jsonify(SCORERS_CACHE[cache_key]['data'])

    try:
        url = f"{BASE_URL}/players/topassists?league={league_id}&season={season}"
        response = requests.get(url, headers=HEADERS)
        data = response.json()
        
        players = []
        for item in data.get("response", [])[:10]:
            p, s = item['player'], item['statistics'][0]
            players.append({
                "rank": len(players) + 1, "id": p['id'], "name": p['name'], "photo": p['photo'],
                "team": s['team']['name'], "team_logo": s['team']['logo'],
                "value": s['goals']['assists'] or 0, # Kluczowa wartość
                "matches": s['games']['appearences'] or 0
            })
            
        SCORERS_CACHE[cache_key] = {'time': now, 'data': players}
        return jsonify(players)
    except: return jsonify([])

@app.route('/api/top-cards/<int:league_id>')
def get_top_cards(league_id):
    # API-Sports ma endpointy 'topyellowcards' i 'topredcards'. 
    # Dla uproszczenia pobierzemy żółte, bo jest ich więcej i ranking jest ciekawszy.
    season = request.args.get('season', default=get_current_season(), type=int)
    cache_key = f"cards_{league_id}_{season}"
    now = time.time()
    
    if cache_key in SCORERS_CACHE and now - SCORERS_CACHE[cache_key]['time'] < 3600:
        return jsonify(SCORERS_CACHE[cache_key]['data'])

    try:
        url = f"{BASE_URL}/players/topyellowcards?league={league_id}&season={season}"
        response = requests.get(url, headers=HEADERS)
        data = response.json()
        
        players = []
        for item in data.get("response", [])[:10]:
            p, s = item['player'], item['statistics'][0]
            players.append({
                "rank": len(players) + 1, "id": p['id'], "name": p['name'], "photo": p['photo'],
                "team": s['team']['name'], "team_logo": s['team']['logo'],
                "value": (s['cards']['yellow'] or 0) + (s['cards']['red'] or 0), # Suma kartek
                "yellow": s['cards']['yellow'] or 0,
                "red": s['cards']['red'] or 0,
                "matches": s['games']['appearences'] or 0
            })
            
        SCORERS_CACHE[cache_key] = {'time': now, 'data': players}
        return jsonify(players)
    except: return jsonify([])

@app.route('/api/referees-list')
def get_referees_list():
    # Sprawdzamy cache (ważny 24h - 86400 sekund, bo lista sędziów rzadko się zmienia)
    now = time.time()
    if 'list' in REFEREE_LIST_CACHE and now - REFEREE_LIST_CACHE['list']['time'] < 86400:
        return jsonify(REFEREE_LIST_CACHE['list']['data'])

    season = get_current_season()
    league_ids = get_search_league_ids()
    unique_referees = set()

    # Przeszukujemy ligi, aby zebrać unikalne nazwiska
    # To może chwilę potrwać przy pierwszym uruchomieniu, ale potem leci z cache
    for league_id in league_ids:
        try:
            # Sprawdzamy czy mamy dane ligi w innym cache, żeby nie pytać API niepotrzebnie
            cache_key = f"raw_fixtures_{league_id}_{season}"
            matches = []
            
            if cache_key in SEARCH_CACHE:
                matches = SEARCH_CACHE[cache_key]['data']
            else:
                # Jeśli nie ma w cache, szybkie zapytanie o ligę
                url = f"{BASE_URL}/fixtures"
                params = {"league": league_id, "season": season}
                resp = requests.get(url, headers=HEADERS, params=params)
                if resp.status_code == 200:
                    matches = resp.json().get("response", [])
                    # Przy okazji zapiszmy to do SEARCH_CACHE dla innych funkcji
                    SEARCH_CACHE[cache_key] = {'time': now, 'data': matches}

            # Wyciąganie nazwisk
            for m in matches:
                ref = m["fixture"].get("referee")
                if ref:
                    # Usuwamy ewentualne kropki i zbędne spacje, np. "S. Marciniak" -> "Szymon Marciniak" (API różnie zwraca)
                    # Tutaj bierzemy surową nazwę, bo jest najpewniejsza do wyszukiwania
                    unique_referees.add(ref)

        except Exception as e:
            print(f"Błąd pobierania listy sędziów dla ligi {league_id}: {e}")

    # Sortujemy alfabetycznie
    sorted_refs = sorted(list(unique_referees))
    
    # Zapisujemy do cache
    REFEREE_LIST_CACHE['list'] = {'time': now, 'data': sorted_refs}
    
    return jsonify(sorted_refs)


@app.route('/api/referee-stats')
def get_referee_stats():
    ref_name = request.args.get('name', '').strip().lower()
    if len(ref_name) < 3:
        return jsonify({"error": "Wpisz co najmniej 3 znaki"}), 400

    # Klucz cache z dopiskiem 'premium', zeby nie brał starych danych bez kartek
    cache_key = f"ref_premium_{ref_name.replace(' ', '_')}"
    now = time.time()

    if cache_key in REFEREE_CACHE and now - REFEREE_CACHE[cache_key]['time'] < 3600:
        return jsonify(REFEREE_CACHE[cache_key]['data'])

    season = get_current_season()
    league_ids = get_search_league_ids()
    
    print(f"DEBUG: Szukam sędziego '{ref_name}' (Premium Mode)...")

    all_matches_found = []
    leagues_scanned = 0

    # 1. ETAP WSTĘPNY: Skanowanie lig w poszukiwaniu meczów sędziego
    for league_id in league_ids:
        internal_cache_key = f"raw_fixtures_{league_id}_{season}"
        
        # Pobieranie listy meczów danej ligi
        if internal_cache_key in SEARCH_CACHE and now - SEARCH_CACHE[internal_cache_key]['time'] < 3600:
            data_response = SEARCH_CACHE[internal_cache_key]['data']
        else:
            try:
                url = f"{BASE_URL}/fixtures"
                params = {"league": league_id, "season": season}
                resp = requests.get(url, headers=HEADERS, params=params)
                if resp.status_code != 200: continue
                data_response = resp.json().get("response", [])
                SEARCH_CACHE[internal_cache_key] = {'time': now, 'data': data_response}
            except: continue

        # Filtrowanie po nazwisku sędziego
        for match in data_response:
            match_referee = match["fixture"].get("referee")
            if match_referee and ref_name in match_referee.lower():
                all_matches_found.append(match)
        
        leagues_scanned += 1

    if not all_matches_found:
        return jsonify({"error": "Nie znaleziono sędziego w tych ligach."}), 404

    # 2. ETAP PREMIUM: Pobieranie detali (kartek) dla każdego meczu
    # Sortujemy od najnowszych, bierzemy max 30 ostatnich meczów, żeby nie zamulić nawet na premium
    all_matches_found.sort(key=lambda x: x["fixture"]["date"], reverse=True)
    matches_to_analyze = all_matches_found[:30] 

    stats = {
        "name": matches_to_analyze[0]["fixture"]["referee"],
        "matches_count": len(matches_to_analyze),
        "total_goals": 0,
        "total_yellow": 0,
        "total_red": 0,
        "total_penalties": 0,
        "leagues": list(set(m["league"]["name"] for m in matches_to_analyze)),
        "recent_matches": []
    }

    print(f"DEBUG: Analizuję detale {len(matches_to_analyze)} meczów...")

    for match in matches_to_analyze:
        fixture_id = match["fixture"]["id"]
        
        # Sprawdzamy czy mamy detale w cache meczowym
        events = []
        if fixture_id in MATCH_CACHE:
            events = MATCH_CACHE[fixture_id]['data'].get('events', [])
        else:
            # Jeśli nie, robimy REQUEST PREMIUM o szczegóły
            try:
                time.sleep(0.1) # Lekkie opóźnienie dla bezpieczeństwa (10 req/s)
                res_det = requests.get(f"{BASE_URL}/fixtures?id={fixture_id}", headers=HEADERS)
                det_data = res_det.json()
                if det_data.get('response'):
                    full_match_data = det_data['response'][0]
                    MATCH_CACHE[fixture_id] = {'time': now, 'data': full_match_data}
                    events = full_match_data.get('events', [])
            except Exception as e:
                print(f"Błąd detali meczu {fixture_id}: {e}")

        # Analiza zdarzeń w meczu
        yellows = 0
        reds = 0
        match_goals = (match["goals"]["home"] or 0) + (match["goals"]["away"] or 0)
        stats["total_goals"] += match_goals

        for event in events:
            e_type = event.get('type')
            e_detail = event.get('detail')

            if e_type == 'Card':
                if e_detail == 'Yellow Card': 
                    stats["total_yellow"] += 1
                    yellows += 1
                elif e_detail == 'Red Card': 
                    stats["total_red"] += 1
                    reds += 1
            
            # Karny: Zazwyczaj to typ 'Goal' z detalem 'Penalty' lub 'Missed Penalty'
            if e_detail == 'Penalty' or e_detail == 'Missed Penalty':
                stats["total_penalties"] += 1

        # Formatowanie do tabeli
        dt = datetime.fromisoformat(match["fixture"]["date"].replace('Z', '+00:00'))
        stats["recent_matches"].append({
            "id": match["fixture"]["id"],  # <--- DODAJ TĘ LINIJKĘ (ID Meczu)
            "date": dt.strftime("%d.%m.%Y"),
            "home": match["teams"]["home"]["name"],
            "away": match["teams"]["away"]["name"],
            "score": f"{match['goals']['home']}-{match['goals']['away']}",
            "cards_info": f"{yellows}🟨 {reds}🟥" if (yellows+reds)>0 else "Brak",
            "league": match["league"]["name"]
        })

    # Średnie
    mc = stats["matches_count"]
    if mc > 0:
        stats["avg_goals"] = round(stats["total_goals"] / mc, 2)
        stats["avg_yellow"] = round(stats["total_yellow"] / mc, 2)
        stats["avg_red"] = round(stats["total_red"] / mc, 2)
    else:
        stats["avg_goals"] = 0; stats["avg_yellow"] = 0; stats["avg_red"] = 0

    REFEREE_CACHE[cache_key] = {'time': now, 'data': stats}
    return jsonify(stats)

@app.route('/api/match-odds/<int:fixture_id>')
def get_match_odds(fixture_id):
    # Cache na 30 minut (kursy nie zmieniają się aż tak gwałtownie przed meczem, 
    # a oszczędzamy zapytania)
    now = time.time()
    if fixture_id in ODDS_CACHE and now - ODDS_CACHE[fixture_id]['time'] < 1800:
        return jsonify(ODDS_CACHE[fixture_id]['data'])

    try:
        # Pobieramy kursy dla konkretnego meczu
        url = f"{BASE_URL}/odds?fixture={fixture_id}"
        response = requests.get(url, headers=HEADERS)
        data = response.json()

        if not data.get("response"):
            return jsonify({"error": "Brak kursów dla tego meczu."}), 404

        # Bierzemy pierwszego lepszego bukmachera (zazwyczaj Bet365 jest pierwszy i najbardziej stabilny)
        odds_data = data["response"][0]
        bookmakers = odds_data.get("bookmakers", [])
        
        selected_bookie = None
        # Szukamy Bet365, jeśli nie ma, bierzemy pierwszego z listy
        for b in bookmakers:
            if b["id"] == 6: # ID 6 to Bet365 w tym API
                selected_bookie = b
                break
        
        if not selected_bookie and bookmakers:
            selected_bookie = bookmakers[0]

        if not selected_bookie:
            return jsonify({"error": "Brak danych bukmachera."}), 404

        # Szukamy rynku "Match Winner" (ID: 1)
        # To standardowy zakład 1X2 (Kto wygra)
        match_winner = None
        for bet in selected_bookie["bets"]:
            if bet["id"] == 1:
                match_winner = bet["values"]
                break
        
        if not match_winner:
            return jsonify({"error": "Brak kursów na zwycięzcę."}), 404

        # Formatowanie danych
        result = {
            "bookie_name": selected_bookie["name"],
            "home": next((x["odd"] for x in match_winner if x["value"] == "Home"), "-"),
            "draw": next((x["odd"] for x in match_winner if x["value"] == "Draw"), "-"),
            "away": next((x["odd"] for x in match_winner if x["value"] == "Away"), "-"),
            "update_time": odds_data.get("update")
        }

        ODDS_CACHE[fixture_id] = {'time': now, 'data': result}
        return jsonify(result)

    except Exception as e:
        print(f"Błąd pobierania kursów: {e}")
        return jsonify({"error": "Błąd serwera"}), 500

@app.route('/api/match-predictions/<int:fixture_id>')
def get_match_predictions(fixture_id):
    now = time.time()
    if fixture_id in PREDICTIONS_CACHE and now - PREDICTIONS_CACHE[fixture_id]['time'] < 3600:
        return jsonify(PREDICTIONS_CACHE[fixture_id]['data'])

    try:
        # 1. Pobieramy dane z API
        url_pred = f"{BASE_URL}/predictions?fixture={fixture_id}"
        res_pred = requests.get(url_pred, headers=HEADERS).json()
        if not res_pred.get("response"): return jsonify({"error": "Brak danych"}), 404

        data_pred = res_pred["response"][0]
        pred = data_pred["predictions"]
        teams = data_pred["teams"]
        comparison = data_pred.get("comparison", {})
        
        # --- POBIERANIE KURSÓW (Do Value Bets) ---
        odds_data = {}
        try:
             res_odds = requests.get(f"{BASE_URL}/odds?fixture={fixture_id}", headers=HEADERS).json()
             if res_odds.get("response"):
                 bookmakers = res_odds["response"][0]["bookmakers"]
                 selected = next((b for b in bookmakers if b["id"] == 6), bookmakers[0])
                 bets = next((b for b in selected["bets"] if b["id"] == 1), None)
                 if bets:
                     odds_data = {
                         "home": next((float(x["odd"]) for x in bets["values"] if x["value"] == "Home"), 0),
                         "draw": next((float(x["odd"]) for x in bets["values"] if x["value"] == "Draw"), 0),
                         "away": next((float(x["odd"]) for x in bets["values"] if x["value"] == "Away"), 0),
                     }
        except: pass

        # --- ZAAWANSOWANY MODEL DIXONA-COLESA ---
        top_scores = []
        
        try:
            # 1. Obliczamy siłę ataku i obrony (Lambda)
            # Dodajemy mały 'boost' (+0.15), żeby model nie był zbyt konserwatywny (unikanie ciągłych 1-1)
            h_att = float(teams["home"]["last_5"]["goals"]["for"]["average"])
            h_def = float(teams["home"]["last_5"]["goals"]["against"]["average"])
            a_att = float(teams["away"]["last_5"]["goals"]["for"]["average"])
            a_def = float(teams["away"]["last_5"]["goals"]["against"]["average"])
            
            # Oczekiwane gole (Expected Goals xG)
            # Uwzględniamy przewagę gospodarza (statystycznie +0.2 gola)
            home_lambda = ((h_att + a_def) / 2) * 1.1 + 0.2 
            away_lambda = ((a_att + h_def) / 2) * 1.1
            
            # Parametr korelacji RHO (dla piłki nożnej zazwyczaj ok. -0.13)
            # Koryguje on prawdopodobieństwo niskich wyników (0-0, 1-0, 0-1, 1-1)
            rho = -0.13

            def poisson(k, lamb):
                return (lamb**k * math.exp(-lamb)) / math.factorial(k)

            def solve_dixon_coles(h_goals, a_goals, h_lambda, a_lambda, rho):
                # Bazowe prawdopodobieństwo z Poissona
                prob = poisson(h_goals, h_lambda) * poisson(a_goals, a_lambda)
                
                # Korekta Dixona-Colesa
                correction = 1.0
                if h_goals == 0 and a_goals == 0:
                    correction = 1.0 - (h_lambda * a_lambda * rho)
                elif h_goals == 0 and a_goals == 1:
                    correction = 1.0 + (h_lambda * rho)
                elif h_goals == 1 and a_goals == 0:
                    correction = 1.0 + (a_lambda * rho)
                elif h_goals == 1 and a_goals == 1:
                    correction = 1.0 - rho
                
                return prob * correction

            # Generujemy macierz wyników (0-6 goli)
            scores_probs = []
            for h in range(7): 
                for a in range(7):
                    p = solve_dixon_coles(h, a, home_lambda, away_lambda, rho)
                    scores_probs.append({"score": f"{h} : {a}", "prob": p})
            
            # Normalizacja (żeby suma dawała 100%) i sortowanie
            total_prob_sum = sum(s["prob"] for s in scores_probs)
            for s in scores_probs:
                s["prob_pct"] = f"{round((s['prob'] / total_prob_sum) * 100, 1)}%"
            
            scores_probs.sort(key=lambda x: x["prob"], reverse=True)
            top_scores = scores_probs[:3] # Bierzemy TOP 3 wyniki
            
            # Ustalenie najbardziej prawdopodobnego wyniku do wyświetlenia
            exact_score = top_scores[0]["score"]

        except Exception as e:
            print(f"Błąd modelu: {e}")
            exact_score = "- : -"
            top_scores = []

        # --- VALUE BETS (Zaktualizowane o nowe prawdopodobieństwa z modelu) ---
        value_bets = []
        if odds_data and odds_data.get("home", 0) > 0:
            try:
                # Sumujemy prawdopodobieństwa z naszego modelu Dixona-Colesa, zamiast brać surowe z API
                # To daje nam "Własny Model" vs "Bukmacher"
                my_prob_home = sum(s["prob"] for s in scores_probs if int(s["score"].split(':')[0]) > int(s["score"].split(':')[1])) / total_prob_sum
                my_prob_draw = sum(s["prob"] for s in scores_probs if int(s["score"].split(':')[0]) == int(s["score"].split(':')[1])) / total_prob_sum
                my_prob_away = sum(s["prob"] for s in scores_probs if int(s["score"].split(':')[0]) < int(s["score"].split(':')[1])) / total_prob_sum

                odds_h, odds_d, odds_a = odds_data["home"], odds_data["draw"], odds_data["away"]

                # Value = (Moje% * Kurs) - 1
                if (my_prob_home * odds_h) - 1 > 0.05: 
                    value_bets.append({"type": "HOME", "label": "Wygrana Gospodarzy", "value": round(((my_prob_home*odds_h)-1)*100, 1), "prob": round(my_prob_home*100), "odd": odds_h})
                if (my_prob_away * odds_a) - 1 > 0.05: 
                    value_bets.append({"type": "AWAY", "label": "Wygrana Gości", "value": round(((my_prob_away*odds_a)-1)*100, 1), "prob": round(my_prob_away*100), "odd": odds_a})
                if (my_prob_draw * odds_d) - 1 > 0.15: # Wyższy próg dla remisu
                    value_bets.append({"type": "DRAW", "label": "Remis", "value": round(((my_prob_draw*odds_d)-1)*100, 1), "prob": round(my_prob_draw*100), "odd": odds_d})
            except: pass

        # --- TRENDY (Statystyki) ---
        stats_tips = []
        expected_total = home_lambda + away_lambda
        
        if expected_total >= 3.2: stats_tips.append({"label": "🔥 Potencjalna Strzelanina", "desc": f"Model przewiduje ~{round(expected_total, 1)} goli", "confidence": "Wysoka"})
        elif expected_total >= 2.6: stats_tips.append({"label": "Over 2.5 Gola", "desc": "Ofensywny mecz", "confidence": "Średnia"})
        elif expected_total <= 1.8: stats_tips.append({"label": "Under 2.5 Gola", "desc": "Mecz defensywny", "confidence": "Średnia"})

        # Streaki
        try:
            h_form = teams["home"]["league"]["form"][-3:] if teams["home"]["league"]["form"] else ""
            if h_form == "WWW": stats_tips.append({"label": "🚀 Fala Wznosząca (Gosp)", "desc": "3 wygrane z rzędu", "confidence": "Ekstra"})
        except: pass

        # BTTS
        try:
            h2h = data_pred.get("h2h", [])
            if len(h2h) >= 3:
                btts_count = sum(1 for m in h2h if m["goals"]["home"] > 0 and m["goals"]["away"] > 0)
                if btts_count / len(h2h) >= 0.75:
                     stats_tips.append({"label": "BTTS - Tak", "desc": "Często w H2H", "confidence": "Wysoka"})
        except: pass

        result = {
            "winner": pred["winner"], # Winner z API
            "advice": pred.get("advice", "Brak danych"),
            "percent": pred["percent"], # Procenty z API (do wyświetlenia porównawczo)
            "comparison": comparison,
            "value_bets": value_bets,
            "stats_tips": stats_tips,
            "top_scores": top_scores, # Wyniki z naszego Dixona-Colesa
            "exact_score": exact_score
        }

        PREDICTIONS_CACHE[fixture_id] = {'time': now, 'data': result}
        return jsonify(result)

    except Exception as e:
        print(f"Błąd algorytmu: {e}")
        return jsonify({"error": "Błąd serwera"}), 500

if __name__ == "__main__":
    app.run(debug=True)