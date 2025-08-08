import redis 

dbmemory_name = "memory"
r = redis.StrictRedis(host="localhost",
                                    port=8502,
                                    password="RedisAuth",
                                    db=0)

ttl = r.ttl("memory")  # trả về số giây còn lại, hoặc -1 nếu không có TTL
print(f"TTL còn lại: {ttl} giây")
print(r.hget('memory', 'abcd'))
# r.delete("memory")
# r.hdel("memory", "tôi muốn tạo video marketing")

# r.hset("memory", "abcd", "abcd")
# r.hset("memory", "abcd", "abcd")

# r.expire("memory", 60)

print(r.exists("memory"))





# cursor = 0
# keys_with_expiry = []
# cursor, keys = r.scan(cursor=cursor, count=100)
# print(cursor)
# print(keys)
# for key in keys:
#     ttl = r.ttl(key)
#     print(ttl)
#     if ttl > 0:  # Only keys with expiry
#         keys_with_expiry.append((key.decode(), ttl))
        
# print(keys_with_expiry)