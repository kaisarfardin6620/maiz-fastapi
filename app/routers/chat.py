import json
import base64
import logging
from typing import List
from bson import ObjectId
from pydantic import BaseModel
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException, File, UploadFile, Form
from app.core.auth import verify_token
from app.core.dependencies import get_current_user
from app.database import get_db
from app.redis_client import redis_client
from app.utils.object_id import doc_to_dict, docs_to_list
from app.utils.response import success_response, APIResponse
from app.models.chat import ChatSessionOut
from app.services.chat_service import (
    get_or_create_session, get_session_by_id, create_session, list_sessions,
    update_session_title, delete_session, auto_title_session_if_needed,
    save_message, save_search_history, process_text_message,
    process_voice_message, process_image_message,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])

class RenameConversationBody(BaseModel):
    title: str

@router.get("/conversations", response_model=APIResponse[List[ChatSessionOut]])
async def get_conversations(
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    sessions = await list_sessions(str(user["_id"]), venue_id=None, limit=limit)
    return success_response(docs_to_list(sessions))

@router.get("/conversations/{conversation_id}", response_model=APIResponse[ChatSessionOut])
async def get_conversation(conversation_id: str, user=Depends(get_current_user)):
    session = await get_session_by_id(str(user["_id"]), conversation_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return success_response(doc_to_dict(session))

@router.get("/conversations/{conversation_id}/messages", response_model=APIResponse[list])
async def get_paginated_messages(
    conversation_id: str, 
    skip: int = Query(0, ge=0), 
    limit: int = Query(50, ge=1, le=100),
    user=Depends(get_current_user)
):
    db = get_db()
    session_obj_id = ObjectId(conversation_id)
    session = await db["chatsessions"].find_one(
        {"_id": session_obj_id, "user": ObjectId(user["_id"])},
        {"messages": {"$slice":[skip, limit]}}
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    return success_response(docs_to_list(session.get("messages",[])))

@router.post("/conversations")
async def create_conversation(
    file: UploadFile = File(...),
    user=Depends(get_current_user)
):
    from app.routers.media import upload_media
    session = await create_session(str(user["_id"]), venue_id=None)
    
    upload_result = await upload_media(file=file, conversation_id=str(session["_id"]), user=user)
    
    return success_response({
        "conversation": doc_to_dict(session),
        "mediaResult": upload_result.get("data")
    }, "Conversation created and media processed")

@router.patch("/conversations/{conversation_id}/title", response_model=APIResponse[ChatSessionOut])
async def rename_conversation(
    conversation_id: str,
    body: RenameConversationBody,
    user=Depends(get_current_user),
):
    updated = await update_session_title(str(user["_id"]), conversation_id, body.title)
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return success_response(doc_to_dict(updated), "Conversation renamed")

@router.delete("/conversations/{conversation_id}")
async def remove_conversation(conversation_id: str, user=Depends(get_current_user)):
    deleted = await delete_session(str(user["_id"]), conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return success_response(message="Conversation deleted")

@router.websocket("/ws")
async def chat_websocket(
    websocket: WebSocket,
    token: str = Query(...),
    conversation_id: str = Query(None),
    conversationId: str = Query(None),
):
    actual_conversation_id = conversationId or conversation_id

    try:
        payload = verify_token(token)
        user_id = payload.get("id") or payload.get("_id") or payload.get("sub")
    except Exception:
        await websocket.close(code=1008, reason="Invalid Token")
        return

    db = get_db()
    try:
        user = await db["users"].find_one({"_id": ObjectId(user_id), "isDeleted": {"$ne": True}})
        if not user or user.get("status") == "blocked":
            await websocket.close(code=1008, reason="User unauthorized or blocked")
            return
    except Exception:
        await websocket.close(code=1008, reason="Invalid User Data")
        return

    await websocket.accept()

    try:
        session = None
        if actual_conversation_id:
            session = await get_session_by_id(user_id, actual_conversation_id)
            if not session:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "conversationId": actual_conversation_id,
                    "message": "Conversation not found",
                }))
                await websocket.close(code=1008)
                return

            await websocket.send_text(json.dumps({
                "type": "conversation_history",
                "conversationId": actual_conversation_id,
                "title": session.get("title", "New Chat"),
                "messages": docs_to_list(session.get("messages", [])),
            }))

        while True:
            try:
                raw = await websocket.receive_text()
                
                try:
                    verify_token(token)
                except Exception:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Session expired"}))
                    await websocket.close(code=1008, reason="Token Expired")
                    return

                rate_limit_key = f"ws_rate_limit:{user_id}"
                requests_count = await redis_client.incr(rate_limit_key)
                if requests_count == 1:
                    await redis_client.expire(rate_limit_key, 60)
                if requests_count > 20:
                    await websocket.send_text(json.dumps({
                        "type": "error", 
                        "message": "Rate limit exceeded. Please slow down."
                    }))
                    continue

                data = json.loads(raw)
                requested_conversation_id = data.get("conversationId")
                start_new = bool(data.get("startNewConversation"))

                if requested_conversation_id:
                    next_session = await get_session_by_id(user_id, requested_conversation_id)
                    if not next_session:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "conversationId": requested_conversation_id,
                            "message": "Conversation not found",
                        }))
                        continue
                    session = next_session

                if start_new or session is None:
                    session = await create_session(user_id, venue_id=None)

                session_id = session["_id"]
                session_id_str = str(session_id)
                await websocket.send_text(json.dumps({
                    "type": "conversation",
                    "conversationId": session_id_str,
                    "title": session.get("title", "New Chat"),
                }))

                input_type = "text"
                user_text = None
                attachment_items =[]
                
                user_gps = data.get("location")

                if data.get("audio"):
                    audio_bytes = base64.b64decode(data["audio"])
                    user_text = await process_voice_message(audio_bytes)
                    input_type = "voice"
                    await websocket.send_text(json.dumps({
                        "type": "transcript",
                        "conversationId": session_id_str,
                        "text": user_text,
                    }))

                elif data.get("imageUrl"):
                    analysis = await process_image_message(
                        data["imageUrl"], context=data.get("text", "")
                    )
                    attachment_items.append({
                        "mediaType": "image",
                        "url": data["imageUrl"],
                        "purpose": "chat",
                    })
                    await websocket.send_text(json.dumps({
                        "type": "image_analysis",
                        "conversationId": session_id_str,
                        "analysis": analysis,
                    }))
                    user_text = data.get("text") or f"[Photo analyzed: {analysis.get('detectedZone', 'unknown zone')}]"
                    input_type = "photo"

                else:
                    user_text = data.get("text", "").strip()
                    if not user_text and not user_gps:
                        continue

                text_to_process = user_text
                if user_gps:
                    lat, lng = user_gps.get("lat"), user_gps.get("lng")
                    if user_text:
                        text_to_process = f"[System Alert: User GPS Location is lat:{lat}, lng:{lng}] User says: {user_text}"
                    else:
                        text_to_process = f"[System Alert: User shared their GPS Location lat:{lat}, lng:{lng}. Find their nearest venue.]"

                was_first_message = len(session.get("messages",[])) == 0
                await save_message(session_id, "user", user_text or "Shared Location",
                                   voice_transcript=user_text if input_type == "voice" else None,
                                   attachments=attachment_items)

                if was_first_message:
                    session = await auto_title_session_if_needed(session, user_text or "Location Search", input_type)
                    await websocket.send_text(json.dumps({
                        "type": "conversation",
                        "conversationId": session_id_str,
                        "title": session.get("title", "New Chat"),
                    }))

                await save_search_history(user_id, user_text or "Location Search", input_type, venue_id=None)

                stream, action_card = await process_text_message(session, text_to_process, user_id, venue_id=None)
                
                full_reply = ""
                buffer = ""
                flushed = False

                if action_card:
                    await websocket.send_text(json.dumps({
                        "type": "action_card",
                        "conversationId": session_id_str,
                        "actionCard": action_card,
                    }))

                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        full_reply += delta
                        
                        if not flushed:
                            buffer += delta
                            if "[NEED_GPS]" in buffer:
                                full_reply = "Please share your location so I can find the nearest venue for you."
                                action_card = {"cardType": "request_location", "ctaLabel": "Share Location"}
                                
                                await websocket.send_text(json.dumps({
                                    "type": "stream",
                                    "conversationId": session_id_str,
                                    "text": full_reply,
                                    "isDone": False,
                                }))
                                break
                            elif len(buffer) > 15:
                                await websocket.send_text(json.dumps({
                                    "type": "stream",
                                    "conversationId": session_id_str,
                                    "text": buffer,
                                    "isDone": False,
                                }))
                                buffer = ""
                                flushed = True
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "stream",
                                "conversationId": session_id_str,
                                "text": delta,
                                "isDone": False,
                            }))

                if full_reply:
                    await save_message(
                        session_id,
                        "assistant",
                        full_reply,
                        action_card=action_card,
                    )

                response_obj = {
                    "type": "stream",
                    "conversationId": session_id_str,
                    "text": "",
                    "isDone": True,
                }
                if action_card:
                    response_obj["actionCard"] = action_card
                
                await websocket.send_text(json.dumps(response_obj))
            except WebSocketDisconnect:
                logger.info("Chat websocket disconnected")
                break
            except Exception:
                logger.exception("Error while processing chat websocket message")
                try:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Unexpected websocket error",
                    }))
                except Exception:
                    pass
                break
    except WebSocketDisconnect:
        logger.info("Chat websocket disconnected")
    except Exception:
        logger.exception("Unhandled chat websocket error")