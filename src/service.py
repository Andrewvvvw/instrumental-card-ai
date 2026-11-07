from .schemas import ProductInput, ProductCard
from .llm import generate_content
from .errors import GenerationError


MISSING_DATA = "данных нет"


def generate_card(product: ProductInput) -> ProductCard:
    generated = generate_content(product)

    invalid_keys = set(generated.selected_keys) - set(product.specs)
    if invalid_keys:
        raise GenerationError(
            "invalid_llm_response",
            "Модель вернула характеристики, которых нет во входных данных.",
        )

    selected_keys = generated.selected_keys or list(product.specs)
    key_characteristics = {
        key: product.specs[key] or MISSING_DATA
        for key in selected_keys
    }

    missing_fields = []
    if not product.manufacturer or not product.manufacturer.strip():
        missing_fields.append("manufacturer")

    if not product.specs:
        missing_fields.append("specs")

    for key, value in product.specs.items():
        if not value:
            missing_fields.append(f"specs.{key}")
            key_characteristics[key] = MISSING_DATA

    if not product.description or not product.description.strip():
        missing_fields.append("description")

    card = ProductCard(
        **generated.model_dump(exclude={"selected_keys"}),
        key_characteristics=key_characteristics,
        missing_fields=missing_fields,
    )
    return card
