from pyrogram import Client, filters from pyrogram.types import Message from database.mongo import add_sudo, remove_sudo, get_all_sudos

OWNER ID (replace with your Telegram user ID)

OWNER_ID = 123456789  # ⚠️ इसे अपने असली Telegram ID से बदलें

def is_owner(user_id): return user_id == OWNER_ID

@Client.on_message(filters.command("sudoadd") & filters.user(OWNER_ID)) async def sudo_add(client, message: Message): if len(message.command) != 2: return await message.reply_text("ℹ️ Usage: /sudoadd <user_id>")

try:
    user_id = int(message.command[1])
    await add_sudo(user_id)
    await message.reply_text(f"✅ User `{user_id}` added as SUDO user.")
except Exception as e:
    await message.reply_text(f"❌ Error: {e}")

@Client.on_message(filters.command("sudoremove") & filters.user(OWNER_ID)) async def sudo_remove(client, message: Message): if len(message.command) != 2: return await message.reply_text("ℹ️ Usage: /sudoremove <user_id>")

try:
    user_id = int(message.command[1])
    await remove_sudo(user_id)
    await message.reply_text(f"🗑️ User `{user_id}` removed from SUDO list.")
except Exception as e:
    await message.reply_text(f"❌ Error: {e}")

@Client.on_message(filters.command("sudolist") & filters.user(OWNER_ID)) async def sudo_list(client, message: Message): try: sudos = await get_all_sudos() if not sudos: return await message.reply_text("👨‍💼 No SUDO users added yet.")

text = "👨‍💼 **SUDO Users List:**\n"
    text += "\n".join([f"• `{uid}`" for uid in sudos])
    await message.reply_text(text)
except Exception as e:
    await message.reply_text(f"❌ Error: {e}")

                  
