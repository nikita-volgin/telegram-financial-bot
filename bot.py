import asyncio, logging, os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, BotCommand, ReplyKeyboardMarkup, KeyboardButton
from openpyxl import Workbook
from database import Database
from parsing import parse_expense, parse_day

load_dotenv()
TOKEN=os.getenv('BOT_TOKEN','')
ENCRYPTION_KEY=os.getenv('ENCRYPTION_KEY','')
ALLOWED={int(x) for x in os.getenv('ALLOWED_USER_IDS','').split(',') if x.strip().isdigit()}
db=Database(os.getenv('DATABASE_PATH','data/expenses.sqlite3'), os.getenv('DEFAULT_TIMEZONE','Asia/Yekaterinburg'), ENCRYPTION_KEY)
router=Router(); pending={}; awaiting_category=set(); awaiting_date={}; awaiting_amount={}; day_override={}

MENU_COMMANDS = [
    BotCommand(command='start', description='👋 Начать работу с ботом'),
    BotCommand(command='help', description='🧭 Все команды и примеры'),
    BotCommand(command='categories', description='🏷️ Мои категории'),
    BotCommand(command='day', description='📅 Траты за выбранный день'),
    BotCommand(command='report', description='📊 Отчёт и Excel-файл'),
    BotCommand(command='settings', description='⚙️ Валюта и настройки'),
    BotCommand(command='newcategory', description='➕ Добавить категорию'),
    BotCommand(command='currency', description='💱 Изменить валюту'),
]

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='💸 Добавить трату'), KeyboardButton(text='📊 Отчёт')],
        [KeyboardButton(text='🏷️ Категории'), KeyboardButton(text='📅 За день')],
        [KeyboardButton(text='⚙️ Настройки'), KeyboardButton(text='➕ Категория')],
        [KeyboardButton(text='💱 Валюта'), KeyboardButton(text='🧭 Помощь')],
    ],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder='Например: кофе 250',
)

def allowed(user_id): return user_id in ALLOWED
async def guard(message: Message):
    if not allowed(message.from_user.id): await message.answer('Доступ запрещён.'); return False
    await db.ensure_user(message.from_user.id); return True
def categories_kb(rows, prefix='choose'):
    buttons=[InlineKeyboardButton(text=r[1], callback_data=f'{prefix}:{r[0]}') for r in rows]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i+2] for i in range(0,len(buttons),2)]+[[InlineKeyboardButton(text='➕ Новая категория',callback_data='newcat')]])
