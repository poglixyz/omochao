import re

# Accepts: "10", "10m", "1h", "1h30m", "1.5h", "90s"
_PATTERN = re.compile(
    r"^(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?$",
    re.IGNORECASE,
)


def parse_minutes(text: str) -> float | None:
    """Return duration as minutes, or None if unparseable."""
    text = text.strip()

    try:
        return float(text)  # bare number = minutes
    except ValueError:
        pass

    m = _PATTERN.match(text)
    if m and any(m.groups()):
        hours = float(m.group(1) or 0)
        mins  = float(m.group(2) or 0)
        secs  = float(m.group(3) or 0)
        total = hours * 60 + mins + secs / 60
        return total if total > 0 else None

    return None


def format_duration(minutes: float) -> str:
    """Human-readable round-trip of a minute value."""
    if minutes < 1:
        return f"{int(minutes * 60)}s"
    if minutes < 60:
        return f"{minutes:g}m"
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h}h{m}m" if m else f"{h}h"
