import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// O jsdom não implementa rolagem; o layout volta ao topo a cada troca de tela.
window.scrollTo = () => {}

afterEach(() => {
  cleanup()
})
