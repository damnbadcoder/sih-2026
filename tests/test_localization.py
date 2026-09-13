import pytest
from app.core.i18n_glossary import apply_glossary, SUPPORTED_LANGUAGES
from app.schemas.localization import LanguageCode, GenerationParams
from app.services.translation_pipeline import TranslationPipeline


def test_supported_languages_count():
    assert len(SUPPORTED_LANGUAGES) == 22


def test_apply_glossary_hindi():
    text = "A severe ransomware attack and malware deployment."
    processed = apply_glossary(text, "hi")
    assert "रै नसमवेयर" in processed
    assert "मैल्वेयर" in processed


def test_translation_pipeline_prompt():
    pipeline = TranslationPipeline(target_language="hi")
    prompt = pipeline.get_system_prompt_addition()
    assert "Hindi" in prompt
    assert "DD/MM/YYYY" in prompt


def test_generation_params_default():
    params = GenerationParams()
    assert params.output_language == LanguageCode.ENGLISH
    assert params.include_glossary_alignment is True