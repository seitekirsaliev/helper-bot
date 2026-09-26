import json
import os
from pathlib import Path

from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

DATA = Path("data")
DATA.mkdir(exist_ok=True)
MEMORY = DATA / "memory.json"

SYSTEM = """Ты Помощник Сейтека. Отвечай по-русски, коротко и по делу.
Умеешь: заметки, задачи, напоминания текстом, общие вопросы.
Не выдумывай цифры Wildberries. Рекламу и цены не запускаешь.
Если просят сохранить — подтверди одной строкой, что записал.
"""


def load_mem() -> dict:
    if MEMORY.exists():
        return json.loads(MEMORY.read_text(encoding="utf-8"))
    return {"notes": [], "tasks": []}


def save_mem(mem: dict) -> None:
    MEMORY.write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")


def client() -> OpenAI:
    return OpenAI(api_key=os.environ["XAI_API_KEY"], base_url="https://api.x.ai/v1")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Помощник на связи.\n"
        "/note текст — сохранить заметку\n"
        "/notes — список заметок\n"
        "/task текст — задача\n"
        "/tasks — задачи\n"
        "/done номер — закрыть задачу\n"
        "Можно просто написать или прислать голосовое (пока лучше текстом)."
    )


async def note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Напишите: /note купить коробку")
        return
    mem = load_mem()
    mem["notes"].append(text)
    save_mem(mem)
    await update.message.reply_text(f"Записал: {text}")


async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mem = load_mem()
    if not mem["notes"]:
        await update.message.reply_text("Заметок пока нет.")
        return
    lines = [f"{i}. {n}" for i, n in enumerate(mem["notes"], 1)]
    await update.message.reply_text("Заметки:\n" + "\n".join(lines))


async def task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Напишите: /task позвонить поставщику")
        return
    mem = load_mem()
    mem["tasks"].append({"text": text, "done": False})
    save_mem(mem)
    await update.message.reply_text(f"Задача: {text}")


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mem = load_mem()
    if not mem["tasks"]:
        await update.message.reply_text("Задач нет.")
        return
    lines = []
    for i, t in enumerate(mem["tasks"], 1):
        mark = "x" if t["done"] else " "
        lines.append(f"{i}. [{mark}] {t['text']}")
    await update.message.reply_text("Задачи:\n" + "\n".join(lines))


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Напишите: /done 1")
        return
    idx = int(context.args[0]) - 1
    mem = load_mem()
    if idx < 0 or idx >= len(mem["tasks"]):
        await update.message.reply_text("Нет такой задачи.")
        return
    mem["tasks"][idx]["done"] = True
    save_mem(mem)
    await update.message.reply_text(f"Закрыл: {mem['tasks'][idx]['text']}")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return
    mem = load_mem()
    extra = ""
    if mem["notes"] or mem["tasks"]:
        extra = "\n\nИзвестные заметки: " + "; ".join(mem["notes"][-10:])
        open_tasks = [t["text"] for t in mem["tasks"] if not t["done"]]
        if open_tasks:
            extra += "\nОткрытые задачи: " + "; ".join(open_tasks)
    try:
        r = client().chat.completions.create(
            model=os.environ.get("XAI_MODEL", "grok-4-fast"),
            messages=[
                {"role": "system", "content": SYSTEM + extra},
                {"role": "user", "content": text},
            ],
        )
        answer = r.choices[0].message.content or "Пустой ответ."
    except Exception as e:
        answer = f"Не смог ответить. Проверьте ключ API. ({e.__class__.__name__})"
    await update.message.reply_text(answer[:4000])


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Нет TELEGRAM_BOT_TOKEN")
    if not os.environ.get("XAI_API_KEY"):
        raise SystemExit("Нет XAI_API_KEY")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("note", note))
    app.add_handler(CommandHandler("notes", notes))
    app.add_handler(CommandHandler("task", task))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
