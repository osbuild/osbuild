def cleanup(*objs):
    """Call cleanup method for all objects, filters None values out"""
    _ = map(lambda o: o.cleanup(), filter(None, objs))
