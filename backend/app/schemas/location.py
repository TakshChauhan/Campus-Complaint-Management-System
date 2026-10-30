"""Canonical hostel -> wing -> floor tree (API contract 7.1/7.2)."""

from typing import List

from pydantic import BaseModel


class FloorNode(BaseModel):
    id: int
    code: str
    name: str


class WingNode(BaseModel):
    id: int
    code: str
    name: str
    floors: List[FloorNode]


class HostelNode(BaseModel):
    id: int
    code: str
    name: str
    wings: List[WingNode]
