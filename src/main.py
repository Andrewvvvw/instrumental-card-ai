from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .errors import GenerationError
from .schemas import ProductInput, ProductCard
from .service import generate_card


SOURCE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Instrument Card AI",
    description="Генерация B2B-карточек измерительных приборов",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=SOURCE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(SOURCE_DIR / "static" / "index.html")


@app.exception_handler(GenerationError)
async def handle_generation_error(request: Request, exc: GenerationError) -> JSONResponse:
    status_codes = {
        "configuration_error": 503,
        "provider_authentication": 503,
        "provider_timeout": 504,
        "provider_rate_limit": 429,
        "provider_unavailable": 503,
        "provider_error": 502,
        "invalid_llm_response": 502,
    }
    return JSONResponse(
        status_code=status_codes.get(exc.code, 502),
        content={"detail": {"code": exc.code, "message": str(exc)}},
    )


@app.post("/generate", response_model=ProductCard)
def generate_product_card(product: ProductInput) -> ProductCard:
    return generate_card(product)
