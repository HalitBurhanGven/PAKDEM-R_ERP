import re
import unicodedata


def normalize_text(value: str | None) -> str:
    text = "" if value is None else str(value).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = " ".join(text.split())
    return text


def build_stock_identity_key(name: str | None, sku: str = "", subgroup: str = "") -> str:
    normalized_name = normalize_text(name)
    normalized_subgroup = normalize_text(subgroup)
    normalized_sku = normalize_text(sku)
    if normalized_sku:
        return f"sku:{normalized_sku}|name:{normalized_name}|sub:{normalized_subgroup}"
    return f"name:{normalized_name}|sub:{normalized_subgroup}"
