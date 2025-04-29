import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
import requests, urllib.parse, filetype, os, time, shutil, tldextract, asyncio, json, random
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.config import Config
from plugins.functions.verify import check_verification, get_token
from plugins.functions.forcesub import handle_force_subscribe
from plugins.functions.display_progress import humanbytes
from plugins.functions.help_uploadbot import DownLoadFile
from plugins.functions.ran_text import random_char
from plugins.database.add import AddUser

cookies_file = 'cookies.txt'

@Client.on_message(filters.private & filters.regex(pattern=".*http.*"))
async def echo(bot, update):
    if update.from_user.id != Config.OWNER_ID:
        if not await check_verification(bot, update.from_user.id) and Config.TRUE_OR_FALSE:
            button = [[
                InlineKeyboardButton("✓⃝ Vᴇʀɪꜰʏ ✓⃝", url=await get_token(bot, update.from_user.id, f"https://telegram.me/{Config.BOT_USERNAME}?start="))
                ], [
                InlineKeyboardButton("🔆 Wᴀᴛᴄʜ Hᴏᴡ Tᴏ Vᴇʀɪꜰʏ 🔆", url=f"{Config.VERIFICATION}")
            ]]
            await update.reply_text(
                text="<b>Pʟᴇᴀsᴇ Vᴇʀɪꜰʏ Fɪʀsᴛ Tᴏ Usᴇ Mᴇ</b>",
                protect_content=True,
                reply_markup=InlineKeyboardMarkup(button)
            )
            return

    # Handle logs
    if Config.LOG_CHANNEL:
        try:
            log_message = await update.forward(Config.LOG_CHANNEL)
            log_info = f"Message Sender Information\nFirst Name: {update.from_user.first_name}\nUser ID: {update.from_user.id}\nUsername: @{update.from_user.username if update.from_user.username else ''}\nUser Link: {update.from_user.mention}"
            await log_message.reply_text(
                text=log_info,
                disable_web_page_preview=True,
                quote=True
            )
        except Exception as error:
            logger.error(f"Error forwarding log: {error}")

    if not update.from_user:
        return await update.reply_text("I don't know about you sar :(")
    
    await AddUser(bot, update)

    if Config.UPDATES_CHANNEL:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return

    url = update.text
    youtube_dl_username = None
    youtube_dl_password = None
    file_name = None

    if "|" in url:
        url_parts = url.split("|")
        if len(url_parts) == 2:
            url = url_parts[0]
            file_name = url_parts[1]
        elif len(url_parts) == 4:
            url = url_parts[0]
            file_name = url_parts[1]
            youtube_dl_username = url_parts[2]
            youtube_dl_password = url_parts[3]

    # Prepare yt-dlp command
    command_to_exec = [
        "yt-dlp",
        "--no-warnings",
        "--allow-dynamic-mpd",
        "--cookies", cookies_file,
        "--no-check-certificate",
        "-j",
        url
    ]
    if Config.HTTP_PROXY != "":
        command_to_exec.append("--proxy")
        command_to_exec.append(Config.HTTP_PROXY)
    else:
        command_to_exec.append("--geo-bypass-country")
        command_to_exec.append("IN")

    if youtube_dl_username:
        command_to_exec.append("--username")
        command_to_exec.append(youtube_dl_username)
    if youtube_dl_password:
        command_to_exec.append("--password")
        command_to_exec.append(youtube_dl_password)

    logger.info(f"Running command: {' '.join(command_to_exec)}")

    chk = await bot.send_message(
        chat_id=update.chat.id,
        text='Processing your link ⌛',
        disable_web_page_preview=True,
        reply_to_message_id=update.id
    )

    # Run yt-dlp command
    process = await asyncio.create_subprocess_exec(
        *command_to_exec,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    e_response = stderr.decode().strip()
    t_response = stdout.decode().strip()

    if e_response:
        error_message = e_response.replace("please report this issue on https://yt-dl.org/bug .", "")
        await chk.delete()
        await bot.send_message(
            chat_id=update.chat.id,
            text=f"Error: {error_message}",
            reply_to_message_id=update.id
        )
        return

    if t_response:
        try:
            response_json = json.loads(t_response)
            randem = random_char(5)
            save_ytdl_json_path = f"{Config.DOWNLOAD_LOCATION}/{update.from_user.id}{randem}.json"
            with open(save_ytdl_json_path, "w", encoding="utf8") as outfile:
                json.dump(response_json, outfile, ensure_ascii=False)

            inline_keyboard = []
            if "formats" in response_json:
                for formats in response_json["formats"]:
                    format_id = formats.get("format_id")
                    format_string = formats.get("format_note") or formats.get("format")
                    if "DASH" in format_string.upper():
                        continue
                    format_ext = formats.get("ext")
                    size = formats.get('filesize') or formats.get('filesize_approx') or 0
                    cb_string = f"video|{format_id}|{format_ext}|{randem}"
                    ikeyboard = [
                        InlineKeyboardButton(f"📁 {format_string} {format_ext} {humanbytes(size)}", callback_data=cb_string.encode("UTF-8"))
                    ]
                    inline_keyboard.append(ikeyboard)

            reply_markup = InlineKeyboardMarkup(inline_keyboard)
            await chk.delete()
            await bot.send_message(
                chat_id=update.chat.id,
                text=f"Please select a format:\n{Translation.SET_CUSTOM_USERNAME_PASSWORD}",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                reply_to_message_id=update.id
            )
        except json.JSONDecodeError:
            await chk.delete()
            await bot.send_message(
                chat_id=update.chat.id,
                text="Failed to parse video details. Please try again later.",
                reply_to_message_id=update.id
  )
