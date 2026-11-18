"""Build Day 3 editorial beats from the same evidence used by the cards."""
from datetime import datetime, timedelta


def _instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def preview_intro(snapshot, agenda, team_name, player_name):
    """Open with a timely decision and keep the existing spoken agenda cues."""
    gameweek = snapshot["next_gw"]
    deadline = _instant(snapshot["deadline"])
    bootstrap = snapshot.get("_bootstrap", {})
    upcoming = [
        event for event in bootstrap.get("events", [])
        if deadline <= _instant(event["deadline_time"]) < deadline + timedelta(days=14)
    ]
    if len(upcoming) >= 3:
        hook = (f"We've got {len(upcoming)} deadlines in the two weeks from Gameweek {gameweek}. "
                "If you're buying this week, make sure you'd still want that player for the next deadline.")
    else:
        hook = f"Who earns a transfer in Gameweek {gameweek}, and when is it worth rolling instead?"

    completed = {int(event["id"]) for event in bootstrap.get("events", [])
                 if event.get("finished") and event.get("data_checked")}
    last_gameweek = max(completed.intersection(snapshot["history_gameweeks"]), default=None)
    results = [row for row in snapshot["fixtures"]
               if last_gameweek is not None and row.get("event") == last_gameweek and row.get("finished")
               and row.get("team_h_score") is not None and row.get("team_a_score") is not None]
    standout = max(
        results,
        key=lambda row: (row["team_h_score"] + row["team_a_score"],
                         abs(row["team_h_score"] - row["team_a_score"]), -row["id"]),
        default=None,
    )
    recap = ""
    if standout and standout["team_h_score"] + standout["team_a_score"] >= 4:
        home, away = standout["team_h_score"], standout["team_a_score"]
        if home == away:
            recap = (f"{team_name(standout['team_h'])} and {team_name(standout['team_a'])} "
                     f"drew {home} all in Gameweek {last_gameweek}.")
        else:
            winner, loser = ("team_h", "team_a") if home > away else ("team_a", "team_h")
            recap = (f"{team_name(standout[winner])} beat {team_name(standout[loser])} "
                     f"{max(home, away)} to {min(home, away)} in Gameweek {last_gameweek}.")

    # Choose a genuinely recent official flag where a lot of managers have a decision.
    cutoff = _instant(snapshot["cutoff"])
    flagged = []
    for raw in bootstrap.get("elements", []):
        player = snapshot["players"].get(int(raw["id"]))
        if not player or player["availability_reason"] == "AVAILABLE" or not player["news_added"] or not player["news"]:
            continue
        if cutoff - timedelta(days=7) <= _instant(player["news_added"]) <= cutoff:
            flagged.append(raw)
    watched = max(flagged, key=lambda raw: (float(raw.get("selected_by_percent") or 0), -raw["id"]), default=None)
    late_news = ""
    if watched and float(watched.get("selected_by_percent") or 0) >= 8:
        player_id = int(watched["id"])
        name = player_name(player_id)
        chance = snapshot["players"][player_id]["availability"]
        if chance is not None and 0 < chance < 1:
            late_news = f"Fantasy Premier League has {name} at {chance:.0%} to play. Keep a bench option ready."
        else:
            late_news = f"If you own {name}, check the latest availability update before you lock your move."

    return " ".join(filter(None, (
        hook, "Welcome back to Fantasy Premier League Vortex.", recap,
        "We have already covered the form and minutes from the last round.",
        f"Now it is decision time. We'll go through {agenda}.", late_news,
    )))


def transfer_player_line(record, name, club, fixture, evidence):
    """Explain market behaviour and offer an original decision tied to the card."""
    identity = f"{name} from {club}"
    action = record["action"]
    if action == "BUY":
        lead = f"{identity} has had {record['transfers_in']:,.0f} transfers in this Gameweek."
    elif action == "SELL":
        lead = f"{identity} has had {record['transfers_out']:,.0f} transfers out this Gameweek."
    else:
        lead = (f"{identity} has averaged {record['recent_average_points']:.1f} points recently. "
                f"We estimate {record['retained_percent_estimate']:.0f} percent of his owners have kept him so far.")

    reason = evidence["availability_reason"]
    chance = evidence["availability"]
    if reason == "SUSPENDED" and chance == 0:
        return f"{lead} He's suspended for the round according to official Fantasy Premier League. Check your bench cover before spending a transfer."
    if reason in {"INJURED", "UNAVAILABLE"} and chance == 0:
        status = "injured" if reason == "INJURED" else "unavailable"
        return f"{lead} Official Fantasy Premier League lists him as {status}. I'd wait for an update before bringing him in."
    if chance is None:
        return f"{lead} His availability is unclear. Check the next team update before deciding."
    if chance < 1:
        return (f"{lead} Fantasy Premier League gives him a {chance:.0%} chance of playing. "
                "I'd wait for the team news if you can.")
    if fixture.startswith("with no fixture"):
        return f"{lead} His club has a blank this Gameweek. Check whether your bench can cover it."
    if not record["has_projection"]:
        return f"{lead} His club play {fixture} next. Our points estimate is missing, so I'd check the team news and your alternatives."
    if action == "HOLD":
        return (f"{lead} His club play {fixture} next. I'd give him another week if your bench is covered "
                "and you have a more urgent move elsewhere.")
    if action == "SELL":
        return (f"{lead} We project {record['xpts']:.1f} points this week. Before you sell, "
                "compare what the replacement gives you over the next few Gameweeks.")
    if record["has_minutes"] and record["xmins"] < 60:
        return (f"{lead} He plays {fixture}, and we project {record['xmins']:.0f} minutes. "
                "I'd want a clearer route to a start before making that transfer.")
    if record["has_horizon"]:
        return (f"{lead} He plays {fixture} next, and we project {record['next_5_xpts']:.1f} points "
                "across the next five Gameweeks. Compare that run with the player you'd sell.")
    return f"{lead} He plays {fixture} next. We project {record['xpts']:.1f} points this week."
