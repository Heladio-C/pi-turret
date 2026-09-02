"""Small shared helpers with no hardware or model dependencies."""


def clamp(value, low, high):
    """Keep value inside [low, high]."""
    return max(low, min(high, value))