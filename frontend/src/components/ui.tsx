import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from 'react'
import { useId } from 'react'
import type { Tone } from '../status'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
  block?: boolean
  /** Ação em andamento: trava o botão e mostra o indicador, sem trocar o texto. */
  busy?: boolean
}

export function Button({
  variant = 'primary',
  block,
  busy = false,
  className = '',
  disabled,
  ...rest
}: ButtonProps) {
  const classes = ['btn', `btn-${variant}`, block ? 'btn-block' : '', busy ? 'btn-busy' : '', className]
  return (
    <button
      className={classes.filter(Boolean).join(' ')}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    />
  )
}

/** Carregando: fichas em branco no lugar do conteúdo, para a tela não "pular" ao chegar. */
export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="carregando" role="status">
      <span className="sr-only">Carregando...</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="ficha-vazia" aria-hidden="true">
          <span className="traco traco-titulo" />
          <span className="traco" />
          <span className="traco traco-curto" />
        </div>
      ))}
    </div>
  )
}

type FieldProps = InputHTMLAttributes<HTMLInputElement> & { label: string }

export function Field({ label, ...rest }: FieldProps) {
  const id = useId()
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} {...rest} />
    </div>
  )
}

type SelectFieldProps = SelectHTMLAttributes<HTMLSelectElement> & { label: string }

export function SelectField({ label, children, ...rest }: SelectFieldProps) {
  const id = useId()
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} {...rest}>
        {children}
      </select>
    </div>
  )
}

/** Ficha: a folha de papel do sistema. `tone` pinta a lombada com o estado. */
export function Card({ tone, children }: { tone?: Tone; children: ReactNode }) {
  return <section className={`ficha ${tone ? `ficha-${tone}` : ''}`}>{children}</section>
}

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'success' | 'error' | 'warning' | 'info'
  children: ReactNode
}) {
  return <span className={`badge ${tone === 'neutral' ? '' : `badge-${tone}`}`}>{children}</span>
}

/** Posições preenchidas: as marcas acompanham a contagem, que fica no texto. */
export function Slots({ filled, total }: { filled: number; total: number }) {
  return (
    <span className="row-vagas">
      <span className="slots" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={`slot ${i < filled ? 'slot-cheio' : ''}`} />
        ))}
      </span>
      <span>
        {filled}/{total} posições
      </span>
    </span>
  )
}

export function Alert({
  tone = 'info',
  children,
}: {
  tone?: 'info' | 'success' | 'error'
  children: ReactNode
}) {
  return (
    <div className={`alert alert-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  )
}
