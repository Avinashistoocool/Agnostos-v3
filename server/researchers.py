"""Owner-scoped researcher records; imports never approve or send mail."""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, field_validator
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from .database import engine, researchers

MAX_UPLOAD = 10 * 1024 * 1024
MAX_ROWS = 5000
FIELDS = ("name", "email", "institution", "country", "research_area", "notes")
HEADERS = ("Name", "Email", "Institution", "Country", "Research area", "Notes")
ALIASES = {
    "professor": "name", "professor name": "name", "name": "name",
    "email": "email", "email address": "email", "contact email": "email",
    "institution": "institution", "university": "institution", "affiliation": "institution",
    "country": "country", "research area": "research_area", "research interests": "research_area",
    "notes": "notes",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class ResearcherInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    institution: str = Field("", max_length=300)
    country: str = Field("", max_length=100)
    research_area: str = Field("", max_length=2000)
    notes: str = Field("", max_length=5000)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if isinstance(value, str):
            return value.strip().lower() or None
        return value


class ResearcherEdit(ResearcherInput):
    updated_at: str = Field(min_length=1, max_length=50)


def public(row) -> dict:
    return {key: value for key, value in row.items() if key != "user_id"}


def read_import(raw: bytes) -> list[ResearcherInput]:
    try:
        with ZipFile(BytesIO(raw)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 40 * 1024 * 1024:
                raise HTTPException(413, "Expanded workbook exceeds 40 MB")
        workbook = load_workbook(BytesIO(raw), read_only=True, data_only=True)
        try:
            sheet = workbook.active
            # Do not trust dimensions written by spreadsheet exporters.
            sheet.reset_dimensions()
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, ())
            columns = {}
            for index, value in enumerate(header):
                key = ALIASES.get(str(value or "").strip().lower())
                if key:
                    if key in columns.values():
                        raise HTTPException(422, f"More than one column maps to {key}")
                    columns[index] = key
            if "name" not in columns.values():
                raise HTTPException(422, "First row must contain a Name or Professor name column")
            result = []
            for number, row in enumerate(rows, 2):
                if number > MAX_ROWS + 1:
                    raise HTTPException(413, f"Import supports at most {MAX_ROWS} rows")
                if not any(value is not None and str(value).strip() for value in row):
                    continue
                values = {key: str(row[index]).strip() if index < len(row) and row[index] is not None
                          else "" for index, key in columns.items()}
                try:
                    result.append(ResearcherInput(**values))
                except ValidationError as exc:
                    problem = exc.errors()[0]
                    raise HTTPException(422, f"Row {number}, {problem['loc'][0]}: {problem['msg']}") from None
            if not result:
                raise HTTPException(422, "Workbook contains no researchers")
            return result
        finally:
            workbook.close()
    except (BadZipFile, InvalidFileException, ParseError, KeyError, ValueError, OSError):
        raise HTTPException(422, "Cannot read this workbook; upload a valid .xlsx file") from None


def router(current_user) -> APIRouter:
    api = APIRouter(prefix="/api/researchers", tags=["researchers"])

    @api.get("")
    def list_researchers(q: str = Query("", max_length=200),
                         limit: int = Query(25, ge=1, le=100),
                         offset: int = Query(0, ge=0), user=Depends(current_user)):
        conditions = [researchers.c.user_id == user["id"]]
        if q.strip():
            conditions.append(or_(*(researchers.c[key].icontains(q.strip(), autoescape=True)
                                    for key in ("name", "email", "institution", "research_area"))))
        with engine.connect() as c:
            total = c.scalar(select(func.count()).select_from(researchers).where(*conditions))
            rows = c.execute(select(researchers).where(*conditions).order_by(researchers.c.id.desc())
                             .limit(limit).offset(offset)).mappings().all()
        return {"items": [public(row) for row in rows], "total": total,
                "limit": limit, "offset": offset, "storage": engine.dialect.name}

    @api.post("", status_code=201)
    def create_researcher(body: ResearcherInput, user=Depends(current_user)):
        stamp = now()
        try:
            with engine.begin() as c:
                row = c.execute(insert(researchers).values(
                    **body.model_dump(), user_id=user["id"], created_at=stamp, updated_at=stamp)
                    .returning(*researchers.c)).mappings().one()
        except IntegrityError:
            raise HTTPException(409, "A researcher with this email already exists in your workspace") from None
        return public(row)

    @api.post("/import")
    async def import_researchers(file: UploadFile = File(...), user=Depends(current_user)):
        if not (file.filename or "").lower().endswith(".xlsx"):
            raise HTTPException(422, "Upload an .xlsx workbook")
        raw = await file.read(MAX_UPLOAD + 1)
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "Workbook exceeds 10 MB")
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(import_records, user["id"], raw)

    @api.get("/export")
    def export_researchers(user=Depends(current_user)):
        with engine.connect() as c:
            rows = c.execute(select(researchers).where(researchers.c.user_id == user["id"])
                             .order_by(researchers.c.id).limit(10001)).mappings().all()
        if len(rows) > 10000:
            raise HTTPException(413, "Export supports at most 10,000 records")
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Researchers"
        sheet.append(HEADERS)
        for row in rows:
            sheet.append([row[key] or "" for key in FIELDS])
            # User-controlled values must stay text, not executable Excel formulas.
            for cell in sheet[sheet.max_row]:
                cell.data_type = "s"
        out = BytesIO()
        workbook.save(out)
        workbook.close()
        return Response(out.getvalue(),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="agnostos-researchers.xlsx"'})

    @api.put("/{researcher_id}")
    def edit_researcher(researcher_id: int, body: ResearcherEdit, user=Depends(current_user)):
        try:
            with engine.begin() as c:
                owned = [researchers.c.id == researcher_id, researchers.c.user_id == user["id"]]
                if not c.scalar(select(researchers.c.id).where(*owned)):
                    raise HTTPException(404, "Researcher not found")
                row = c.execute(update(researchers).where(
                    *owned, researchers.c.updated_at == body.updated_at)
                    .values(**body.model_dump(exclude={"updated_at"}), updated_at=now())
                    .returning(*researchers.c)).mappings().first()
                if row is None:
                    raise HTTPException(409, "This record changed in another window; reload before editing")
        except IntegrityError:
            raise HTTPException(409, "A researcher with this email already exists in your workspace") from None
        return public(row)

    @api.delete("/{researcher_id}", status_code=204)
    def delete_researcher(researcher_id: int, updated_at: str = Query(min_length=1, max_length=50),
                          user=Depends(current_user)):
        with engine.begin() as c:
            owned = [researchers.c.id == researcher_id, researchers.c.user_id == user["id"]]
            if not c.scalar(select(researchers.c.id).where(*owned)):
                raise HTTPException(404, "Researcher not found")
            removed = c.execute(delete(researchers).where(
                *owned, researchers.c.updated_at == updated_at))
            if removed.rowcount != 1:
                raise HTTPException(409, "This record changed in another window; reload before deleting")
        return Response(status_code=204)

    return api


def import_records(user_id: int, raw: bytes) -> dict:
    records = read_import(raw)  # Validate the whole workbook before writing anything.
    added = skipped = 0
    with engine.begin() as c:
        existing = c.execute(select(researchers).where(researchers.c.user_id == user_id)).mappings().all()
        emails = {row["email"] for row in existing if row["email"]}
        unnamed = {(row["name"].casefold(), row["institution"].casefold())
                   for row in existing if not row["email"]}
        for record in records:
            identity = (record.name.casefold(), record.institution.casefold())
            if (record.email in emails if record.email else identity in unnamed):
                skipped += 1
                continue
            stamp = now()
            try:
                c.execute(insert(researchers).values(**record.model_dump(), user_id=user_id,
                                                    created_at=stamp, updated_at=stamp))
            except IntegrityError:
                raise HTTPException(409, "Workspace changed during import; retry the workbook") from None
            if record.email:
                emails.add(record.email)
            else:
                unnamed.add(identity)
            added += 1
    return {"imported": added, "skipped": skipped,
            "message": "Existing records were not overwritten. Nothing was approved or sent."}
