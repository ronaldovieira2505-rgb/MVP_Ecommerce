/** Cor do estado da vaga, usada na lombada da ficha e no marcador.
 *
 * A convenção vale em todas as telas: colete (amarelo) é o que depende de uma
 * ação da empresa, verde é dinheiro retido em custódia, azul é turno em
 * andamento e cinza é vaga encerrada.
 */
export type Tone = 'colete' | 'carimbo' | 'uniforme' | 'encerrada'

const TONES: Record<string, Tone> = {
  AGUARDANDO_PAGAMENTO: 'colete',
  PUBLICADA: 'carimbo',
  CANDIDATURAS_ENCERRADAS: 'uniforme',
  EM_ANDAMENTO: 'uniforme',
  FINALIZADA: 'encerrada',
  CANCELADA: 'encerrada',
}

export function toneFor(status: string): Tone {
  return TONES[status] ?? 'encerrada'
}

/** Marcador de estado equivalente ao tom da lombada. */
export function badgeToneFor(status: string): 'neutral' | 'success' | 'warning' | 'info' {
  switch (toneFor(status)) {
    case 'colete':
      return 'warning'
    case 'carimbo':
      return 'success'
    case 'uniforme':
      return 'info'
    default:
      return 'neutral'
  }
}
