from prisma import Prisma

db = Prisma()


async def connect_db() -> None:
    await db.connect()


async def disconnect_db() -> None:
    await db.disconnect()