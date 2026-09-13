# app/services/translation_pipeline.py

from app.core.i18n_glossary import apply_glossary, SUPPORTED_LANGUAGES


class TranslationPipeline:
    def __init__(self, target_language: str = "en"):
        self.target_language = target_language

    def get_system_prompt_addition(self) -> str:
        if self.target_language == "en":
            return ""
        lang_name = SUPPORTED_LANGUAGES.get(self.target_language, "English")
        return (
            f"\n\nCRITICAL DIRECTIVE: Generate the entire response in {lang_name} ({self.target_language}). "
            "Use native terminology, Indian date formats (DD/MM/YYYY), and Indian currency/number formatting (lakh/crore) where applicable. "
            "Maintain high professional cybersecurity standards."
        )

    def post_process(self, text: str) -> str:
        return apply_glossary(text, self.target_language)