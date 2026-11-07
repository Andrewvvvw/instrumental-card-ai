import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from src.errors import GenerationError
from src.llm import generate_content
from src.main import app
from src.schemas import LLMGeneratedContent, ProductInput
from src.service import generate_card


def generated_content(selected_keys=None):
    return LLMGeneratedContent(
        seo_title="Манометр",
        seo_description="Описание прибора. " * 50,
        search_queries=["манометр", "манометр для измерений", "прибор давления"],
        commercial_block="Для измерения давления.",
        selected_keys=[] if selected_keys is None else selected_keys,
    )


def completion(content, *, finish_reason="stop", refusal=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason=finish_reason,
        message=SimpleNamespace(content=content, refusal=refusal),
    )])


def status_error(error_type, status):
    response = Mock(status_code=status, request=Mock(), headers={})
    return error_type("private provider error", response=response, body=None)


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Network disabled")))
        self.enterContext(patch.dict("os.environ", {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_MODEL": "test-model",
        }))
        self.sdk = self.enterContext(patch("src.llm.OpenAI"))
        self.create = self.sdk.return_value.__enter__.return_value.chat.completions.create
        self.create.return_value = completion(generated_content().model_dump_json())
        self.product = ProductInput(name="Манометр", specs={"диапазон": "0–1,6 МПа"})


class InputTests(OfflineTestCase):
    def test_trim_text_and_specifications(self):
        product = ProductInput(
            name="  Манометр  ", manufacturer="  Завод  ",
            description="  Описание  ", specs={" диапазон ": " 0–1,6 МПа "},
        )
        self.assertEqual(product.name, "Манометр")
        self.assertEqual(product.manufacturer, "Завод")
        self.assertEqual(product.description, "Описание")
        self.assertEqual(product.specs, {"диапазон": "0–1,6 МПа"})

    def test_optional_whitespace_becomes_none(self):
        product = ProductInput(name="Манометр", manufacturer=" \t", description=" \n")
        self.assertIsNone(product.manufacturer)
        self.assertIsNone(product.description)

    def test_blank_spec_value_is_retained_as_missing(self):
        product = ProductInput(name="Манометр", specs={"питание": " \t"})
        self.assertEqual(product.specs, {"питание": ""})

    def test_invalid_input_is_rejected(self):
        for data in (
            {}, {"name": ""}, {"name": " \t\n"},
            {"name": "Манометр", "specs": {"": "значение"}},
            {"name": "Манометр", "specs": {" \t": "значение"}},
            {"name": "Манометр", "specs": {"питание": None}},
            {"name": "Манометр", "specs": {"питание": 12}},
            {"name": "Манометр", "specs": []},
        ):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                ProductInput.model_validate(data)
        self.sdk.assert_not_called()


class ServiceTests(OfflineTestCase):
    def test_empty_selection_falls_back_to_all_input_specs(self):
        with patch("src.service.generate_content", return_value=generated_content()):
            card = generate_card(self.product)
        self.assertEqual(card.key_characteristics, self.product.specs)

    def test_selected_values_are_copied_from_input(self):
        product = ProductInput(name="Манометр", specs={"диапазон": "0–1,6 МПа", "класс": "1,5"})
        with patch("src.service.generate_content", return_value=generated_content(["класс"])):
            card = generate_card(product)
        self.assertEqual(card.key_characteristics, {"класс": "1,5"})

    def test_unknown_selected_key_is_rejected(self):
        with patch("src.service.generate_content", return_value=generated_content(["выдуманный ключ"])):
            with self.assertRaises(GenerationError) as caught:
                generate_card(self.product)
        self.assertEqual(caught.exception.code, "invalid_llm_response")

    def test_missing_values_are_reported_even_when_not_selected(self):
        product = ProductInput(
            name="Манометр", manufacturer=" ", description=" ",
            specs={"диапазон": "0–1,6 МПа", "питание": " "},
        )
        original = product.model_dump()
        with patch("src.service.generate_content", return_value=generated_content(["диапазон"])):
            card = generate_card(product)
        self.assertEqual(card.key_characteristics, {"диапазон": "0–1,6 МПа", "питание": "данных нет"})
        self.assertEqual(card.missing_fields, ["manufacturer", "specs.питание", "description"])
        self.assertEqual(product.model_dump(), original)

    def test_empty_specs_are_reported(self):
        with patch("src.service.generate_content", return_value=generated_content()):
            card = generate_card(ProductInput(name="Манометр"))
        self.assertEqual(card.key_characteristics, {})
        self.assertEqual(card.missing_fields, ["manufacturer", "specs", "description"])

    def test_complete_input_has_no_missing_fields(self):
        product = ProductInput(
            name="Манометр", manufacturer="Завод", description="Описание",
            specs={"диапазон": "0–1,6 МПа"},
        )
        with patch("src.service.generate_content", return_value=generated_content()):
            card = generate_card(product)
        self.assertEqual(card.missing_fields, [])


