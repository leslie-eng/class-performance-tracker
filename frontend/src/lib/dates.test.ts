import {
    addDays,
    dateForDay,
    dayNumber,
    daysBetween,
    elapsedDays,
    formatCountdown,
    greeting,
    isoDay,
    parseDay,
    relativeTime,
    secondsToMidnight,
    shortDate,
} from './dates'
import type { Challenge } from './types'

/** Only start_date/total_days drive the date helpers, but build a whole Challenge to stay type-safe. */
function ch(start_date: string, total_days: number): Challenge {
    return {
        id: 1,
        name: 'Challenge',
        description: null,
        start_date,
        end_date: addDays(start_date, total_days - 1),
        total_days,
        task_types_allowed: 'both',
        scoring_rules: {},
        effective_rules: {} as Challenge['effective_rules'],
    }
}

describe('parseDay / isoDay', () => {
    it('parses YYYY-MM-DD as UTC without timezone drift', () => {
        const d = parseDay('2026-03-05')
        expect(d.getUTCFullYear()).toBe(2026)
        expect(d.getUTCMonth()).toBe(2) // March
        expect(d.getUTCDate()).toBe(5)
        expect(d.toISOString().slice(0, 10)).toBe('2026-03-05')
    })

    it('round-trips through isoDay', () => {
        expect(isoDay(parseDay('2026-12-31'))).toBe('2026-12-31')
        expect(isoDay(parseDay('2025-01-01'))).toBe('2025-01-01')
    })

    it('does not shift a date across the local-time boundary', () => {
        // A UTC-midnight parse would render as the previous day in a negative-offset zone,
        // which is the exact bug parseDay avoids.
        expect(isoDay(parseDay('2026-01-01'))).toBe('2026-01-01')
    })
})

describe('addDays', () => {
    it('adds and subtracts whole days', () => {
        expect(addDays('2026-01-10', 5)).toBe('2026-01-15')
        expect(addDays('2026-01-10', -5)).toBe('2026-01-05')
        expect(addDays('2026-01-10', 0)).toBe('2026-01-10')
    })

    it('crosses a month end (2026 is not a leap year, so Feb has 28 days)', () => {
        expect(addDays('2026-02-28', 1)).toBe('2026-03-01')
    })

    it('crosses a month start', () => {
        expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    })

    it('crosses a year boundary', () => {
        expect(addDays('2025-12-31', 1)).toBe('2026-01-01')
        expect(addDays('2026-01-01', -1)).toBe('2025-12-31')
    })
})

describe('daysBetween', () => {
    it('counts forward, backward and zero', () => {
        expect(daysBetween('2026-01-01', '2026-01-31')).toBe(30)
        expect(daysBetween('2026-01-31', '2026-01-01')).toBe(-30)
        expect(daysBetween('2026-01-01', '2026-01-01')).toBe(0)
    })

    it('spans months and years', () => {
        expect(daysBetween('2025-12-25', '2026-01-01')).toBe(7)
    })
})

describe('dayNumber / dateForDay', () => {
    it('treats start_date as day 1', () => {
        const c = ch('2026-01-01', 30)
        expect(dayNumber(c, '2026-01-01')).toBe(1)
        expect(dayNumber(c, '2026-01-10')).toBe(10)
    })

    it('returns less than 1 before the challenge starts', () => {
        expect(dayNumber(ch('2026-01-10', 30), '2026-01-09')).toBe(0)
        expect(dayNumber(ch('2026-01-10', 30), '2026-01-01')).toBe(-8)
    })

    it('can exceed total_days after the challenge ends', () => {
        expect(dayNumber(ch('2026-01-01', 5), '2026-01-31')).toBe(31)
    })

    it('dateForDay is the inverse of dayNumber', () => {
        const c = ch('2026-02-20', 40)
        for (const iso of ['2026-02-20', '2026-03-01', '2026-03-15']) {
            expect(dateForDay(c, dayNumber(c, iso))).toBe(iso)
        }
    })

    it('dateForDay(1) is the start date', () => {
        expect(dateForDay(ch('2026-05-09', 10), 1)).toBe('2026-05-09')
    })
})

