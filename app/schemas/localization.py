# app/schemas/localization.py

from enum import Enum
from pydantic import BaseModel, Field


class LanguageCode(str, Enum):
    ENGLISH = "en"
    HINDI = "hi"
    BENGALI = "bn"
    TELUGU = "te"
    MARATHI = "mr"
    TAMIL = "ta"
    GUJARATI = "gu"
    URDU = "ur"
    KANNADA = "kn"
    ODIA = "or"
    MALAYALAM = "ml"
    PUNJABI = "pa"
    ASSAMESE = "as"
    MAITHILI = "mai"
    SANTALI = "sat"
    KASHMIRI = "ks"
    NEPALI = "ne"
    SINDHI = "sd"
    KONKANI = "kok"
    DOGRI = "doi"
    MANIPURI = "mni"
    BHOJPURI = "bho"


class GenerationParams(BaseModel):
    output_language: LanguageCode = Field(default=LanguageCode.ENGLISH)
    include_glossary_alignment: bool = Field(default=True)