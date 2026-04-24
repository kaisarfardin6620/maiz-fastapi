from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED

from app.core.auth import verify_token
from app.database import get_db
from app.mcp.registry import registry
from app.mcp.schemas import JsonRpcError, JsonRpcRequest, JsonRpcResponse
from app.utils.object_id import str_to_objectid

router = APIRouter(prefix="/mcp", tags=["MCP"])

JSON_RPC_INVALID_REQUEST = -32600
JSON_RPC_METHOD_NOT_FOUND = -32601
JSON_RPC_INVALID_PARAMS = -32602
JSON_RPC_INTERNAL_ERROR = -32603


async def _build_context(authorization: Optional[str]) -> dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")

    payload = verify_token(token)
    user_id = payload.get("id") or payload.get("_id") or payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        object_id = str_to_objectid(str(user_id))
    except ValueError:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    db = get_db()
    user = await db["users"].find_one({"_id": object_id, "isDeleted": {"$ne": True}})
    if not user:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="User not found")

    if user.get("status") == "blocked":
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Account is blocked")

    return {"user": user}


@router.get("/")
async def mcp_index():
    return {
        "name": "Maiz MCP",
        "version": "1.0.0",
        "transport": "json-rpc-http",
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False,
        },
    }


@router.get("/tools")
async def list_tools(authorization: Optional[str] = Header(default=None)):
    await _build_context(authorization)
    return {"tools": registry.list_tools()}


@router.post("/")
async def handle_mcp(request: Request, authorization: Optional[str] = Header(default=None)):
    context = await _build_context(authorization)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            JsonRpcResponse(
                id=None,
                error=JsonRpcError(code=JSON_RPC_INVALID_REQUEST, message="Invalid JSON body"),
            ).model_dump(exclude_none=True),
            status_code=200,
        )

    if isinstance(body, list):
        responses = []
        for item in body:
            response = await _handle_rpc_item(item, context)
            if response is not None:
                responses.append(response.model_dump(exclude_none=True))
        return JSONResponse(responses)

    response = await _handle_rpc_item(body, context)
    if response is None:
        return JSONResponse(status_code=204, content=None)
    return JSONResponse(response.model_dump(exclude_none=True))


async def _handle_rpc_item(payload: dict[str, Any], context: dict[str, Any]) -> Optional[JsonRpcResponse]:
    try:
        request = JsonRpcRequest.model_validate(payload)
    except Exception:
        return JsonRpcResponse(
            id=payload.get("id") if isinstance(payload, dict) else None,
            error=JsonRpcError(code=JSON_RPC_INVALID_REQUEST, message="Invalid JSON-RPC request"),
        )

    if request.method == "initialize":
        return JsonRpcResponse(
            id=request.id,
            result={
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "Maiz MCP", "version": "1.0.0"},
                "capabilities": {
                    "tools": {},
                },
            },
        )

    if request.method == "tools/list":
        return JsonRpcResponse(id=request.id, result={"tools": registry.list_tools()})

    if request.method == "tools/call":
        params = request.params or {}
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if not tool_name:
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(code=JSON_RPC_INVALID_PARAMS, message="Missing tool name"),
            )

        try:
            handler = registry.get_handler(tool_name)
        except LookupError as exc:
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(code=JSON_RPC_METHOD_NOT_FOUND, message=str(exc)),
            )

        try:
            result = await handler(arguments, context)
        except ValueError as exc:
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(code=JSON_RPC_INVALID_PARAMS, message=str(exc)),
            )
        except HTTPException as exc:
            status_code = getattr(exc, "status_code", HTTP_400_BAD_REQUEST)
            if status_code in (HTTP_400_BAD_REQUEST, 404):
                error_code = JSON_RPC_INVALID_PARAMS
            elif status_code == HTTP_401_UNAUTHORIZED:
                error_code = HTTP_401_UNAUTHORIZED
            else:
                error_code = JSON_RPC_INTERNAL_ERROR
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(code=error_code, message=str(exc.detail)),
            )
        except Exception as exc:
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(code=JSON_RPC_INTERNAL_ERROR, message="Tool execution failed", data={"detail": str(exc)}),
            )

        return JsonRpcResponse(
            id=request.id,
            result={
                "content": [{"type": "text", "text": _serialize_tool_result(result)}],
                "isError": False,
            },
        )

    if request.method == "ping":
        return JsonRpcResponse(id=request.id, result={"ok": True})

    return JsonRpcResponse(
        id=request.id,
        error=JsonRpcError(code=JSON_RPC_METHOD_NOT_FOUND, message=f"Unsupported method: {request.method}"),
    )


def _serialize_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list, tuple)):
        import json

        return json.dumps(result, default=str, ensure_ascii=False)
    return str(result)
