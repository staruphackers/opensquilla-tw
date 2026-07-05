// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LAST_ROUTE_KEY } from './lastRoute'
import { defaultRootRedirect } from './sharedRoutes'

beforeEach(() => {
  localStorage.clear()
  delete window.opensquillaDesktop
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
})

describe('defaultRootRedirect', () => {
  it('opens the desktop app on Chat even when a previous route was saved', () => {
    window.opensquillaDesktop = {} as never
    localStorage.setItem(LAST_ROUTE_KEY, '/sessions')

    expect(defaultRootRedirect()).toBe('/chat')
  })

  it('keeps browser desktop restore behavior', () => {
    localStorage.setItem(LAST_ROUTE_KEY, '/overview')

    expect(defaultRootRedirect()).toBe('/overview')
  })
})
