import json
import base64
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from app.core.auth import verify_token
from app.services.chat_service import (
    get_or_create_session,
    save_message,
    save_search_history,
    process_text_message,
    process_voice_message,
    process_image_message,
)

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.websocket("/ws")
async def chat_websocket(
    websocket: WebSocket,
    token: str = Query(...),
    venue_id: str = Query(None),
):
    try:
        payload = verify_token(token)
        user_id = payload.get("id") or payload.get("_id") or payload.get("sub")
    except Exception:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    try:
        session = await get_or_create_session(user_id, venue_id)
        session_id = session["_id"]

        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            input_type = "text"
            user_text = None

            if data.get("audio"):
                audio_bytes = base64.b64decode(data["audio"])
                user_text = await process_voice_message(audio_bytes)
                input_type = "voice"
                await websocket.send_text(json.dumps({
                    "type": "transcript",
                    "text": user_text,
                }))

            elif data.get("imageUrl"):
                analysis = await process_image_message(
                    data["imageUrl"], context=data.get("text", "")
                )
                await websocket.send_text(json.dumps({
                    "type": "image_analysis",
                    "analysis": analysis,
                }))
                user_text = data.get("text") or f"[Photo analyzed: {analysis.get('detectedZone', 'unknown zone')}]"
                input_type = "photo"

            else:
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue

            await save_message(session_id, "user", user_text,
                               voice_transcript=user_text if input_type == "voice" else None)

            await save_search_history(user_id, user_text, input_type, venue_id)

            stream = await process_text_message(session, user_text, user_id, venue_id)
            full_reply = ""

            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_reply += delta
                    await websocket.send_text(json.dumps({
                        "type": "stream",
                        "text": delta,
                        "isDone": False,
                    }))

            await websocket.send_text(json.dumps({
                "type": "stream",
                "text": "",
                "isDone": True,
            }))

            await save_message(session_id, "assistant", full_reply)

            session = await get_or_create_session(user_id, venue_id)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        await websocket.close()