import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button, Loading } from './ui'

describe('Button', () => {
  it('em andamento fica travado, avisa leitores de tela e mantém o texto', async () => {
    const onClick = vi.fn()
    render(
      <Button busy onClick={onClick}>
        Pagar e publicar
      </Button>,
    )

    const button = screen.getByRole('button', { name: 'Pagar e publicar' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('fora de andamento funciona normalmente', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Buscar</Button>)

    const button = screen.getByRole('button', { name: 'Buscar' })
    expect(button).not.toHaveAttribute('aria-busy')
    await userEvent.click(button)
    expect(onClick).toHaveBeenCalledOnce()
  })
})

describe('Loading', () => {
  it('anuncia o carregamento e desenha uma ficha em branco por linha', () => {
    const { container } = render(<Loading rows={2} />)

    expect(screen.getByRole('status')).toHaveTextContent('Carregando...')
    expect(container.querySelectorAll('.ficha-vazia')).toHaveLength(2)
  })
})
