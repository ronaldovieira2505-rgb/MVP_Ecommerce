from datetime import date

from django.core.exceptions import ValidationError


def _digits(value):
    return "".join(c for c in str(value) if c.isdigit())


def _check_digit(digits, weights):
    total = sum(int(d) * w for d, w in zip(digits, weights, strict=False))
    rest = total % 11
    return "0" if rest < 2 else str(11 - rest)


def is_valid_cpf(value):
    cpf = str(value)
    if len(cpf) != 11 or not cpf.isdigit() or cpf == cpf[0] * 11:
        return False
    first = _check_digit(cpf[:9], range(10, 1, -1))
    second = _check_digit(cpf[:9] + first, range(11, 1, -1))
    return cpf[9:] == first + second


def is_valid_cnpj(value):
    cnpj = str(value)
    if len(cnpj) != 14 or not cnpj.isdigit() or cnpj == cnpj[0] * 14:
        return False
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, *w1]
    first = _check_digit(cnpj[:12], w1)
    second = _check_digit(cnpj[:12] + first, w2)
    return cnpj[12:] == first + second


def validate_cpf(value):
    if not is_valid_cpf(value):
        raise ValidationError("CPF inválido.")


def validate_cnpj(value):
    if not is_valid_cnpj(value):
        raise ValidationError("CNPJ inválido.")


def validate_adult(value):
    today = date.today()
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if age < 18:
        raise ValidationError("O prestador deve ter 18 anos ou mais.")
