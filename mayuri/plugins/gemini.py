import html
import pickle
import pkg_resources

from google import genai
from mayuri import PREFIX
from mayuri.mayuri import Mayuri
from mayuri.util.graph import post_to_telegraph
from mayuri.util.time import check_time_gap
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from time import time

@Mayuri.on_message(filters.command("gemini", PREFIX))
async def cmd_gemini(c, m):
    chat_id = m.chat.id
    uid = m.from_user.id if m.from_user else m.sender_chat.id
    db = c.db["gemini_history"]
    sdk_version = pkg_resources.get_distribution("google-genai").version
    if len(m.command) == 1:
        return await m.reply_text(await c.tl(m.chat.id, "no_question"))
    if not c.config["gemini"]["API_KEY"]:
        return await m.reply_text("Gemini API_KEY env is missing!!!")
    is_in_gap, _ = await check_time_gap(uid)
    if is_in_gap and not await c.check_sudo(uid):
        return await m.reply_text(await c.tl(m.chat.id, "dont_spam"))
    msg = await m.reply_text(await c.tl(m.chat.id, "find_answers_str"))
    question = (m.text.split(None, 1))[1]
    model = c.config["gemini"]["MODEL"]
    client = genai.Client(api_key=c.config["gemini"]["API_KEY"])
    history = None
    get_history = await db.find_one({"$and": [{"chat_id": chat_id}, {"user_id": uid}]})
    if get_history:
        if get_history["last_updated"] + 60*60 < time(): # 1 hour
            await db.delete_one({"$and": [{"chat_id": chat_id}, {"user_id": uid}]})
            history = None
        else:
            history = pickle.loads(get_history["chat_session"])
    if history:
        chat_session = history
    else:
        chat_session = client.chats.create(model=model)
    try:
        response = chat_session.send_message(question)
        raw_jawaban = html.escape(response.text)
        jawaban = f"""{raw_jawaban}

Powered by: <a href='https://aistudio.google.com'>Gemini</a>
model: {model}
sdk: <a href='https://pypi.org/project/google-genai'>google-genai</a> ({sdk_version})
        """
    except Exception:
        return await msg.edit_text(await c.tl(m.chat.id, "could_not_find_answers"))
    except Exception as e:
        return await msg.edit_text(f"Error: {e}")
    if len(jawaban) > 2000:
        answerlink = await post_to_telegraph(
            False, f"Mayuri ChatBot: {question}", html.escape(f"<code>{raw_jawaban}</code>")
        )
        btn = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(text=await c.tl(m.chat.id, "here"), url=answerlink)
                ]
            ]
        )
        toolong = await c.tl(
            m.chat.id,
            "answers_too_long"
        )
        toolong_msg = f"""{toolong}

Powered by: <a href='https://aistudio.google.com'>Gemini</a>
model: {model}
sdk: <a href='https://pypi.org/project/google-genai'>google-genai</a> ({sdk_version})
        """
        return await msg.edit_text(
            toolong_msg,
            disable_web_page_preview=True,
            reply_markup=btn
            )
    else:
        await msg.edit_text(jawaban, disable_web_page_preview=True)
    dump_session = pickle.dumps(chat_session)
    # Update history
    data = {
        "chat_id": chat_id,
        "user_id": uid,
        "chat_session": dump_session,
        "last_updated": time()
    }
    await db.update_one({"$and": [{"chat_id": chat_id}, {"user_id": uid}]}, {"$set": data}, upsert=True)

@Mayuri.on_message(filters.command("gemini_stop", PREFIX))
async def cmd_genai_stop(c, m):
    chat_id = m.chat.id
    uid = m.from_user.id if m.from_user else m.sender_chat.id
    db = c.db["gemini_history"]
    await db.delete_one({"$and": [{"chat_id": chat_id}, {"user_id": uid}]})
    await m.reply_text(await c.tl(m.chat.id, "gemini_stop"))
