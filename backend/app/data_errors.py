from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class DataErrorDetail:
    code: str
    message: str
    hint: str
    paper_id: str | None = None

    def as_detail(self) -> dict[str, str]:
        payload = {"code": self.code, "message": self.message, "hint": self.hint}
        if self.paper_id:
            payload["paper_id"] = self.paper_id
        return payload


class DataServiceError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, hint: str, paper_id: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = DataErrorDetail(code=code, message=message, hint=hint, paper_id=paper_id)


def data_http_exception(error: DataServiceError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail.as_detail())
