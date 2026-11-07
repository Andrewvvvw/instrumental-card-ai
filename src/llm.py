import os
from openai import OpenAI
from dotenv import load_dotenv

from prompts import SYSTEM_PROMPT, build_user_prompt
from schemas import ProductInput, LLMGeneratedContent

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

def generate_content(product: ProductInput):
    schema = LLMGeneratedContent.model_json_schema()

    response = client.chat.completions.create(
        model="nvidia/nemotron-3.5-super-vl:free",
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
        extra_body={
            "provider": {
                "require_parameters": True
            }
        },
    )

    content = response.choices[0].message.content

    if not content or not content.strip():
        raise ValueError("LLM returned empty content")

    if response.choices[0].finish_reason == "length":
        raise ValueError("LLM response was truncated")

    return LLMGeneratedContent.model_validate_json(content)