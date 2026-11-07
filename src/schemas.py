from typing import Annotated

from pydantic import BaseModel, Field, ConfigDict, StringConstraints, field_validator


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ProductInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: NonEmptyString
    manufacturer: str | None = None
    specs: dict[NonEmptyString, str] = Field(default_factory=dict)
    description: str | None = None

    @field_validator("manufacturer", "description")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value or None


class ProductCard(BaseModel):
    seo_title: str = Field(max_length=70)
    seo_description: str = Field(min_length=800, max_length=1200)
    key_characteristics: dict[str, str]
    search_queries: list[str] = Field(min_length=3, max_length=5)
    commercial_block: str
    missing_fields: list[str] = Field(default_factory=list)


class LLMGeneratedContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seo_title: str = Field(max_length=70)
    seo_description: str = Field(min_length=800, max_length=1200)
    search_queries: list[str] = Field(min_length=3, max_length=5)
    commercial_block: str
    selected_keys: list[str]
