import sqlite3

conn = sqlite3.connect("bets.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS bets (
    number INTEGER UNIQUE,
    user_id INTEGER,
    username TEXT
)
""")

conn.commit()


def get_available_numbers(limit=50):
    cursor.execute("SELECT number FROM bets")
    taken = {row[0] for row in cursor.fetchall()}
    return [n for n in range(1, limit + 1) if n not in taken]


def pick_number(number, user_id, username):
    try:
        cursor.execute(
            "INSERT INTO bets (number, user_id, username) VALUES (?, ?, ?)",
            (number, user_id, username)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_all_bets():
    cursor.execute("SELECT number, username FROM bets ORDER BY number")
    return cursor.fetchall()
