# app/core/i18n_glossary.py

SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "te": "Telugu",
    "mr": "Marathi",
    "ta": "Tamil",
    "gu": "Gujarati",
    "ur": "Urdu",
    "kn": "Kannada",
    "or": "Odia",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "as": "Assamese",
    "mai": "Maithili",
    "sat": "Santali",
    "ks": "Kashmiri",
    "ne": "Nepali",
    "sd": "Sindhi",
    "kok": "Konkani",
    "doi": "Dogri",
    "mni": "Manipuri",
    "bho": "Bhojpuri",
}

CYBER_GLOSSARY = {
    "hi": {
        "ransomware": "रै नसमवेयर",
        "malware": "मैल्वेयर",
        "phishing": "फ़िशिंग",
        "vulnerability": "कमजोरी",
        "threat intelligence": "थ्रेट इंटेलिजेंस",
        "indicator of compromise": "कम्प्रोमाइज़ के संकेतक",
        "firewall": "फ़ायरवॉल",
        "encryption": "एन्क्रिप्शन",
    },
    "ta": {
        "ransomware": "ransomware",
        "malware": "malware",
        "phishing": "phishing",
        "vulnerability": "பாதிப்பு",
        "threat intelligence": "அச்சுறுத்தல் நுண்ணறிவு",
        "indicator of compromise": "சமரச குறியீடுகள்",
        "firewall": "firewall",
        "encryption": "மறைகுறியாக்கம்",
    },
    "bn": {
        "ransomware": "র‌্যানসমওয়্যার",
        "malware": "ম্যালওয়্যার",
        "phishing": "ফিশিং",
        "vulnerability": "ভালনারেবিলিটি",
        "threat intelligence": "হুমকি গোয়েন্দা",
        "indicator of compromise": "সংক্রমণের সূচক",
        "firewall": "ফায়ারওয়াল",
        "encryption": "এনক্রিপশন",
    },
    "te": {
        "ransomware": "రాన్సమ్‌వేర్",
        "malware": "మాల్‌వేర్",
        "phishing": "ఫిషింగ్",
        "vulnerability": "దుర్ಬಲತೆ",
        "threat intelligence": "ముప్పు ఇంటెలిజెన్స్",
        "indicator of compromise": "సమస్య సంకేతాలు",
        "firewall": "ఫైర్‌వాల్",
        "encryption": "ఎన్‌క్రిప్షన్",
    },
    "mr": {
        "ransomware": "रॅमसमवेअर",
        "malware": "मॅलवेअर",
        "phishing": "फिशिंग",
        "vulnerability": "सुरक्षा त्रुटी",
        "threat intelligence": "धमकी बुद्धिमत्ता",
        "indicator of compromise": "तडजोड निर्देशक",
        "firewall": "फायरवॉल",
        "encryption": "एन्क्रिप्शन",
    },
}


def apply_glossary(text: str, lang: str) -> str:
    if lang not in CYBER_GLOSSARY:
        return text
    glossary = CYBER_GLOSSARY[lang]
    for eng_term, target_term in glossary.items():
        text = text.replace(eng_term, target_term)
        text = text.replace(eng_term.capitalize(), target_term)
    return text