import { initials } from './format'

describe('initials', () => {
    it('uses the first letter of the first two words', () => {
        expect(initials('Maya Patel')).toBe('MP')
        expect(initials('Demo Student')).toBe('DS')
    })

    it('collapses extra whitespace', () => {
        expect(initials('  Maya   Patel  ')).toBe('MP')
    })

    it('takes at most two words', () => {
        expect(initials('Maya Anjali Patel')).toBe('MA')
    })

    it('handles a single name', () => {
        expect(initials('Prince')).toBe('P')
    })

    it('upper-cases', () => {
        expect(initials('maya patel')).toBe('MP')
    })

    it('returns an empty string for empty or whitespace-only input', () => {
        expect(initials('')).toBe('')
        expect(initials('   ')).toBe('')
    })

    it('handles apostrophes without breaking (O\'Connor -> first letters)', () => {
        expect(initials("Liam O'Connor")).toBe('LO')
    })
})
