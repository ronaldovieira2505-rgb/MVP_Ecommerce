export function onlyDigits(value: string): string {
  return value.replace(/\D/g, '')
}

function checkDigit(digits: string, weights: number[]): number {
  const total = weights.reduce((sum, weight, i) => sum + Number(digits[i]) * weight, 0)
  const rest = total % 11
  return rest < 2 ? 0 : 11 - rest
}

/** Valida os dígitos verificadores (mesma regra do backend). Aceita máscara. */
export function isValidCnpj(value: string): boolean {
  const cnpj = onlyDigits(value)
  if (cnpj.length !== 14 || /^(\d)\1+$/.test(cnpj)) return false
  const w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
  const first = checkDigit(cnpj.slice(0, 12), w1)
  const second = checkDigit(cnpj.slice(0, 12) + first, [6, ...w1])
  return cnpj.slice(12) === `${first}${second}`
}
