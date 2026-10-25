import { describe, expect, it } from 'vitest'
import packages from '../engine/assets/octatrack-module-packages.json'
import { cardBuildError, moduleUsbOnly } from './usb-only'

describe('modules that need the Modwerk base', () => {
  it('keeps a module whose USB package requires a base DSP feature out of card firmware', () => {
    const published = { packages: [{ id: 'repitch', requires: 8 }, { id: 'tapehead' }] }
    expect(moduleUsbOnly('repitch', published)).toBe(true)
    expect(moduleUsbOnly('tapehead', published)).toBe(false)
    expect(cardBuildError(['tapehead'], true, published)).toBe('')
    expect(cardBuildError(['tapehead', 'repitch'], true, published)).toMatch(/^Repitch needs the Modwerk base, so card firmware cannot include it\. Sync this set over USB/)
    // Without USB sync (the beta interface) it does not point at a sync the member cannot start.
    expect(cardBuildError(['repitch'], false, published)).toMatch(/in the beta for now; take it out to build card firmware\.$/)
    expect(() => cardBuildError(['unknown'], true, published)).toThrow('Unknown module')
  })

  it('follows the published packages', () => {
    expect(moduleUsbOnly('ring-sc')).toBe(true) // RINGMOD SC: its package requires the key bus
    for (const entry of packages.packages as { id: string; requires?: number }[]) {
      expect(moduleUsbOnly(entry.id)).toBe(!!entry.requires)
      if (!entry.requires) expect(cardBuildError([entry.id])).toBe('')
    }
  })
})
