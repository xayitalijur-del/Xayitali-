import sqlite3

def init_db():
    conn = sqlite3.connect("tez_mebel.db")
    cursor = conn.cursor()

    # Mahsulotlar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            price REAL
        )
    """)

    # Buyurtmalar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            fullname TEXT,
            phone TEXT,
            address TEXT,
            total_price REAL,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_default_products():
    conn = sqlite3.connect("tez_mebel.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        sample_products = [
            ("Zamonaviy Oshxona Mebeli + Vitayajka va Gaz Panel", "Komplekt: yuqori sifatli MDF oshxona mebeli va 100% kafolatli jihozlar.", 4500000),
            ("Keng Kupe Shkaf (Yotoqxona uchun)", "Mustahkam materialdan tayyorlangan zamonaviy shkaf.", 3200000),
            ("Ofis Stoli va Kreslo to'plami", "Qulay va ishbop zamonaviy ofis jihozi.", 1800000),
        ]
        cursor.executemany("INSERT INTO products (name, description, price) VALUES (?, ?, ?)", sample_products)
        conn.commit()
    conn.close()
