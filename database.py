import aiosqlite
from pathlib import Path
from security import DataCipher

BASE_CATEGORIES = {
    "Продукты": "хлеб,молоко,магазин,магнит,пятерочка,еда,супермаркет",
    "Кафе и рестораны": "кафе,ресторан,кофе,обед,ужин,доставка",
    "Транспорт": "такси,метро,автобус,бензин,заправка",
    "Жильё и коммунальные услуги": "аренда,квартира,жкх,коммуналка,электричество",
    "Здоровье": "аптека,врач,лекарство,больница",
    "Одежда": "одежда,обувь,магазин одежды",
    "Развлечения": "кино,театр,netflix,игра,концерт",
    "Связь и интернет": "интернет,телефон,связь,мобильный",
    "Прочее": "",
}

class Database:
    def __init__(self, path: str, default_timezone: str = 'Asia/Yekaterinburg', encryption_key: str = ''):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path, self.default_timezone = path, default_timezone
        self.cipher = DataCipher(encryption_key)

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript('''
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, currency TEXT NOT NULL DEFAULT '₽', timezone TEXT NOT NULL DEFAULT 'Europe/Moscow');
            CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT NOT NULL, keywords TEXT NOT NULL DEFAULT '', UNIQUE(user_id,name));
            CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, category_id INTEGER, amount REAL NOT NULL, description TEXT NOT NULL, expense_date TEXT NOT NULL, currency TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(category_id) REFERENCES categories(id));
            CREATE TABLE IF NOT EXISTS reminder_log (user_id INTEGER NOT NULL, reminder_date TEXT NOT NULL, PRIMARY KEY(user_id, reminder_date));
            ''')
            columns={row[1] for row in await (await db.execute("PRAGMA table_info(expenses)")).fetchall()}
            if 'encrypted' not in columns:
                await db.execute("ALTER TABLE expenses ADD COLUMN encrypted INTEGER NOT NULL DEFAULT 0")
            rows=await (await db.execute("SELECT id,amount,description FROM expenses WHERE encrypted=0")).fetchall()
            for expense_id, amount, description in rows:
                await db.execute("UPDATE expenses SET amount=?,description=?,encrypted=1 WHERE id=?", (self.cipher.encrypt(str(amount)),self.cipher.encrypt(description),expense_id))
            await db.commit()

    async def ensure_user(self, user_id):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT OR IGNORE INTO users(user_id,timezone) VALUES(?,?)", (user_id,self.default_timezone))
            await db.execute("UPDATE users SET timezone=? WHERE user_id=? AND timezone='Europe/Moscow'", (self.default_timezone,user_id))
            for name, keys in BASE_CATEGORIES.items():
                await db.execute("INSERT OR IGNORE INTO categories(user_id,name,keywords) VALUES(?,?,?)", (user_id,name,keys))
            await db.commit()

    async def categories(self, user_id):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("SELECT id,name,keywords FROM categories WHERE user_id=? ORDER BY name",(user_id,)); return await cur.fetchall()

    async def category(self, user_id, category_id):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("SELECT id,name,keywords FROM categories WHERE user_id=? AND id=?",(user_id,category_id)); return await cur.fetchone()

    async def find_category(self, user_id, text):
        rows=await self.categories(user_id); text=text.lower()
        return next((r for r in rows if any(k.strip() and k.strip() in text for k in r[2].lower().split(','))), None)

    async def add_category(self,user_id,name,keywords=''):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("INSERT INTO categories(user_id,name,keywords) VALUES(?,?,?)",(user_id,name,keywords)); await db.commit(); return cur.lastrowid

    async def add_expense(self,user_id,category_id,amount,description,date,currency):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("INSERT INTO expenses(user_id,category_id,amount,description,expense_date,currency,encrypted) VALUES(?,?,?,?,?,?,1)",(user_id,category_id,self.cipher.encrypt(str(amount)),self.cipher.encrypt(description),date,currency)); await db.commit(); return cur.lastrowid

    async def learn_keyword(self, user_id, category_id, phrase):
        """Retain a manually confirmed phrase for future automatic categorisation."""
        keyword=phrase.lower().strip()
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("SELECT keywords FROM categories WHERE id=? AND user_id=?",(category_id,user_id)); row=await cur.fetchone()
            if row and keyword not in [x.strip() for x in row[0].split(',')]:
                await db.execute("UPDATE categories SET keywords=? WHERE id=?", ((row[0]+','+keyword).strip(','),category_id))
                await db.commit()

    async def delete_expense(self,user_id,expense_id):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM expenses WHERE id=? AND user_id=?",(expense_id,user_id)); await db.commit()

    async def update_expense_amount(self, user_id, expense_id, amount):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("UPDATE expenses SET amount=?,encrypted=1 WHERE id=? AND user_id=?", (self.cipher.encrypt(str(amount)),expense_id,user_id))
            await db.commit(); return cur.rowcount == 1

    async def update_expense_date(self, user_id, expense_id, expense_date):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("UPDATE expenses SET expense_date=? WHERE id=? AND user_id=?", (expense_date,expense_id,user_id))
            await db.commit(); return cur.rowcount == 1

    async def expenses(self,user_id,start,end):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute('''SELECT e.id,e.amount,e.description,e.expense_date,e.currency,COALESCE(c.name,'Прочее'),e.encrypted FROM expenses e LEFT JOIN categories c ON c.id=e.category_id WHERE e.user_id=? AND e.expense_date BETWEEN ? AND ? ORDER BY e.expense_date DESC,e.id DESC''',(user_id,start,end))
            rows=await cur.fetchall()
            return [(r[0],float(self.cipher.decrypt(r[1])) if r[6] else float(r[1]),self.cipher.decrypt(r[2]) if r[6] else r[2],r[3],r[4],r[5]) for r in rows]

    async def currency(self,user_id):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("SELECT currency FROM users WHERE user_id=?",(user_id,)); row=await cur.fetchone(); return row[0]

    async def set_currency(self,user_id,currency):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET currency=? WHERE user_id=?",(currency,user_id)); await db.commit()

    async def reminder_users(self):
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("SELECT user_id,timezone FROM users"); return await cur.fetchall()

    async def claim_reminder(self, user_id, reminder_date):
        """Returns True only once per user and local calendar date."""
        async with aiosqlite.connect(self.path) as db:
            cur=await db.execute("INSERT OR IGNORE INTO reminder_log(user_id,reminder_date) VALUES(?,?)", (user_id,reminder_date))
            await db.commit(); return cur.rowcount == 1
