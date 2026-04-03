"""
data_prep.py
------------
Parses raw Cricsheet YAML files for England Men's T20 Internationals
and produces a clean, analysis-ready CSV for use in Power BI.

Data source: Cricsheet (https://cricsheet.org) — T20I match data (YAML format)

Output columns:
    match_id, date, city, venue, match_type, gender,
    team1, team2, teams, winner, toss_winner, toss_decision,
    player_of_match, innings_number, innings_name, batting_team,
    bowling_team, over, ball_in_over, ball_str, batter, bowler,
    non_striker, runs_total, runs_batter, runs_extras, extras_detail,
    is_legal_ball, is_boundary, is_dot_ball, wicket_flag,
    dismissal_kind, player_out, fielders, phase

Usage:
    1. Download T20I YAML zip from https://cricsheet.org/downloads/
    2. Extract to a local folder
    3. Update YAML_FOLDER and OUTPUT_CSV paths below
    4. Run: python data_prep.py
"""

import os
import yaml
import pandas as pd

# ── CONFIG ────────────────────────────────────────────────────────────────────
YAML_FOLDER = "data/raw_yaml"        # folder containing Cricsheet .yaml files
OUTPUT_CSV  = "data/england_t20i_ball_by_ball_clean.csv"
# ─────────────────────────────────────────────────────────────────────────────


def classify_phase(over):
    """Classify match phase based on over number."""
    if over is None:
        return None
    if 1 <= over <= 6:
        return "Powerplay"
    elif 7 <= over <= 15:
        return "Middle"
    elif 16 <= over <= 20:
        return "Death"
    return "Other"


def parse_deliveries(innings_detail, team1, team2):
    """
    Handle both Cricsheet delivery formats:
      - Legacy: list of {over.ball: ball_data}
      - Modern: list of {over: int, deliveries: [...]}
    Returns a flat list of (ball_key, ball_data) tuples.
    """
    deliveries = innings_detail.get("deliveries")

    if deliveries is None:
        # Modern overs format
        deliveries = []
        for over_block in innings_detail.get("overs", []):
            over_index = over_block.get("over", 0)
            for i, d in enumerate(over_block.get("deliveries", []), start=1):
                key = float(f"{over_index}.{i}")
                deliveries.append({key: d})

    return deliveries or []


