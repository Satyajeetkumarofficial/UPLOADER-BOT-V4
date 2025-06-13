import logging
import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timedelta # Import timedelta
from pyrogram import enums
from pyrogram.types import InputMediaPhoto
from plugins.config import Config
from plugins.script import Translation
from plugins.thumbnail import Gthumb01, Gthumb02 # Assuming these are functions, not just a module
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes
from plugins.functions.metadata import Mdata01, Mdata02, Mdata03
from plugins.database.database import db
from PIL import Image
from plugins.functions.ran_text import random_char

cookies_file = 'cookies.txt'

# Initialize global dictionaries for tracking user activity
uploading_users = {}
cooldown_users = {}

# Set up logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# 🔐 यूजर लॉक और रीयल-टाइम वेट सिस्टम
async def check_user_limit(update):
    user_id = update.from_user.id
    now = datetime.utcnow()

    # 👑 OWNER allowed without restriction
    if user_id == Config.OWNER_ID:
        return True

    # 🧑‍💼 SUDO USERS allowed without cooldown, but with upload lock
    if user_id in Config.SUDO_USERS:
        # Check if sudo user's expiry is still valid
        expiry = Config.SUDO_USERS.get(user_id) # Use .get() for safer access
        if expiry and expiry > now: # Ensure expiry exists and is in the future
            if uploading_users.get(user_id, False):
                await update.message.reply_text(
                    "🚫 कृपया प्रतीक्षा करें...\n📤 आपकी पिछली फ़ाइल अभी अपलोड हो रही है।"
                )
                return False
            return True
        else:
            # Remove expired sudo user entry
            if user_id in Config.SUDO_USERS: # Check before deleting
                del Config.SUDO_USERS[user_id]

    # 🟥 Uploading check (normal user)
    if uploading_users.get(user_id, False):
        await update.message.reply_text(
            "🚫 कृपया प्रतीक्षा करें...\n📤 आपकी पिछली फ़ाइल अभी अपलोड हो रही है।"
        )
        return False

    # ⏳ 3-Min Cooldown for normal users only
    if user_id in cooldown_users:
        wait_until = cooldown_users[user_id]
        remaining = (wait_until - now).total_seconds()
        if remaining > 0:
            await update.message.reply_text(
                f"⏳ कृपया {int(remaining)} सेकंड बाद पुनः प्रयास करें।"
            )
            return False
        else:
            cooldown_users.pop(user_id) # Remove expired cooldown

    return True

