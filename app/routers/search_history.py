from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.search_history import SearchHistoryGrouped
from app.utils.object_id import docs_to_list, str_to_objectid
from app.utils.response import success_response, APIResponse

router = APIRouter(prefix="/history", tags=["Search History"])


@router.get("/", response_model=APIResponse[SearchHistoryGrouped])
async def get_search_history(user=Depends(get_current_user)):
    db = get_db()
    user_id = ObjectId(user["_id"])
    now = datetime.now(timezone.utc)

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    cursor = db["searchhistories"].find(
        {"user": user_id, "isDeleted": {"$ne": True}},
        sort=[("searchedAt", -1)],
        limit=100,
    )
    all_items = await cursor.to_list(length=100)

    today, last_week, last_month = [],[],[]
    for item in all_items:
        searched_at = item.get("searchedAt")
        if not searched_at:
            continue
        if searched_at.tzinfo is None:
            searched_at = searched_at.replace(tzinfo=timezone.utc)

        if searched_at >= today_start:
            today.append(item)
        elif searched_at >= week_start:
            last_week.append(item)
        elif searched_at >= month_start:
            last_month.append(item)

    return success_response({
        "today": docs_to_list(today),
        "lastWeek": docs_to_list(last_week),
        "lastMonth": docs_to_list(last_month),
    })


@router.delete("/{history_id}")
async def delete_history_item(history_id: str, user=Depends(get_current_user)):
    db = get_db()
    try:
        history_obj_id = str_to_objectid(history_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db["searchhistories"].update_one(
        {"_id": history_obj_id, "user": ObjectId(user["_id"])} ,
        {"$set": {"isDeleted": True}},
    )
    return success_response(message="Deleted")