from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.local_scope import LOCAL_USER_ID, LOCAL_WORKSPACE_ID, seed_local_scope
from app.models import BrandDNA

router = APIRouter(prefix="/brand", tags=["brand"])


class BrandValues(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    audience: str = Field(default="", max_length=5000)
    positioning: str = Field(default="", max_length=5000)
    voice: str = Field(default="", max_length=5000)
    guidelines: str = Field(default="", max_length=10000)
    prohibited_claims: str = Field(default="", max_length=10000)


class BrandInput(BrandValues):
    version: int = Field(ge=0)


class BrandOutput(BrandValues):
    model_config = ConfigDict(from_attributes=True)
    version: int


def get_session():
    with SessionLocal.begin() as session:
        yield session


def local_only():
    if get_settings().environment != "development":
        raise HTTPException(503, "Authentication must be configured before using this workspace.")


SessionDependency = Annotated[Session, Depends(get_session)]
ScopeDependency = Depends(local_only)


@router.get("", response_model=BrandOutput | None, dependencies=[ScopeDependency])
def get_brand(session: SessionDependency):
    return session.scalar(
        select(BrandDNA).where(
            BrandDNA.workspace_id == LOCAL_WORKSPACE_ID,
            BrandDNA.user_id == LOCAL_USER_ID,
        )
    )


@router.put("", response_model=BrandOutput, dependencies=[ScopeDependency])
def save_brand(payload: BrandInput, session: SessionDependency):
    seed_local_scope(session)
    values = payload.model_dump(exclude={"version"})
    if payload.version == 0:
        statement = (
            insert(BrandDNA)
            .values(
                **values,
                user_id=LOCAL_USER_ID,
                workspace_id=LOCAL_WORKSPACE_ID,
                version=1,
            )
            .on_conflict_do_nothing(index_elements=[BrandDNA.workspace_id])
            .returning(BrandDNA)
        )
        brand = session.scalar(statement)
    else:
        update_statement = (
            update(BrandDNA)
            .where(
                BrandDNA.workspace_id == LOCAL_WORKSPACE_ID,
                BrandDNA.user_id == LOCAL_USER_ID,
                BrandDNA.version == payload.version,
            )
            .values(**values, version=BrandDNA.version + 1)
            .returning(BrandDNA)
        )
        brand = session.scalar(update_statement)
    if brand is None:
        raise HTTPException(409, "The brand profile changed. Reload before saving again.")
    return brand
