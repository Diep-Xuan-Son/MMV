import redis 

dbmemory_name = "memory"
r = redis.StrictRedis(host="localhost",
                                    port=6669,
                                    password="RedisAuth",
                                    db=0)

ttl = r.ttl("memory")  # trả về số giây còn lại, hoặc -1 nếu không có TTL
print(f"TTL còn lại: {ttl} giây")
print(r.hget('memory', 'abcd'))
# r.delete("memory")
# r.hdel("memory", "tôi muốn tạo video marketing")

r.hset("memory", "abcd", "abcd")
# r.hset("memory", "abcd", "abcd")

# r.expire("memory", 60)

# print(r.exists("memory"))