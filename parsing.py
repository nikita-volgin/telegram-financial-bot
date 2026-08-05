import re
from datetime import date, timedelta

AMOUNT = re.compile(r"(?<![\w.])(\d+(?:[.,]\d{1,2})?)(?:\s*(₽|руб\.?|тенге|₸|\$|€))?(?!\w)", re.I)
DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b")

def parse_expense(text: str):
    text=text.strip(); category=None
    tag=re.search(r"\s+#([^#]+)$", text)
    if tag: category=tag.group(1).strip(); text=text[:tag.start()].strip()
    today=date.today(); exp_date=today
    if re.search(r"\s+вчера$",text,re.I): text=re.sub(r"\s+вчера$","",text,flags=re.I); exp_date=today-timedelta(days=1)
    else:
        m=DATE.search(text)
        if m:
            day,month,year=map(int,(m.group(1),m.group(2),m.group(3) or today.year)); exp_date=date(year,month,day); text=(text[:m.start()]+text[m.end():]).strip()
    m=AMOUNT.search(text)
    if not m: raise ValueError("Не нашёл сумму. Пример: «Хлеб 200».")
    amount=float(m.group(1).replace(',','.')); currency={'руб':'₽','руб.':'₽','тенге':'₸'}.get((m.group(2) or '').lower(),m.group(2))
    description=(text[:m.start()]+text[m.end():]).strip(' -—')
    if not description: raise ValueError("Не нашёл описание траты.")
    return description,amount,exp_date.isoformat(),currency,category

def parse_day(value):
    value=value.strip(); today=date.today()
    if not value: return today.isoformat()
    if re.match(r'^\d{4}-\d{2}-\d{2}$',value): return value
    parts=list(map(int,value.split('.')))
    if len(parts)==2:
        d,m=parts; return date(today.year,m,d).isoformat()
    if len(parts)==3:
        d,m,y=parts; return date(y,m,d).isoformat()
    raise ValueError('Invalid date')