def saved_expense_kb(expense_id):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📅 Редактировать дату',callback_data=f'editdate:{expense_id}')]])
def day_kb(rows, expense_date):
    buttons=[]
    for r in rows:
        buttons.append([InlineKeyboardButton(text=f'✏️ Сумма: {r[2][:18]}',callback_data=f'editamount:{r[0]}'), InlineKeyboardButton(text='🗑',callback_data=f'delete:{r[0]}')])
    buttons.append([InlineKeyboardButton(text='➕ Добавить трату за этот день',callback_data=f'addday:{expense_date}')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def reminder_loop(bot: Bot):
    """Delivers one light-hearted reminder to each user at 22:00 local time."""
    while True:
        now_utc=datetime.now(timezone.utc)
        for user_id, user_timezone in await db.reminder_users():
            try: local_now=now_utc.astimezone(ZoneInfo(user_timezone))
            except ZoneInfoNotFoundError: local_now=now_utc.astimezone(ZoneInfo('Asia/Yekaterinburg'))
            if local_now.hour == 22 and await db.claim_reminder(user_id, local_now.date().isoformat()):
                try:
                    await bot.send_message(user_id, '🧾 Псс… кошелёк просил передать: пора вспомнить, куда сегодня убежали деньги.\n\nЗапиши траты, пока они не превратились в финансовый детектив 🕵️‍♂️', reply_markup=MAIN_MENU)
                except Exception:
                    logging.exception('Could not send reminder to user %s', user_id)
        await asyncio.sleep(60)

@router.message(Command('start'))
async def start(m:Message):
    if await guard(m): await m.answer('Привет! Отправьте трату: <b>Хлеб 200</b> или <b>Такси 1500 #Транспорт</b>.\n\nВсе действия — в меню внизу 👇', parse_mode='HTML', reply_markup=MAIN_MENU)
@router.message(Command('help'))
async def help_(m:Message):
    if await guard(m): await m.answer('🧭 <b>Меню команд</b>\n\n🏷️ /categories — категории\n📅 /day 03.08 — траты за день\n📊 /report month — отчёт + Excel\n⚙️ /settings — валюта\n➕ /newcategory — добавить категорию\n💱 /currency ₽ — изменить валюту\n\n<b>Быстрый ввод:</b>\n«Хлеб 200», «200 хлеб», «Хлеб 200 вчера».', parse_mode='HTML', reply_markup=MAIN_MENU)
@router.message(Command('categories'))
async def cats(m:Message):
    if not await guard(m): return
    rows=await db.categories(m.from_user.id); await m.answer('Категории:\n'+'\n'.join(f'• {x[1]} ({x[2] or "без ключевых слов"})' for x in rows)+'\n\nЧтобы добавить: /newcategory Название')
@router.message(Command('newcategory'))
async def newcat_cmd(m:Message, command:CommandObject):
    if not await guard(m): return
    name=(command.args or '').strip()
    if not name: awaiting_category.add(m.from_user.id); return await m.answer('Введите название новой категории.')
    try: await db.add_category(m.from_user.id,name); await m.answer(f'Категория «{name}» добавлена.')
    except Exception: await m.answer('Такая категория уже есть.')
@router.message(Command('settings'))
async def settings(m:Message):
    if not await guard(m): return
    await m.answer(f'Валюта по умолчанию: {await db.currency(m.from_user.id)}\nНапоминание: ежедневно в 22:00 по времени Екатеринбурга.\nИзменить валюту: /currency ₽')
@router.message(Command('currency'))
async def currency(m:Message, command:CommandObject):
    if not await guard(m): return
    c=(command.args or '').strip()
    if not c: return await m.answer('Пример: /currency ₽')
    await db.set_currency(m.from_user.id,c); await m.answer(f'Валюта изменена на {c}.')
@router.message(Command('day'))
async def day(m:Message, command:CommandObject):
    if not await guard(m): return
    try: d=parse_day(command.args or '')
    except Exception: return await m.answer('Дата: /day 03.08 или /day 2026-08-03')
    rows=await db.expenses(m.from_user.id,d,d)
    text=f'Траты за {d}:\n'+'\n'.join(f'{r[0]}. {r[2]} — {r[1]:g} {r[4]} ({r[5]})' for r in rows) if rows else f'За {d} трат пока нет.'
    await m.answer(text,reply_markup=day_kb(rows,d))
@router.message(Command('report'))
async def report(m:Message, command:CommandObject):
    if not await guard(m): return
    arg=(command.args or 'month').lower().strip(); today=date.today()
    if arg in ('today','сегодня'): start=end=today
    elif arg in ('week','неделя'): start=today-timedelta(days=today.weekday()); end=today
    elif arg in ('month','месяц'): start=today.replace(day=1); end=today
    else:
        try:
            a,b=arg.split('-'); start=date.fromisoformat(a.strip()) if len(a.strip())==10 else date(today.year,*reversed(tuple(map(int,a.strip().split('.'))))); end=date.fromisoformat(b.strip()) if len(b.strip())==10 else date(today.year,*reversed(tuple(map(int,b.strip().split('.')))))
        except Exception:return await m.answer('Пример: /report month, /report week или /report 01.08-06.08')
    rows=await db.expenses(m.from_user.id,start.isoformat(),end.isoformat())
    if not rows:return await m.answer('За выбранный период трат нет.')
    totals=defaultdict(float)
    for r in rows: totals[r[5]]+=r[1]
    total=sum(totals.values()); currency=rows[0][4]
    text=f'📊 Отчёт: {start:%d.%m}–{end:%d.%m}\nВсего: <b>{total:g} {currency}</b>\n\n'+'\n'.join(f'• {k}: {v:g} {currency} ({v/total:.0%})' for k,v in sorted(totals.items(),key=lambda x:-x[1]))+'\n\nТоп трат:\n'+'\n'.join(f'• {r[2]} — {r[1]:g} {r[4]}' for r in sorted(rows,key=lambda x:-x[1])[:5])
    await m.answer(text,parse_mode='HTML'); await m.answer_document(BufferedInputFile(make_xlsx(rows,totals),'report.xlsx'),caption='Excel-выгрузка')
def make_xlsx(rows,totals):
    wb=Workbook(); ws=wb.active; ws.title='Траты'; ws.append(['Дата','Описание','Сумма','Валюта','Категория'])
    for r in rows: ws.append([r[3],r[2],r[1],r[4],r[5]])
    ss=wb.create_sheet('Сводка'); ss.append(['Категория','Сумма'])
    for k,v in totals.items():ss.append([k,v])
    from io import BytesIO
    out=BytesIO(); wb.save(out); return out.getvalue()
@router.callback_query(F.data.startswith('delete:'))
async def delete(c:CallbackQuery):
    if not allowed(c.from_user.id): return
    await db.delete_expense(c.from_user.id,int(c.data.split(':')[1])); await c.message.edit_text('Трата удалена.'); await c.answer()
@router.callback_query(F.data.startswith('editamount:'))
async def edit_amount(c: CallbackQuery):
    if not allowed(c.from_user.id): return
    awaiting_amount[c.from_user.id]=int(c.data.split(':')[1])
    await c.message.answer('✏️ Введите новую сумму, например: 350.50')
    await c.answer()
@router.callback_query(F.data.startswith('editdate:'))
async def edit_date(c: CallbackQuery):
    if not allowed(c.from_user.id): return
    awaiting_date[c.from_user.id]=int(c.data.split(':')[1])
    await c.message.answer('📅 Введите дату: <b>03.08</b>, <b>03.08.2026</b> или <b>2026-08-03</b>.', parse_mode='HTML')
    await c.answer()
@router.callback_query(F.data.startswith('addday:'))
async def add_day(c: CallbackQuery):
    if not allowed(c.from_user.id): return
    day_override[c.from_user.id]=c.data.split(':',1)[1]
    await c.message.answer(f'➕ Введите трату — сохраню её за {day_override[c.from_user.id]}.')
    await c.answer()
@router.callback_query(F.data.startswith('choose:'))
async def choose(c:CallbackQuery):
    if not allowed(c.from_user.id) or c.from_user.id not in pending:return
    info=pending.pop(c.from_user.id); cat=await db.category(c.from_user.id,int(c.data.split(':')[1])); expense_id=await db.add_expense(c.from_user.id,cat[0],*info[:4]); await db.learn_keyword(c.from_user.id,cat[0],info[1])
    await c.message.edit_text(f'✅ {info[1]} — {info[0]:g} {info[3]}\nКатегория: {cat[1]}\nДата: {info[2]}',reply_markup=saved_expense_kb(expense_id)); await c.answer()
@router.callback_query(F.data=='newcat')
async def newcat_callback(c:CallbackQuery):
    awaiting_category.add(c.from_user.id); await c.message.answer('Введите название новой категории.'); await c.answer()
@router.message(F.text.in_({'💸 Добавить трату','📊 Отчёт','🏷️ Категории','📅 За день','⚙️ Настройки','➕ Категория','💱 Валюта','🧭 Помощь'}))
async def menu_buttons(m: Message):
    if not await guard(m): return
    action=m.text
    if action=='💸 Добавить трату':
        await m.answer('💸 Пришлите трату: <b>Кофе 250</b>, <b>200 хлеб</b> или <b>Такси 1500 #Транспорт</b>.',parse_mode='HTML')
    elif action=='📊 Отчёт':
        await report(m, CommandObject(prefix='/', command='report', args='month'))
    elif action=='🏷️ Категории':
        await cats(m)
    elif action=='📅 За день':
        await m.answer('📅 Пришлите дату командой: <b>/day 03.08</b>\nИли без даты: <b>/day</b> — траты за сегодня.',parse_mode='HTML')
    elif action=='⚙️ Настройки':
        await settings(m)
    elif action=='➕ Категория':
        awaiting_category.add(m.from_user.id); await m.answer('➕ Введите название новой категории.')
    elif action=='💱 Валюта':
        await m.answer('💱 Укажите валюту так: <b>/currency ₽</b>, <b>/currency $</b> или <b>/currency ₸</b>.',parse_mode='HTML')
    else:
        await help_(m)
@router.message(F.text)
async def text(m:Message):
    if not await guard(m): return
    uid=m.from_user.id
    if uid in awaiting_amount:
        expense_id=awaiting_amount[uid]
        try: amount=float(m.text.strip().replace(',','.')); assert amount>0
        except Exception: return await m.answer('Введите положительную сумму, например: 350.50')
        awaiting_amount.pop(uid)
        if await db.update_expense_amount(uid,expense_id,amount): await m.answer(f'✅ Сумма изменена на {amount:g}.')
        else: await m.answer('Не нашёл эту трату.')
        return
    if uid in awaiting_date:
        expense_id=awaiting_date[uid]
        try: expense_date=parse_day(m.text)
        except Exception: return await m.answer('Введите дату в формате 03.08, 03.08.2026 или 2026-08-03.')
        awaiting_date.pop(uid)
        if await db.update_expense_date(uid,expense_id,expense_date): await m.answer(f'✅ Трата перенесена на {expense_date}.')
        else: await m.answer('Не нашёл эту трату.')
        return
    if uid in awaiting_category:
        awaiting_category.remove(uid)
        try:
            category_id=await db.add_category(uid,m.text.strip())
            if uid in pending:
                info=pending.pop(uid); expense_id=await db.add_expense(uid,category_id,*info[:4]); await db.learn_keyword(uid,category_id,info[1])
                await m.answer(f'✅ {info[1]} — {info[0]:g} {info[3]}\nНовая категория: {m.text.strip()}\nДата: {info[2]}',reply_markup=saved_expense_kb(expense_id))
            else: await m.answer(f'Категория «{m.text.strip()}» добавлена.')
        except Exception: await m.answer('Такая категория уже есть.')
        return
    try: description,amount,d,currency,manual=parse_expense(m.text)
    except ValueError as e:return await m.answer(str(e))
    d=day_override.pop(uid,d)
    currency=currency or await db.currency(uid); rows=await db.categories(uid)
    cat=next((x for x in rows if x[1].lower()==manual.lower()),None) if manual else await db.find_category(uid,description)
    if cat:
        expense_id=await db.add_expense(uid,cat[0],amount,description,d,currency); return await m.answer(f'✅ {description} — {amount:g} {currency}\nКатегория: {cat[1]}\nДата: {d}',reply_markup=saved_expense_kb(expense_id))
    pending[uid]=(amount,description,d,currency); await m.answer('Не удалось определить категорию. Выберите:',reply_markup=categories_kb(rows))
async def main():
    if not TOKEN or TOKEN=='replace_me': raise RuntimeError('Fill BOT_TOKEN in .env')
    if not ALLOWED: raise RuntimeError('Set ALLOWED_USER_IDS in .env')
    if not ENCRYPTION_KEY: raise RuntimeError('Set ENCRYPTION_KEY in .env or hosting environment')
    await db.init(); bot=Bot(TOKEN); await bot.set_my_commands(MENU_COMMANDS)
    for user_id in ALLOWED:
        await bot.send_message(user_id, '✅ Бот запущен. Главное меню — внизу 👇', reply_markup=MAIN_MENU)
    dp=Dispatcher(); dp.include_router(router); reminder_task=asyncio.create_task(reminder_loop(bot))
    try: await dp.start_polling(bot)
    finally: reminder_task.cancel()
if __name__=='__main__': logging.basicConfig(level=logging.INFO); asyncio.run(main())
