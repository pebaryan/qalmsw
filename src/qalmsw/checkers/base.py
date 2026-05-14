"""Shared types for all checkers.

Every checker produces `Finding`s with the same shape, so downstream report/CI code
can consume them uniformly regardless of which checker emitted them.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field

from qalmsw.document import Document


class Severity(StrEnum):
    info = "info"
    warning = "warning"
    error = "error"


class Finding(BaseModel):
    checker: str
    severity: Severity
    line: int
    message: str
    suggestion: str | None = None
    excerpt: str | None = Field(default=None, description="Short source snippet this refers to")
    file: str | None = Field(
        default=None,
        description="Source file if different from the document being checked (e.g. a .bib)",
    )


class Checker(Protocol):
    name: str

    def check(self, doc: Document) -> list[Finding]: ...