async def youtube_dl_call_back(bot, update):
    user_id = update.from_user.id # Define user_id here for consistency and clarity

    if not await check_user_limit(update):
        return

    # Mark user as uploading
    uploading_users[user_id] = True

    cb_data = update.data
    tg_send_type, youtube_dl_format, youtube_dl_ext, ranom = cb_data.split("|")
    random1 = random_char(5) # This random1 is probably for temporary directory, not related to ranom from callback

    save_ytdl_json_path = os.path.join(Config.DOWNLOAD_LOCATION, f"{user_id}{ranom}.json")

    response_json = {}
    try:
        with open(save_ytdl_json_path, "r", encoding="utf8") as f:
            response_json = json.load(f)
    except FileNotFoundError as e:
        logger.error(f"JSON file not found: {e}")
        await update.message.delete()
        uploading_users.pop(user_id, None) # Important: remove user from uploading_users on failure
        return False
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON: {e}")
        await update.message.delete()
        uploading_users.pop(user_id, None) # Important: remove user from uploading_users on failure
        return False

    youtube_dl_url = update.message.reply_to_message.text
    custom_file_name = f"{response_json.get('title', 'Unknown Title')}_{youtube_dl_format}.{youtube_dl_ext}" # Default title if not found
    youtube_dl_username = None
    youtube_dl_password = None

    # More robust URL and custom file name parsing
    url_parts = youtube_dl_url.split("|")
    if len(url_parts) == 2:
        youtube_dl_url, custom_file_name = [part.strip() for part in url_parts]
    elif len(url_parts) == 4:
        youtube_dl_url, custom_file_name, youtube_dl_username, youtube_dl_password = [part.strip() for part in url_parts]
    else:
        # Fallback to entities for URL if no pipe separation or invalid format
        for entity in update.message.reply_to_message.entities:
            if entity.type == "text_link":
                youtube_dl_url = entity.url
                break # Found URL, no need to check other entities
            elif entity.type == "url":
                o = entity.offset
                l = entity.length
                youtube_dl_url = youtube_dl_url[o:o + l]
                break # Found URL, no need to check other entities

    logger.info(f"YouTube URL: {youtube_dl_url}")
    logger.info(f"Custom File Name: {custom_file_name}")

    await update.message.edit_caption(
        caption=Translation.DOWNLOAD_START.format(custom_file_name)
    )

    description = Translation.CUSTOM_CAPTION_UL_FILE
    if "fulltitle" in response_json:
        description = response_json["fulltitle"][0:1021]

    tmp_directory_for_each_user = os.path.join(Config.DOWNLOAD_LOCATION, f"{user_id}{random1}")
    os.makedirs(tmp_directory_for_each_user, exist_ok=True)
    # Ensure download_directory includes the full path including the custom_file_name
    download_directory = os.path.join(tmp_directory_for_each_user, custom_file_name)

    command_to_exec = [
        "yt-dlp",
        "-c",
        "--max-filesize", str(Config.TG_MAX_FILE_SIZE),
        "--embed-subs",
        "-f", f"{youtube_dl_format}+bestaudio/best", # Prefer best quality video and audio
        "--hls-prefer-ffmpeg",
        "--cookies", cookies_file,
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        youtube_dl_url,
        "-o", download_directory # Output file name
    ]

    if tg_send_type == "audio":
        command_to_exec = [
            "yt-dlp",
            "-c",
            "--max-filesize", str(Config.TG_MAX_FILE_SIZE),
            "--extract-audio",
            "--cookies", cookies_file,
            "--audio-format", youtube_dl_ext,
            "--audio-quality", youtube_dl_format,
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            youtube_dl_url,
            "-o", download_directory # Output file name
        ]

    if Config.HTTP_PROXY:
        command_to_exec.extend(["--proxy", Config.HTTP_PROXY])
    if youtube_dl_username:
        command_to_exec.extend(["--username", youtube_dl_username])
    if youtube_dl_password:
        command_to_exec.extend(["--password", youtube_dl_password])

    command_to_exec.append("--no-warnings")

    logger.info(f"Executing yt-dlp command: {command_to_exec}")
    start = datetime.now()

    process = await asyncio.create_subprocess_exec(
        *command_to_exec,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()
    e_response = stderr.decode().strip()
    t_response = stdout.decode().strip()
    logger.info(f"yt-dlp stderr: {e_response}")
    logger.info(f"yt-dlp stdout: {t_response}")

    if process.returncode != 0:
        logger.error(f"yt-dlp command failed with return code {process.returncode}. Error: {e_response}")
        error_message = e_response.replace("**Invalid link !**", "").strip() # Clean up error message
        await update.message.edit_caption(
            caption=f"Error: {error_message if error_message else 'An unknown error occurred during download.'}"
        )
        uploading_users.pop(user_id, None) # Important: remove user from uploading_users on failure
        return False

    # Clean up the JSON file after successful download command
    try:
        os.remove(save_ytdl_json_path)
    except FileNotFoundError:
        pass # Already removed or never existed, fine

    end_one = datetime.now()
    time_taken_for_download = (end_one - start).seconds

    # yt-dlp might change the extension, so find the actual downloaded file
    # This loop is more robust for finding the downloaded file
    downloaded_file_path = None
    for root, _, files in os.walk(tmp_directory_for_each_user):
        for file in files:
            if file.startswith(os.path.splitext(custom_file_name)[0]): # Check if file starts with expected name
                downloaded_file_path = os.path.join(root, file)
                break
        if downloaded_file_path:
            break

    if not downloaded_file_path or not os.path.isfile(downloaded_file_path):
        logger.error(f"Downloaded file not found in {tmp_directory_for_each_user}")
        await update.message.edit_caption(
            caption=Translation.DOWNLOAD_FAILED
        )
        uploading_users.pop(user_id, None) # Important: remove user from uploading_users on failure
        return False

    file_size = os.stat(downloaded_file_path).st_size

    if file_size > Config.TG_MAX_FILE_SIZE:
        await update.message.edit_caption(
            caption=Translation.RCHD_TG_API_LIMIT.format(time_taken_for_download, humanbytes(file_size))
        )
        # Clean up in case of file size limit
        try:
            shutil.rmtree(tmp_directory_for_each_user)
        except Exception as e:
            logger.error(f"Error cleaning up after file size limit: {e}")
        uploading_users.pop(user_id, None) # Important: remove user from uploading_users on failure
        return False
    else:
        await update.message.edit_caption(
            caption=Translation.UPLOAD_START.format(os.path.basename(downloaded_file_path))
        )
        start_time = time.time()
        
        # Initialize thumbnail_to_remove for cleanup
        thumbnail_to_remove = None

        try:
            if tg_send_type == "audio":
                duration = await Mdata03(downloaded_file_path) # Assuming Mdata03 extracts audio duration
                thumbnail_to_remove = await Gthumb01(bot, update) # Gthumb01 for general thumbnail
                await update.message.reply_audio(
                    audio=downloaded_file_path,
                    caption=description,
                    duration=duration,
                    thumb=thumbnail_to_remove,
                    progress=progress_for_pyrogram,
                    progress_args=(
                        Translation.UPLOAD_START,
                        update.message,
                        start_time
                    )
                )
            elif tg_send_type == "vm":
                width, duration = await Mdata02(downloaded_file_path) # Assuming Mdata02 extracts video note data
                thumbnail_to_remove = await Gthumb02(bot, update, duration, downloaded_file_path) # Gthumb02 for video thumbnail
                await update.message.reply_video_note(
                    video_note=downloaded_file_path,
                    duration=duration,
                    length=width,
                    thumb=thumbnail_to_remove,
                    progress=progress_for_pyrogram,
                    progress_args=(
                        Translation.UPLOAD_START,
                        update.message,
                        start_time
                    )
                )
            elif not await db.get_upload_as_doc(user_id): # User wants document upload
                thumbnail_to_remove = await Gthumb01(bot, update)
                await update.message.reply_document(
                    document=downloaded_file_path,
                    thumb=thumbnail_to_remove,
                    caption=description,
                    progress=progress_for_pyrogram,
                    progress_args=(
                        Translation.UPLOAD_START,
                        update.message,
                        start_time
                    )
                )
            else: # User wants video upload (default if not audio/vm/document)
                width, height, duration = await Mdata01(downloaded_file_path) # Assuming Mdata01 extracts video metadata
                thumbnail_to_remove = await Gthumb02(bot, update, duration, downloaded_file_path)
                await update.message.reply_video(
                    video=downloaded_file_path,
                    caption=description,
                    duration=duration,
                    width=width,
                    height=height,
                    supports_streaming=True,
                    thumb=thumbnail_to_remove,
                    progress=progress_for_pyrogram,
                    progress_args=(
                        Translation.UPLOAD_START,
                        update.message,
                        start_time
                    )
                )
            logger.info(f"✅ Successfully uploaded: {os.path.basename(downloaded_file_path)}")

        except Exception as e:
            logger.error(f"Error during upload: {e}")
            await update.message.edit_caption(
                caption=Translation.UPLOAD_FAILED.format(e)
            )
            uploading_users.pop(user_id, None) # Important: remove user from uploading_users on failure
            return False # Exit on upload failure

        end_two = datetime.now()
        time_taken_for_upload = (end_two - end_one).seconds

        # Clean up temporary files
        try:
            shutil.rmtree(tmp_directory_for_each_user)
            if thumbnail_to_remove and os.path.exists(thumbnail_to_remove):
                os.remove(thumbnail_to_remove)
        except Exception as e:
            logger.error(f"Error cleaning up: {e}")

        await update.message.edit_caption(
            caption=Translation.AFTER_SUCCESSFUL_UPLOAD_MSG_WITH_TS.format(time_taken_for_download, time_taken_for_upload)
        )
        
        # Remove user from uploading_users after successful upload
        uploading_users.pop(user_id, None)

        # Apply cooldown for normal users
        if user_id not in Config.SUDO_USERS and user_id != Config.OWNER_ID:
            cooldown_users[user_id] = datetime.utcnow() + timedelta(minutes=3)

        logger.info(f"✅ Downloaded in: {time_taken_for_download} seconds")
        logger.info(f"✅ Uploaded in: {time_taken_for_upload} seconds")

