"""Currency normalization: the printed currency becomes an ISO 4217 code before
it reaches the invoice row, price memory, or a WhatsApp reply.

C3 reads the currency exactly as printed ("Dhs", "dirhams", the new dirham
sign) because the eval needs to know what the model saw. Everything after
extraction is deterministic, so the code is derived here, once, and the reply
never says "total dirhams 402.00" again (found live 2026-08-24).
"""

# U+20C3 UAE DIRHAM SIGN (Unicode 18.0) and U+20C1 SAUDI RIYAL SIGN (17.0):
# both are stylised Arabic letters, so they arrive as single code points
# from a vision model that reads a printed receipt with the new marks.
UAE_DIRHAM_SIGN = "⃃"
SAUDI_RIYAL_SIGN = "⃁"

# Keys are already cleaned (see _clean). Bare "dinar" is deliberately absent:
# Kuwait and Bahrain both use it and guessing would be worse than passing the
# printed word through. Bare "riyal" maps to Saudi and "rial" to Oman, the
# spellings each country prints; a printed ISO code always wins anyway.
_ALIASES: dict[str, str] = {
    # United Arab Emirates
    "aed": "AED",
    "dirham": "AED",
    "dirhams": "AED",
    "dhs": "AED",
    "dh": "AED",
    "uae dirham": "AED",
    "uae dirhams": "AED",
    "درهم": "AED",
    "دراهم": "AED",
    "درهم إماراتي": "AED",
    "دإ": "AED",
    UAE_DIRHAM_SIGN: "AED",
    # Saudi Arabia
    "sar": "SAR",
    "sr": "SAR",
    "riyal": "SAR",
    "riyals": "SAR",
    "saudi riyal": "SAR",
    "saudi riyals": "SAR",
    "ريال": "SAR",
    "ريال سعودي": "SAR",
    "رس": "SAR",
    SAUDI_RIYAL_SIGN: "SAR",
    # Qatar
    "qar": "QAR",
    "qr": "QAR",
    "qatari riyal": "QAR",
    "ريال قطري": "QAR",
    "رق": "QAR",
    # Kuwait
    "kwd": "KWD",
    "kd": "KWD",
    "kuwaiti dinar": "KWD",
    "دينار كويتي": "KWD",
    "دك": "KWD",
    # Bahrain
    "bhd": "BHD",
    "bd": "BHD",
    "bahraini dinar": "BHD",
    "دينار بحريني": "BHD",
    "دب": "BHD",
    # Oman
    "omr": "OMR",
    "ro": "OMR",
    "rial": "OMR",
    "rials": "OMR",
    "omani rial": "OMR",
    "ريال عماني": "OMR",
    "رع": "OMR",
}

# Punctuation that printed currency marks carry and the aliases do not:
# "Dhs.", "(AED)", "د.إ", "ر.س", and the Arabic tatweel used for kerning.
_STRIP = str.maketrans("", "", ".,()[]/ـ")


def _clean(raw: str) -> str:
    return " ".join(raw.translate(_STRIP).casefold().split())


def normalize_currency(raw: str | None) -> str | None:
    """Printed currency -> ISO 4217 code. Unknown text passes through trimmed:
    a word we cannot place is still information, and inventing a code is not.
    """
    if raw is None:
        return None
    key = _clean(raw)
    if not key:
        return None
    if key in _ALIASES:
        return _ALIASES[key]
    # "AED (Dhs)", "Total in Dirhams": the first token we recognise decides.
    for token in key.split():
        if token in _ALIASES:
            return _ALIASES[token]
    return raw.strip()


def currency_differs(invoice_currency: str | None, tenant_currency: str | None) -> bool:
    """Is this invoice billed in something other than the tenant's own money?

    The one comparison behind the WP-28 hold: the reply asks about it, price
    memory refuses it, and the ack says so. `supplier_items.last_price` is a
    bare number with no currency dimension, so a USD line landing in an AED
    tenant's baseline is not a small inaccuracy - it is a number that means
    nothing, and by M5 it is a cost per gram that means nothing.

    Either side unknown is not a mismatch: an unreadable currency is a
    different problem (the invoice defaults to the tenant's on the way in),
    and inventing a hold from a null would stop invoices for no reason.
    """
    if not invoice_currency or not tenant_currency:
        return False
    return invoice_currency.strip().upper() != tenant_currency.strip().upper()
