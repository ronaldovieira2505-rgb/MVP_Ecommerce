import { onlyDigits } from './cnpj'

function checkDigit(digits: string, start: number): number {
  const total = digits.split('').reduce((sum, d, i) => sum + Number(d) * (start - i), 0)
  const rest = total % 11
  return rest < 2 ? 0 : 11 - rest
}

/** Valida os dígitos verificadores (mesma regra do backend). Aceita máscara. */
export function isValidCpf(value: string): boolean {
  const cpf = onlyDigits(value)
  if (cpf.length !== 11 || /^(\d)\1+$/.test(cpf)) return false
  const first = checkDigit(cpf.slice(0, 9), 10)
  const second = checkDigit(cpf.slice(0, 9) + first, 11)
  return cpf.slice(9) === `${first}${second}`
}

/** Idade completa em anos na data de hoje; `birthDate` no formato AAAA-MM-DD. */
export function ageFrom(birthDate: string, today = new Date()): number {
  const [year, month, day] = birthDate.split('-').map(Number)
  const hadBirthday =
    today.getMonth() + 1 > month || (today.getMonth() + 1 === month && today.getDate() >= day)
  return today.getFullYear() - year - (hadBirthday ? 0 : 1)
}
