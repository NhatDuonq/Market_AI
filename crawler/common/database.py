import psycopg2


def get_connection():

    return psycopg2.connect(
        host="postgres",
        database="market_ai",
        user="market",
        password="abcxyz123@"
    )
