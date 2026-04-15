from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


JsonRpcVersion = Literal["2.0"]


class JsonRpcRequest(BaseModel):
    jsonrpc: JsonRpcVersion = Field(default="2.0")
    id: Optional[Union[str, int]] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class JsonRpcResponse(BaseModel):
    jsonrpc: JsonRpcVersion = Field(default="2.0")
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None


class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ToolSchema(BaseModel):
    type: Literal["object"] = "object"
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: List[str] = Field(default_factory=list)
    additionalProperties: Optional[bool] = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    inputSchema: ToolSchema