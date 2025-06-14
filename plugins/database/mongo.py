import motor.motor_asyncio
import os

# Get MongoDB URL from environment or config
MONGO_URL = os.environ.get("MONGO_URL")

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = client['uploader_bot']  # database name
sudos_col = db['sudos']  # collection to store sudo users

async def add_sudo(user_id: int):
    if not await sudos_col.find_one({"user_id": user_id}):
        await sudos_col.insert_one({"user_id": user_id})

async def remove_sudo(user_id: int):
    await sudos_col.delete_one({"user_id": user_id})

async def is_sudo(user_id: int) -> bool:
    return await sudos_col.find_one({"user_id": user_id}) is not None

async def get_all_sudos() -> list:
    sudos = await sudos_col.find().to_list(length=100)
    return [entry["user_id"] for entry in sudos]
