"""Full club identities for presentation, keyed by stable FPL club code."""

# FPL publishes short display names for these clubs even in its name field.
_FULL_CLUB_NAMES = {
    1: ("Man Utd", "Manchester United"),
    2: ("Leeds", "Leeds United"),
    4: ("Newcastle", "Newcastle United"),
    6: ("Spurs", "Tottenham Hotspur"),
    17: ("Nott'm Forest", "Nottingham Forest"),
    21: ("West Ham", "West Ham United"),
    36: ("Brighton", "Brighton & Hove Albion"),
    39: ("Wolves", "Wolverhampton Wanderers"),
    43: ("Man City", "Manchester City"),
}


def full_club_name(team, canonical_name=None, *, speech=False):
    """Expand known provider display aliases without guessing from abbreviations."""
    canonical = (canonical_name or team.get("name") or "").strip()
    override = _FULL_CLUB_NAMES.get(team.get("code"))
    if override and canonical.casefold() == override[0].casefold():
        canonical = override[1]
    full = team.get("full_name") or canonical
    name = (team.get("speech_name") or full) if speech else full
    if not name or name.casefold() == str(team.get("short") or "").casefold():
        raise ValueError(f"Unresolved full name for club {team.get('id')}")
    return name.replace("&", "and") if speech else name
