// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LAST_ROUTE_KEY } from './lastRoute'
import { defaultRootRedirect, sharedRoutes } from './sharedRoutes'

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

describe('knowledge routes', () => {
  it('keeps RAG in the Build band and canonicalizes the legacy path', () => {
    const rag = sharedRoutes.find((route) => route.path === '/rag')
    const legacy = sharedRoutes.find((route) => route.path === '/knowledge')

    expect(rag?.meta).toMatchObject({ group: 'Operate', icon: 'fileText', navOrder: 50 })
    expect(legacy?.redirect).toBe('/rag')
  })
})
