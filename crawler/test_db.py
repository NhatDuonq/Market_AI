import psycopg2


conn = psycopg2.connect(
    host="postgres",
    database="market_ai",
    user="market",
    password="abcxyz123@"
)

cursor = conn.cursor()

cursor.execute("""
SELECT current_database();
""")

result = cursor.fetchone()

print("Connected database:", result[0])


cursor.close()
conn.close()