describe('elapsedDays', () => {
    const c = ch('2026-01-01', 5)

    it('counts day 1 on the first day', () => {
        expect(elapsedDays(c, '2026-01-01')).toBe(1)
    })

    it('never exceeds total_days', () => {
        expect(elapsedDays(c, '2026-01-05')).toBe(5)
        expect(elapsedDays(c, '2027-01-01')).toBe(5)
    })

    it('never goes below zero before the start', () => {
        expect(elapsedDays(c, '2025-12-31')).toBe(0)
    })
})

describe('formatCountdown', () => {
    it('pads every field to two digits', () => {
        expect(formatCountdown(0)).toBe('00:00:00')
        expect(formatCountdown(59)).toBe('00:00:59')
        expect(formatCountdown(3661)).toBe('01:01:01')
        expect(formatCountdown(86_399)).toBe('23:59:59')
    })
})

describe('secondsToMidnight', () => {
    it('is a full day at UTC midnight', () => {
        expect(secondsToMidnight('UTC', new Date('2026-06-01T00:00:00Z'))).toBe(86_400)
    })

    it('counts down through the day', () => {
        expect(secondsToMidnight('UTC', new Date('2026-06-01T12:00:00Z'))).toBe(43_200)
        expect(secondsToMidnight('UTC', new Date('2026-06-01T23:59:59Z'))).toBe(1)
    })

    it('applies the timezone offset (Nairobi is UTC+3)', () => {
        // 21:00 UTC is already 00:00 the next day in Nairobi.
        expect(secondsToMidnight('Africa/Nairobi', new Date('2026-06-01T20:59:59Z'))).toBe(1)
        expect(secondsToMidnight('Africa/Nairobi', new Date('2026-06-01T21:00:00Z'))).toBe(86_400)
    })
})

describe('relativeTime', () => {
    const base = Date.parse('2026-06-01T12:00:00Z')
    const at = (msAgo: number) => new Date(base - msAgo).toISOString()

    it('uses friendly buckets', () => {
        expect(relativeTime(at(30_000), base)).toBe('just now')
        expect(relativeTime(at(60_000), base)).toBe('1m ago')
        expect(relativeTime(at(120_000), base)).toBe('2m ago')
        expect(relativeTime(at(3_600_000), base)).toBe('1h ago')
        expect(relativeTime(at(7_200_000), base)).toBe('2h ago')
        expect(relativeTime(at(86_400_000), base)).toBe('yesterday')
        expect(relativeTime(at(3 * 86_400_000), base)).toBe('3 days ago')
    })

    it('falls back to a short date after 30 days', () => {
        const out = relativeTime(at(40 * 86_400_000), base)
        expect(out).not.toMatch(/ago|just now|yesterday/)
        expect(out.length).toBeGreaterThan(0)
    })
})

describe('shortDate', () => {
    it('renders the right day of the month', () => {
        expect(shortDate('2026-01-15')).toContain('15')
    })
})

describe('greeting', () => {
    afterEach(() => vi.useRealTimers())

    it('changes with the hour in the given timezone', () => {
        vi.useFakeTimers()
        vi.setSystemTime(new Date('2026-06-01T08:00:00Z'))
        expect(greeting('UTC')).toBe('Good morning')

        vi.setSystemTime(new Date('2026-06-01T13:00:00Z'))
        expect(greeting('UTC')).toBe('Good afternoon')

        vi.setSystemTime(new Date('2026-06-01T20:00:00Z'))
        expect(greeting('UTC')).toBe('Good evening')
    })

    it('respects the timezone offset', () => {
        vi.useFakeTimers()
        // 05:00 UTC is 08:00 in Nairobi.
        vi.setSystemTime(new Date('2026-06-01T05:00:00Z'))
        expect(greeting('Africa/Nairobi')).toBe('Good morning')
        expect(greeting('UTC')).toBe('Good morning')
    })
})
