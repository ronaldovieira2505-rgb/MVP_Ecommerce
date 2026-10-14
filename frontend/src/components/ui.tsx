import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import { useId } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
  block?: boolean
}

export function Button({ variant = 'primary', block, className = '', ...rest }: ButtonProps) {
  const classes = ['btn', `btn-${variant}`, block ? 'btn-block' : '', className]
  return <button className={classes.filter(Boolean).join(' ')} {...rest} />
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

export function Card({ children }: { children: ReactNode }) {
  return <section className="card">{children}</section>
}

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'success' | 'error' | 'warning'
  children: ReactNode
}) {
  return <span className={`badge ${tone === 'neutral' ? '' : `badge-${tone}`}`}>{children}</span>
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