class LLMTests(OfflineTestCase):
    def test_valid_response_and_single_request_without_retries(self):
        result = generate_content(self.product)
        self.assertIsInstance(result, LLMGeneratedContent)
        self.sdk.assert_called_once_with(
            base_url="https://openrouter.ai/api/v1", api_key="test-key",
            timeout=60.0, max_retries=0,
        )
        self.create.assert_called_once()
        self.assertEqual(self.create.call_args.kwargs["model"], "test-model")
        user_prompt = self.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn("Манометр", user_prompt)
        self.assertIn("0–1,6 МПа", user_prompt)
        self.sdk.return_value.__exit__.assert_called_once()

    def test_missing_api_key_does_not_create_client(self):
        for key in ("", " \t"):
            with self.subTest(key=key), patch.dict("os.environ", {"OPENROUTER_API_KEY": key}):
                with self.assertRaises(GenerationError) as caught:
                    generate_content(self.product)
                self.assertEqual(caught.exception.code, "configuration_error")
        self.sdk.assert_not_called()

    def test_missing_model_does_not_create_client(self):
        for model in ("", " \t"):
            with self.subTest(model=model), patch.dict("os.environ", {"OPENROUTER_MODEL": model}):
                with self.assertRaises(GenerationError) as caught:
                    generate_content(self.product)
                self.assertEqual(caught.exception.code, "configuration_error")
        self.sdk.assert_not_called()

    def test_provider_errors_are_translated_without_leaking_details(self):
        cases = (
            (APITimeoutError(request=Mock()), "provider_timeout"),
            (APIConnectionError(request=Mock()), "provider_unavailable"),
            (status_error(RateLimitError, 429), "provider_rate_limit"),
            (status_error(AuthenticationError, 401), "provider_authentication"),
            (status_error(PermissionDeniedError, 403), "provider_authentication"),
            (status_error(APIStatusError, 503), "provider_unavailable"),
            (status_error(APIStatusError, 400), "provider_error"),
            (APIError("private provider error", request=Mock(), body=None), "provider_error"),
        )
        for error, code in cases:
            with self.subTest(error=type(error).__name__, code=code):
                self.create.reset_mock()
                self.create.side_effect = error
                with self.assertRaises(GenerationError) as caught:
                    generate_content(self.product)
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("private provider error", str(caught.exception))
                self.create.assert_called_once()

    def test_empty_truncated_and_refused_responses_are_rejected(self):
        cases = (
            SimpleNamespace(choices=[]),
            completion(None), completion(""), completion(" \n"),
            completion("{}", finish_reason="length"),
            completion(None, refusal="private refusal detail"),
        )
        for response in cases:
            with self.subTest(response=response):
                self.create.return_value = response
                with self.assertRaises(GenerationError) as caught:
                    generate_content(self.product)
                self.assertEqual(caught.exception.code, "invalid_llm_response")

    def test_invalid_json_and_invalid_schema_are_rejected(self):
        valid = generated_content().model_dump()
        for content in (
            "not JSON", "null", "[]", "{}",
            json.dumps({**valid, "seo_title": "x" * 71}),
            json.dumps({**valid, "seo_description": "слишком коротко"}),
            json.dumps({**valid, "search_queries": []}),
            json.dumps({**valid, "unexpected": "field"}),
        ):
            with self.subTest(content=content):
                self.create.return_value = completion(content)
                with self.assertRaises(GenerationError) as caught:
                    generate_content(self.product)
                self.assertEqual(caught.exception.code, "invalid_llm_response")


class APITests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.http = self.enterContext(TestClient(app))

    def test_successful_request_with_incomplete_data(self):
        response = self.http.post("/generate", json={"name": "Манометр", "specs": {"питание": " "}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["key_characteristics"], {"питание": "данных нет"})
        self.assertIn("specs.питание", response.json()["missing_fields"])
        self.create.assert_called_once()

    def test_invalid_json_does_not_call_llm(self):
        response = self.http.post("/generate", content='{"name":', headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422)
        self.sdk.assert_not_called()

    def test_invalid_fields_do_not_call_llm(self):
        for data in ({"name": " "}, {"name": "Манометр", "specs": {" ": "12 В"}}, {"name": 42}):
            with self.subTest(data=data):
                response = self.http.post("/generate", json=data)
                self.assertEqual(response.status_code, 422)
        self.sdk.assert_not_called()

    def test_upstream_failures_have_expected_http_status(self):
        cases = (
            (APITimeoutError(request=Mock()), 504, "provider_timeout"),
            (APIConnectionError(request=Mock()), 503, "provider_unavailable"),
            (status_error(RateLimitError, 429), 429, "provider_rate_limit"),
            (status_error(AuthenticationError, 401), 503, "provider_authentication"),
            (status_error(PermissionDeniedError, 403), 503, "provider_authentication"),
            (status_error(APIStatusError, 500), 503, "provider_unavailable"),
            (status_error(APIStatusError, 400), 502, "provider_error"),
        )
        for error, status, code in cases:
            with self.subTest(status=status, code=code):
                self.create.reset_mock()
                self.create.side_effect = error
                response = self.http.post("/generate", json={"name": "Манометр"})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["detail"]["code"], code)
                self.assertNotIn("private provider error", response.text)
                self.create.assert_called_once()

    def test_invalid_llm_content_returns_502(self):
        self.create.return_value = completion("not JSON")
        response = self.http.post("/generate", json={"name": "Манометр"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["code"], "invalid_llm_response")

    def test_unknown_selected_key_returns_502(self):
        self.create.return_value = completion(generated_content(["выдуманный ключ"]).model_dump_json())
        response = self.http.post("/generate", json={"name": "Манометр"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["code"], "invalid_llm_response")

    def test_missing_api_key_returns_503(self):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}):
            response = self.http.post("/generate", json={"name": "Манометр"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "configuration_error")
        self.sdk.assert_not_called()

    def test_missing_model_returns_503(self):
        with patch.dict("os.environ", {"OPENROUTER_MODEL": ""}):
            response = self.http.post("/generate", json={"name": "Манометр"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "configuration_error")
        self.sdk.assert_not_called()


if __name__ == "__main__":
    unittest.main()
