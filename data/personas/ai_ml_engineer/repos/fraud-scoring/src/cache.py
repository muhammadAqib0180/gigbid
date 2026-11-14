import redis

r = redis.Redis.from_url(REDIS_URL)


def cached(key: str, ttl: int = 300):
    hit = r.get(key)
    if hit:
        return json.loads(hit)
    value = compute(key)
    r.setex(key, ttl, json.dumps(value))
    return value
