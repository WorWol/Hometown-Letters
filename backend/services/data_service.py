"""统一处理业务数据删除和派生计数。"""
from __future__ import annotations

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import storage
from services.storage_tasks import add_task as add_storage_task
from db.models import Hometown, Letter, LetterLike, LetterMemory, LetterSummary, Mail, Memory, PastSelfProfile, Postcard, Profile, SystemEvent, User


def postcard_keys(row: Postcard) -> dict[str, str]:
    return {
        "thumb": row.image_thumb_key,
        "card": row.image_card_key,
        "original": row.image_original_key,
        "reference": row.reference_image_key,
    }


async def recalculate_postcard_count(db: AsyncSession, user_id: int) -> int:
    total = await db.scalar(select(func.count(Postcard.id)).where(Postcard.user_id == user_id)) or 0
    await db.execute(update(User).where(User.id == user_id).values(postcard_count=total))
    return total


async def delete_postcard(db: AsyncSession, row: Postcard, *, update_count: bool = True) -> None:
    keys = postcard_keys(row)
    try:
        await storage.delete_images(keys)
    except Exception as error:
        await add_storage_task(db, "postcard", row.id, keys, error)
    await db.execute(update(Mail).where(Mail.attached_postcard_id == row.id).values(attached_postcard_id=None))
    await db.delete(row)
    if update_count:
        await db.execute(update(User).where(User.id == row.user_id, User.postcard_count > 0).values(postcard_count=User.postcard_count - 1))


async def delete_letter(db: AsyncSession, row: Letter) -> None:
    await db.execute(update(Mail).where(Mail.attached_letter_id == row.id).values(attached_letter_id=None))
    await db.execute(delete(LetterLike).where(LetterLike.letter_id == row.id))
    summaries = (await db.scalars(select(LetterSummary).where(or_(LetterSummary.start_letter_id == row.id, LetterSummary.end_letter_id == row.id)))).all()
    summary_ids = [summary.id for summary in summaries]
    if summary_ids:
        await db.execute(delete(LetterMemory).where(LetterMemory.summary_id.in_(summary_ids)))
        await db.execute(delete(LetterSummary).where(LetterSummary.id.in_(summary_ids)))
    await db.delete(row)


async def delete_user(db: AsyncSession, row: User) -> None:
    postcards = (await db.scalars(select(Postcard).where(Postcard.user_id == row.id))).all()
    for postcard in postcards:
        keys = postcard_keys(postcard)
        try:
            await storage.delete_images(keys)
        except Exception as error:
            await add_storage_task(db, "postcard", postcard.id, keys, error)
    postcard_ids = [postcard.id for postcard in postcards]
    letters = (await db.scalars(select(Letter).where(Letter.user_id == row.id))).all()
    letter_ids = [letter.id for letter in letters]

    await db.execute(update(Mail).where(or_(Mail.sender_id == row.id, Mail.recipient_id == row.id)).values(attached_postcard_id=None, attached_letter_id=None))
    if postcard_ids:
        await db.execute(update(Mail).where(Mail.attached_postcard_id.in_(postcard_ids)).values(attached_postcard_id=None))
    if letter_ids:
        await db.execute(update(Mail).where(Mail.attached_letter_id.in_(letter_ids)).values(attached_letter_id=None))
        await db.execute(delete(LetterLike).where(LetterLike.letter_id.in_(letter_ids)))
        summary_ids = [summary.id for summary in (await db.scalars(select(LetterSummary).where(or_(LetterSummary.user_id == row.id, LetterSummary.start_letter_id.in_(letter_ids), LetterSummary.end_letter_id.in_(letter_ids))))).all()]
        if summary_ids:
            await db.execute(delete(LetterMemory).where(LetterMemory.summary_id.in_(summary_ids)))
            await db.execute(delete(LetterSummary).where(LetterSummary.id.in_(summary_ids)))
        await db.execute(delete(Letter).where(Letter.id.in_(letter_ids)))

    await db.execute(delete(Mail).where(or_(Mail.sender_id == row.id, Mail.recipient_id == row.id)))
    for model, column in (
        (LetterLike, LetterLike.user_id), (LetterMemory, LetterMemory.user_id),
        (LetterSummary, LetterSummary.user_id), (Memory, Memory.user_id),
        (PastSelfProfile, PastSelfProfile.user_id), (Profile, Profile.user_id),
        (Hometown, Hometown.user_id), (Postcard, Postcard.user_id),
    ):
        await db.execute(delete(model).where(column == row.id))
    await db.execute(update(SystemEvent).where(SystemEvent.user_id == row.id).values(user_id=None))
    await db.delete(row)
