import { canEditOrCancel, emptyProposal, MAX_CHALLENGE_DAYS, STATUS_BADGE, validateProposal } from './challenges'
import { addDays } from './dates'
import type { ChallengeStatus, ProposalInput } from './types'

const today = '2026-10-31'
const valid = (over: Partial<ProposalInput> = {}): ProposalInput => ({
    name: '30 Days of SQL',
    description: null,
    start_date: '2026-11-02',
    end_date: '2026-12-01',
    task_types_allowed: 'code',
    ...over,
})

describe('validateProposal', () => {
    it('accepts a valid proposal', () => {
        expect(validateProposal(valid(), today)).toEqual({})
        expect(validateProposal(valid({ start_date: today, end_date: today }), today)).toEqual({})
    })

    it('needs a name of at least 3 characters, ignoring spaces', () => {
        expect(validateProposal(valid({ name: '  Go ' }), today).name).toMatch(/at least 3/)
    })

    it("rejects a start date in the past, but not when an edit leaves it unchanged", () => {
        expect(validateProposal(valid({ start_date: '2026-10-30' }), today).start_date).toMatch(/past/)
        expect(validateProposal(valid({ start_date: '2026-10-30' }), today, false)).toEqual({})
    })

    it('needs the end on or after the start', () => {
        expect(validateProposal(valid({ end_date: '2026-11-01' }), today).end_date).toMatch(/on or after/)
    })

    it(`allows at most ${MAX_CHALLENGE_DAYS} days, counting both ends`, () => {
        const start = '2026-11-01'
        expect(validateProposal(valid({ start_date: start, end_date: addDays(start, MAX_CHALLENGE_DAYS - 1) }), today)).toEqual({})
        expect(validateProposal(valid({ start_date: start, end_date: addDays(start, MAX_CHALLENGE_DAYS) }), today).end_date).toMatch(/at most/)
    })

    it('reports missing dates', () => {
        const errors = validateProposal(valid({ start_date: '', end_date: '' }), today)
        expect(errors.start_date).toMatch(/start date/)
        expect(errors.end_date).toMatch(/end date/)
    })
})

describe('emptyProposal', () => {
    it('starts tomorrow, runs a month, and passes validation once named', () => {
        const p = emptyProposal(today)
        expect(p.start_date).toBe('2026-11-01')
        expect(validateProposal({ ...p, name: 'A real name' }, today)).toEqual({})
    })
})

describe('status badges and actions', () => {
    const all: ChallengeStatus[] = ['pending', 'approved', 'rejected', 'cancelled']

    it('has a distinct label for every status', () => {
        const labels = all.map((s) => STATUS_BADGE[s].label)
        expect(new Set(labels).size).toBe(all.length)
        expect(STATUS_BADGE.rejected.label).toBe('Not approved')
    })

    it('only lets members edit or cancel while pending', () => {
        expect(all.filter(canEditOrCancel)).toEqual(['pending'])
    })
})
