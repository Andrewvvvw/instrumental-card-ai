from pydantic import BaseModel, Field

class ProductInput(BaseModel):
    name: str = Field(min_length=1)
    manufacturer: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    description: str | None = None

class ProductCard(BaseModel):
    seo_title: str = Field(max_length=70)
    seo_description: str = Field(min_length=800, max_length=1200)
    key_characteristics: dict[str, str]
    search_queries: list[str] = Field(min_length=3, max_length=5)
    commercial_block: str
    missing_fields: list[str] = Field(default_factory=list)