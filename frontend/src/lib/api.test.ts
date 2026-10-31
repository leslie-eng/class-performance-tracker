import { apiBase, errorMessage, nonJsonMessage, pointsAtFrontend } from './api'

describe('apiBase', () => {
    it('falls back to the dev proxy when unset or blank', () => {
        expect(apiBase(undefined)).toBe('/api')
        expect(apiBase('')).toBe('/api')
        expect(apiBase('   ')).toBe('/api')
    })

    it('strips trailing slashes', () => {
        expect(apiBase('https://api.example.com/')).toBe('https://api.example.com')
        expect(apiBase('https://api.example.com///')).toBe('https://api.example.com')
    })

    it('keeps an explicit scheme', () => {
        expect(apiBase('https://api.example.com')).toBe('https://api.example.com')
        expect(apiBase('http://localhost:8000')).toBe('http://localhost:8000')
    })

    it('adds https when the scheme is missing', () => {
        // Without this the URL would resolve against the frontend's own origin.
        expect(apiBase('classtrack-api.onrender.com')).toBe('https://classtrack-api.onrender.com')
    })

    it('leaves a relative path alone', () => {
        expect(apiBase('/api')).toBe('/api')
    })

    it('trims surrounding whitespace', () => {
        expect(apiBase('  https://api.example.com/  ')).toBe('https://api.example.com')
    })
})

describe('errorMessage', () => {
    it('returns a string detail verbatim', () => {
        expect(errorMessage({ detail: 'Email already registered' }, 'fallback')).toBe('Email already registered')
    })

    it('formats a FastAPI validation array with field paths', () => {
        const body = {
            detail: [
                { loc: ['body', 'email'], msg: 'value is not a valid email address' },
                { loc: ['body', 'password'], msg: 'String should have at least 8 characters' },
            ],
        }
        expect(errorMessage(body, 'fallback')).toBe(
            'email: value is not a valid email address; password: String should have at least 8 characters',
        )
    })

    it('strips the "Value error, " prefix that pydantic adds', () => {
        const body = { detail: [{ loc: ['body', 'day_number'], msg: 'Value error, Day must be between 1 and 100' }] }
        expect(errorMessage(body, 'fallback')).toBe('day_number: Day must be between 1 and 100')
    })

    it('omits the field when loc only contains body', () => {
        const body = { detail: [{ loc: ['body'], msg: 'Invalid payload' }] }
        expect(errorMessage(body, 'fallback')).toBe('Invalid payload')
    })

    it('uses the fallback for an empty validation array', () => {
        expect(errorMessage({ detail: [] }, 'fallback')).toBe('fallback')
    })

    it('uses the fallback when there is no detail (e.g. a 2xx HTML page)', () => {
        expect(errorMessage(null, 'fallback')).toBe('fallback')
        expect(errorMessage('<!doctype html>', 'fallback')).toBe('fallback')
        expect(errorMessage({}, 'fallback')).toBe('fallback')
    })

    // Documents real behaviour rather than ideal behaviour: a missing msg renders as an
    // empty string after the field name (pydantic always sends one, so this is a guard).
    it('keeps the field name but leaves the message empty when msg is missing', () => {
        expect(errorMessage({ detail: [{ loc: ['body', 'x'] }] }, 'fallback')).toBe('x: ')
    })
})


describe('pointsAtFrontend', () => {
    const site = 'https://classtrack-web.onrender.com'

    it('is true for the dev proxy and for the site itself', () => {
        expect(pointsAtFrontend('/api', site)).toBe(true)
        expect(pointsAtFrontend(site, site)).toBe(true)
    })

    it('is false for a separate API host', () => {
        expect(pointsAtFrontend('https://class-performance-tracker.onrender.com', site)).toBe(false)
        expect(pointsAtFrontend('http://localhost:8000', 'http://localhost:5173')).toBe(false)
    })
})

describe('nonJsonMessage', () => {
    const site = 'https://classtrack-web.onrender.com'

    it('blames VITE_API_URL only when it points at the frontend', () => {
        expect(nonJsonMessage('/api', site)).toMatch(/VITE_API_URL is probably unset/)
    })

    // A separate API host answering with HTML is a sleeping free-tier instance waking up,
    // not a misconfiguration: telling people to change VITE_API_URL sent them the wrong way.
    it('says a separate API is probably starting up', () => {
        const msg = nonJsonMessage('https://class-performance-tracker.onrender.com', site)
        expect(msg).toMatch(/probably still starting up/)
        expect(msg).not.toMatch(/VITE_API_URL/)
    })
})