def parse_match(data, filename):
    """Extract all ball-by-ball rows from a single match YAML."""
    rows = []
    info = data.get("info", {})

    # ── Filters ───────────────────────────────────────────────────────────────
    teams      = info.get("teams", [])
    gender     = info.get("gender")
    match_type = info.get("match_type")

    if gender != "male":
        return rows
    if "England" not in teams:
        return rows
    if match_type not in ("T20", "T20I", "T20I (non-official)"):
        return rows

    # ── Match metadata ────────────────────────────────────────────────────────
    match_id   = info.get("match_id", filename)
    city       = info.get("city")
    venue      = info.get("venue")
    dates      = info.get("dates", [])
    date       = dates[0] if dates else None
    outcome    = info.get("outcome", {})
    winner     = outcome.get("winner")
    toss       = info.get("toss", {})
    toss_winner   = toss.get("winner")
    toss_decision = toss.get("decision")

    pom = info.get("player_of_match")
    player_of_match = pom[0] if isinstance(pom, list) and pom else pom

    team1 = teams[0] if len(teams) > 0 else None
    team2 = teams[1] if len(teams) > 1 else None

    # ── Innings loop ──────────────────────────────────────────────────────────
    for innings_number, innings in enumerate(data.get("innings", []), start=1):
        for innings_name, innings_detail in innings.items():

            batting_team = innings_detail.get("team")
            bowling_team = None
            if team1 and team2:
                bowling_team = team2 if batting_team == team1 else team1

            deliveries = parse_deliveries(innings_detail, team1, team2)

            for delivery in deliveries:
                for ball_key, ball_data in delivery.items():

                    # ── Over / ball number ────────────────────────────────────
                    ball_str = str(ball_key)
                    try:
                        over_part, ball_part = ball_str.split(".")
                        over_number  = int(over_part) + 1   # convert to 1-based
                        ball_in_over = int(ball_part)
                    except Exception:
                        over_number = ball_in_over = None

                    # ── Runs and extras ───────────────────────────────────────
                    runs         = ball_data.get("runs", {})
                    extras       = ball_data.get("extras", {})
                    runs_total   = runs.get("total", 0)
                    runs_batter  = runs.get("batsman", 0)
                    runs_extras  = runs.get("extras", 0)

                    extras_keys  = extras.keys()
                    is_wide      = "wides"   in extras_keys
                    is_noball    = "noballs" in extras_keys
                    is_legal_ball = 0 if (is_wide or is_noball) else 1
                    is_boundary  = 1 if runs_batter in (4, 6) else 0
                    is_dot_ball  = 1 if (runs_total == 0 and runs_extras == 0) else 0

                    # ── Wicket details ────────────────────────────────────────
                    wicket_flag = dismissal_kind = player_out = fielders = None
                    wicket_flag = 0

                    wickets_data = ball_data.get("wickets") or (
                        [ball_data["wicket"]] if "wicket" in ball_data else None
                    )

                    if wickets_data:
                        wicket_flag = 1
                        w = wickets_data[0]
                        dismissal_kind = w.get("kind")
                        player_out     = w.get("player_out")
                        f = w.get("fielders")
                        fielders = ", ".join(f) if isinstance(f, list) else f

                    # ── Build row ─────────────────────────────────────────────
                    rows.append({
                        "match_id":        match_id,
                        "date":            date,
                        "city":            city,
                        "venue":           venue,
                        "match_type":      match_type,
                        "gender":          gender,
                        "team1":           team1,
                        "team2":           team2,
                        "teams":           ", ".join(teams) if teams else None,
                        "winner":          winner,
                        "toss_winner":     toss_winner,
                        "toss_decision":   toss_decision,
                        "player_of_match": player_of_match,
                        "innings_number":  innings_number,
                        "innings_name":    innings_name,
                        "batting_team":    batting_team,
                        "bowling_team":    bowling_team,
                        "over":            over_number,
                        "ball_in_over":    ball_in_over,
                        "ball_str":        ball_str,
                        "batter":          ball_data.get("batter") or ball_data.get("batsman"),
                        "bowler":          ball_data.get("bowler"),
                        "non_striker":     ball_data.get("non_striker"),
                        "runs_total":      runs_total,
                        "runs_batter":     runs_batter,
                        "runs_extras":     runs_extras,
                        "extras_detail":   str(extras) if extras else None,
                        "is_legal_ball":   is_legal_ball,
                        "is_boundary":     is_boundary,
                        "is_dot_ball":     is_dot_ball,
                        "wicket_flag":     wicket_flag,
                        "dismissal_kind":  dismissal_kind,
                        "player_out":      player_out,
                        "fielders":        fielders,
                    })

    return rows


def main():
    all_rows = []
    file_count = england_match_count = 0

    for filename in os.listdir(YAML_FOLDER):
        if not filename.endswith((".yaml", ".yml")):
            continue

        full_path = os.path.join(YAML_FOLDER, filename)
        with open(full_path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
            except Exception as e:
                print(f"Skipping {filename}: {e}")
                continue

        rows = parse_match(data, filename)
        if rows:
            england_match_count += 1
            all_rows.extend(rows)

        file_count += 1
        if file_count % 50 == 0:
            print(f"  Processed {file_count} files | England matches: {england_match_count}")

    print(f"\nComplete: {file_count} files scanned | "
          f"{england_match_count} England matches | {len(all_rows)} deliveries")

    df = pd.DataFrame(all_rows)
    df["phase"] = df["over"].apply(classify_phase)

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"Saved: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
