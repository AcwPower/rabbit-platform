from datetime import timedelta

def boss_requested_window(at, start_time, end_time):
    """Current or next Beijing daily window; an ongoing window starts now."""
    local = at + timedelta(hours=8)
    hour, minute = map(int, start_time.split(':'))
    start = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    hour, minute = map(int, end_time.split(':'))
    end = start.replace(hour=hour, minute=minute)
    if end <= start:
        end += timedelta(days=1)
    if start > local and start - timedelta(days=1) <= local < end - timedelta(days=1):
        start -= timedelta(days=1)
        end -= timedelta(days=1)
    elif end <= local:
        start += timedelta(days=1)
        end += timedelta(days=1)
    return max(start, local) - timedelta(hours=8), end - timedelta(hours=8)

def default_end_at(boarded_at, end_time):
    """Next occurrence of the team's end time, expressed in UTC for persistence."""
    local=boarded_at+timedelta(hours=8)
    hour,minute=map(int,end_time.split(':'))
    end=local.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if end<=local:end+=timedelta(days=1)
    return end-timedelta(hours=8)
