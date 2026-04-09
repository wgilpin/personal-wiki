"""Pydantic models for structured API output."""

from pydantic import BaseModel


class Snapshot(BaseModel):
    path: str
    content: str


class ProjectSummary(BaseModel):
    path: str
    updated_content: str


class ThemeUpdate(BaseModel):
    path: str
    updated_content: str


class PendingItem(BaseModel):
    action: str
    project: str
    date_captured: str
    source_meeting: str


class PeopleUpdate(BaseModel):
    path: str
    updated_content: str


class IndexUpdate(BaseModel):
    path: str
    one_line_summary: str


class WikiOutput(BaseModel):
    snapshots: list[Snapshot] = []
    project_summaries: list[ProjectSummary] = []
    theme_updates: list[ThemeUpdate] = []
    pending_bill: list[PendingItem] = []
    people_updates: list[PeopleUpdate] = []
    index_updates: list[IndexUpdate] = []


class PathList(BaseModel):
    paths: list[str]
