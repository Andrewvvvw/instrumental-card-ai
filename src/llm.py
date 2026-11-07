import os

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from dotenv import load_dotenv
from pydantic import ValidationError

from .errors import GenerationError
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schemas import ProductInput, LLMGeneratedContent

load_dotenv()


def generate_content(product: ProductInput) -> LLMGeneratedContent:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise GenerationError(
            "configuration_error",
            "Не задан OPENROUTER_API_KEY. Добавьте ключ в переменные окружения или .env.",
        )

    model = os.getenv("OPENROUTER_MODEL", "").strip()
    if not model:
        raise GenerationError(
            "configuration_error",
            "Не задан OPENROUTER_MODEL. Укажите модель в переменных окружения или .env.",
        )

    schema = LLMGeneratedContent.model_json_schema()

    try:
        with OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=60.0,
            max_retries=0,
        ) as client:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(product)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "generated_content",
                        "strict": True,
                        "schema": schema,
                    },
                },
                extra_body={"provider": {"require_parameters": True}},
            )
    except APITimeoutError as exc:
        raise GenerationError(
            "provider_timeout", "Провайдер LLM не ответил вовремя. Попробуйте позже.",
        ) from exc
    except RateLimitError as exc:
        raise GenerationError(
            "provider_rate_limit", "Достигнут лимит запросов к LLM. Попробуйте позже.",
        ) from exc
    except (AuthenticationError, PermissionDeniedError) as exc:
        raise GenerationError(
            "provider_authentication",
            "Провайдер LLM отклонил доступ. Проверьте API-ключ и права доступа к модели.",
        ) from exc
    except APIConnectionError as exc:
        raise GenerationError(
            "provider_unavailable", "Не удалось подключиться к провайдеру LLM.",
        ) from exc
    except APIStatusError as exc:
        if exc.status_code >= 500:
            raise GenerationError(
                "provider_unavailable", "Провайдер LLM временно недоступен.",
            ) from exc
        raise GenerationError(
            "provider_error", "Провайдер LLM отклонил запрос. Проверьте настройки модели.",
        ) from exc
    except APIError as exc:
        raise GenerationError(
            "provider_error", "Не удалось получить корректный ответ от провайдера LLM.",
        ) from exc

    if not response.choices:
        raise GenerationError("invalid_llm_response", "Провайдер LLM вернул пустой ответ.")

    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise GenerationError("invalid_llm_response", "Ответ модели обрезан и непригоден для карточки.")

    if choice.message.refusal:
        raise GenerationError("invalid_llm_response", "Модель отказалась сформировать карточку.")

    content = choice.message.content

    if not content or not content.strip():
        raise GenerationError("invalid_llm_response", "Модель вернула пустое содержимое ответа.")

    try:
        return LLMGeneratedContent.model_validate_json(content)
    except ValidationError as exc:
        raise GenerationError(
            "invalid_llm_response", "Ответ модели не соответствует формату карточки товара.",
        ) from exc
