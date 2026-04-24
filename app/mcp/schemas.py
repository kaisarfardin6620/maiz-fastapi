from __future__ import annotations

from enum import Enum
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
    additionalProperties: bool = False


class ToolDefinition(BaseModel):
    name: str
    description: str
    inputSchema: ToolSchema


class McpCallArguments(BaseModel):
    arguments: Dict[str, Any] = Field(default_factory=dict)


class McpRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class McpToolCallResult(BaseModel):
    content: List[TextContent] = Field(default_factory=list)
    isError: bool = False
