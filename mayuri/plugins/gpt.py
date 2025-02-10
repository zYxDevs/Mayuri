import html
import pkg_resources

from azure.ai.inference.aio import ChatCompletionsClient
from azure.ai.inference.models import AssistantMessage, UserMessage
from azure.core.credentials import AzureKeyCredential

from mayuri import PREFIX
from mayuri.mayuri import Mayuri
from mayuri.util.graph import post_to_telegraph
from mayuri.util.time import check_time_gap
from pyrogram import filters
from pyrogram.errors import MessageTooLong
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from time import time

@Mayuri.on_message(filters.command("gpt", PREFIX))
async def cmd_gpt(c,m):
    endpoint = "https://models.inference.ai.azure.com"
    model = c.config["gpt"]["MODEL"]
    sdk_version = pkg_resources.get_distribution("azure-ai-inference").version
    if len(m.command) == 1:
        return await m.reply_text(await c.tl(m.chat.id, "no_question"))
    if not c.config["gpt"]["API_KEY"]:
        return await m.reply_text("OPENAI_API env is missing!!!")
    db = c.db["gpt_chat_history"]
    uid = m.from_user.id if m.from_user else m.sender_chat.id
    is_in_gap, _ = await check_time_gap(uid)
    if is_in_gap and not await c.check_sudo(uid):
        return await m.reply_text(await c.tl(m.chat.id, "dont_spam"))
    question = (m.text.split(None, 1))[1]
    msg = await m.reply_text(await c.tl(m.chat.id, "find_answers_str"))
    answer = ""
    history = []
    try:
        get_history = await db.find_one({"$and": [{"chat_id": m.chat.id}, {"user_id": uid}]})
        if get_history:
            if get_history["last_updated"] + 60*60 < time():
                await db.delete_one({"$and": [{"chat_id": m.chat.id}, {"user_id": uid}]})
                get_history = None
            for h in get_history["history"]:
                if h["role"] == "assistant":
                    history.append(AssistantMessage(content=h["content"]))
                else:
                    history.append(UserMessage(content=h["content"]))
        history.append(UserMessage(content=question))
        async with ChatCompletionsClient(endpoint, AzureKeyCredential(c.config["gpt"]["API_KEY"])) as client:
            response = await client.complete(
                messages=history,
                temperature=1.0,
                top_p=1.0,
                max_tokens=1000,
                model=model
            )
            await client.close()
        raw_answer = response.choices[0].message.content
        raw_answer = html.escape(raw_answer)
        answer = f"""{raw_answer}

Powered by: <a href='https://github.com/marketplace/models/azure-openai/{model}'>Azure AI</a>
model: {model}
sdk: <a href='https://pypi.org/project/azure-ai-inference/'>azure-ai-inference</a> ({sdk_version})
        """
        await msg.edit_text(answer, disable_web_page_preview=True)
    except MessageTooLong:
        answerlink = await post_to_telegraph(
            False, f"Mayuri ChatBot: {question}", html.escape(f"<code>{raw_answer}</code>")
        )
        btn = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(text=await c.tl(m.chat.id, "show_answer"), url=answerlink)
                ]
            ]
        )
        toolong = await c.tl(
            m.chat.id,
            "answers_too_long"
        )
        toolong_msg = f"""{toolong}

Powered by: <a href='https://github.com/marketplace/models/azure-openai/{model}'>Azure AI</a>
model: {model}
sdk: <a href='https://pypi.org/project/azure-ai-inference/'>azure-ai-inference</a> ({sdk_version})
        """
        return await msg.edit_text(
            toolong_msg,
            disable_web_page_preview=True,
            reply_markup=btn
            )
    except Exception as e:
        await msg.edit_text(f"ERROR: {e}")
    else:
        await db.update_one({"$and": [{"chat_id": m.chat.id}, {"user_id": uid}]}, {"$push": {"history": {"role": "user","content": question}}}, upsert=True)
        await db.update_one({"$and": [{"chat_id": m.chat.id}, {"user_id": uid}]}, {"$push": {"history": {"role": "assistant","content": raw_answer}}}, upsert=True)
        await db.update_one({"$and": [{"chat_id": m.chat.id}, {"user_id": uid}]}, {"$set": {"last_updated": time()}}, upsert=True)

@Mayuri.on_message(filters.command("gptstop", PREFIX))
async def cmd_gptstop(c,m):
    db = c.db["gpt_chat_history"]
    uid = m.from_user.id if m.from_user else m.sender_chat.id
    await db.delete_one({"$and": [{"chat_id": m.chat.id}, {"user_id": uid}]})
    await m.reply_text(await c.tl(m.chat.id, "gpt_history_deleted"))
