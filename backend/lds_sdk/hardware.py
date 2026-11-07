"""Read-only machine telemetry; core job and maintenance guards own its probe."""

__all__ = ['machine_stats']


def machine_stats() -> dict:
    """Return the cached machine snapshot, omitting unavailable hardware fields."""
    from app.services.system_stats import machine_stats as read
    return read()
