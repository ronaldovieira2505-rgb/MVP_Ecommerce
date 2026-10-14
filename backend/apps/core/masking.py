"""Máscaras de dados pessoais (LGPD) para respostas e logs."""


def _digits(value):
    return "".join(c for c in str(value or "") if c.isdigit())


def mask_cpf(cpf):
    digits = _digits(cpf)
    if len(digits) != 11:
        return "***"
    return f"***.{digits[3:6]}.{digits[6:9]}-**"


def mask_phone(phone):
    digits = _digits(phone)
    return f"****{digits[-4:]}" if len(digits) >= 4 else "****"


def mask_email(email):
    local, _, domain = str(email or "").partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"


def mask_pix_key(key_type, key):
    if not key:
        return ""
    if key_type == "CPF":
        return mask_cpf(key)
    if key_type == "EMAIL":
        return mask_email(key)
    if key_type == "TELEFONE":
        return mask_phone(key)
    return f"****{str(key)[-4:]}"
