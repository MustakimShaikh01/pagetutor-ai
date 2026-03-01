'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';

const API = 'http://localhost:8000/api/v1';

/* ── password strength ───────────────────────────── */
type Strength = { score: number; label: string; color: string };
function calcStrength(pwd: string): Strength {
    if (!pwd) return { score: 0, label: '', color: '' };
    let sc = 0;
    if (pwd.length >= 8) sc++;
    if (pwd.length >= 12) sc++;
    if (/[0-9]/.test(pwd)) sc++;
    if (/[^a-zA-Z0-9]/.test(pwd)) sc++;
    const map: Strength[] = [
        { score: 0, label: 'Too short', color: 'var(--c-red)' },
        { score: 1, label: 'Weak', color: 'var(--c-orange)' },
        { score: 2, label: 'Fair', color: 'var(--c-yellow)' },
        { score: 3, label: 'Good', color: 'var(--c-green)' },
        { score: 4, label: 'Strong 💪', color: 'var(--c-teal)' },
    ];
    return map[sc];
}

/* ── parse pydantic/fastapi errors ───────────────── */
function parseApiError(data: any): string {
    if (typeof data?.detail === 'string') return data.detail;
    if (Array.isArray(data?.detail)) {
        return data.detail
            .map((e: any) => e.msg?.replace(/^Value error,\s*/i, ''))
            .filter(Boolean)
            .join('. ');
    }
    return 'Something went wrong. Please try again.';
}

/* ── eye icon ─────────────────────────────────────── */
const EyeOpen = () => <span style={{ fontSize: '1.1rem', lineHeight: 1 }}>👁️</span>;
const EyeClosed = () => <span style={{ fontSize: '1.1rem', lineHeight: 1 }}>🙈</span>;

/* ── field-level validation ──────────────────────── */
interface FieldErrors {
    full_name?: string;
    email?: string;
    password?: string;
    confirmPassword?: string;
}

function validateForm(
    mode: 'login' | 'register',
    form: { full_name: string; email: string; password: string; confirmPassword: string }
): FieldErrors {
    const err: FieldErrors = {};
    if (mode === 'register') {
        if (!form.full_name.trim() || form.full_name.trim().length < 2)
            err.full_name = 'Full name must be at least 2 characters';
        if (form.password.length < 8)
            err.password = 'Password must be at least 8 characters';
        if (form.password !== form.confirmPassword)
            err.confirmPassword = 'Passwords do not match';
    }
    if (!form.email.includes('@'))
        err.email = 'Enter a valid email address';
    return err;
}

/* ══════════════════════════════════════════════════
   Auth Page
═══════════════════════════════════════════════════ */
export default function AuthPage() {
    const router = useRouter();
    const [mode, setMode] = useState<'login' | 'register'>('login');
    const [loading, setLoading] = useState(false);
    const [apiError, setApiError] = useState('');
    const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
    const [showPwd, setShowPwd] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [form, setForm] = useState({
        full_name: '', email: '', password: '', confirmPassword: ''
    });

    const strength = calcStrength(form.password);

    const set = useCallback((k: keyof typeof form, v: string) => {
        setForm(f => ({ ...f, [k]: v }));
        setFieldErrors(fe => ({ ...fe, [k]: undefined }));
        setApiError('');
    }, []);

    const switchMode = (m: typeof mode) => {
        setMode(m);
        setApiError('');
        setFieldErrors({});
        setForm({ full_name: '', email: '', password: '', confirmPassword: '' });
    };

    const handle = async (e: React.FormEvent) => {
        e.preventDefault();
        const errors = validateForm(mode, form);
        if (Object.keys(errors).length) { setFieldErrors(errors); return; }

        setLoading(true);
        setApiError('');
        try {
            if (mode === 'register') {
                const r = await fetch(`${API}/auth/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: form.email,
                        password: form.password,
                        full_name: form.full_name.trim(),
                    }),
                });
                if (!r.ok) throw new Error(parseApiError(await r.json()));
            }

            const r = await fetch(`${API}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ email: form.email, password: form.password }),
            });
            const data = await r.json();
            if (!r.ok) throw new Error(parseApiError(data));

            if (data.access_token) localStorage.setItem('token', data.access_token);
            router.push('/dashboard');
        } catch (err: any) {
            setApiError(err.message);
        } finally {
            setLoading(false);
        }
    };

    /* ── render ── */
    return (
        <div className="auth-page">
            <div className="auth-card animate-fade-in-up">

                {/* Header */}
                <div className="auth-header">
                    <div className="auth-logo">🎓</div>
                    <h1>PageTutor AI</h1>
                    <p>Enterprise PDF Learning Platform</p>
                </div>

                {/* Tabs */}
                <div className="auth-tabs" role="tablist">
                    {(['login', 'register'] as const).map(m => (
                        <button
                            key={m}
                            role="tab"
                            aria-selected={mode === m}
                            className={`auth-tab ${mode === m ? 'active' : ''}`}
                            onClick={() => switchMode(m)}
                        >
                            {m === 'login' ? '🔑 Sign In' : '🚀 Register'}
                        </button>
                    ))}
                </div>

                {/* Form */}
                <form onSubmit={handle} className="auth-form" noValidate>

                    {/* Full Name */}
                    {mode === 'register' && (
                        <div className="form-group">
                            <label htmlFor="full_name">Full Name</label>
                            <input
                                id="full_name"
                                type="text"
                                placeholder="Mustakim Shaikh"
                                value={form.full_name}
                                onChange={e => set('full_name', e.target.value)}
                                className={fieldErrors.full_name ? 'input-error' : ''}
                                autoComplete="name"
                            />
                            {fieldErrors.full_name && (
                                <span className="field-error">⚠ {fieldErrors.full_name}</span>
                            )}
                        </div>
                    )}

                    {/* Email */}
                    <div className="form-group">
                        <label htmlFor="email">Email Address</label>
                        <input
                            id="email"
                            type="email"
                            placeholder="you@example.com"
                            value={form.email}
                            onChange={e => set('email', e.target.value)}
                            className={fieldErrors.email ? 'input-error' : ''}
                            autoComplete="email"
                        />
                        {fieldErrors.email && (
                            <span className="field-error">⚠ {fieldErrors.email}</span>
                        )}
                    </div>

                    {/* Password */}
                    <div className="form-group">
                        <label htmlFor="password">Password</label>
                        <div className="input-wrap">
                            <input
                                id="password"
                                type={showPwd ? 'text' : 'password'}
                                placeholder={mode === 'register' ? 'Min 8 characters' : '••••••••'}
                                value={form.password}
                                onChange={e => set('password', e.target.value)}
                                className={fieldErrors.password ? 'input-error' : ''}
                                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                            />
                            <button
                                type="button"
                                className="pwd-toggle"
                                onClick={() => setShowPwd(v => !v)}
                                aria-label={showPwd ? 'Hide password' : 'Show password'}
                                tabIndex={-1}
                            >
                                {showPwd ? <EyeClosed /> : <EyeOpen />}
                            </button>
                        </div>
                        {fieldErrors.password && (
                            <span className="field-error">⚠ {fieldErrors.password}</span>
                        )}

                        {/* Strength bar (register only) */}
                        {mode === 'register' && form.password.length > 0 && (
                            <div className="pwd-strength">
                                <div className="pwd-bar">
                                    {[0, 1, 2, 3].map(i => (
                                        <div key={i} className="pwd-segment" style={{
                                            background: i < strength.score ? strength.color : 'rgba(255,255,255,0.07)',
                                        }} />
                                    ))}
                                </div>
                                <span className="pwd-label" style={{ color: strength.color }}>{strength.label}</span>
                            </div>
                        )}

                        {/* Hints */}
                        {mode === 'register' && (
                            <div className="pwd-hints">
                                <span className={form.password.length >= 8 ? 'hint-ok' : 'hint-dim'}>
                                    {form.password.length >= 8 ? '✓' : '○'} At least 8 characters
                                </span>
                                <span className={/[0-9]/.test(form.password) ? 'hint-ok' : 'hint-dim'}>
                                    {/[0-9]/.test(form.password) ? '✓' : '○'} Contains a number
                                </span>
                                <span className={/[^a-zA-Z0-9]/.test(form.password) ? 'hint-ok' : 'hint-dim'}>
                                    {/[^a-zA-Z0-9]/.test(form.password) ? '✓' : '○'} Special character (recommended)
                                </span>
                            </div>
                        )}
                    </div>

                    {/* Confirm Password (register only) */}
                    {mode === 'register' && (
                        <div className="form-group">
                            <label htmlFor="confirmPassword">Confirm Password</label>
                            <div className="input-wrap">
                                <input
                                    id="confirmPassword"
                                    type={showConfirm ? 'text' : 'password'}
                                    placeholder="Re-enter password"
                                    value={form.confirmPassword}
                                    onChange={e => set('confirmPassword', e.target.value)}
                                    className={fieldErrors.confirmPassword ? 'input-error' : form.confirmPassword && form.confirmPassword === form.password ? 'input-ok' : ''}
                                    autoComplete="new-password"
                                />
                                <button
                                    type="button"
                                    className="pwd-toggle"
                                    onClick={() => setShowConfirm(v => !v)}
                                    aria-label={showConfirm ? 'Hide' : 'Show'}
                                    tabIndex={-1}
                                >
                                    {showConfirm ? <EyeClosed /> : <EyeOpen />}
                                </button>
                            </div>
                            {fieldErrors.confirmPassword && (
                                <span className="field-error">⚠ {fieldErrors.confirmPassword}</span>
                            )}
                            {!fieldErrors.confirmPassword && form.confirmPassword && form.confirmPassword === form.password && (
                                <span className="field-success">✓ Passwords match</span>
                            )}
                        </div>
                    )}

                    {/* API error banner */}
                    {apiError && (
                        <div className="auth-error" role="alert">
                            <strong>Error:</strong> {apiError}
                        </div>
                    )}

                    <button type="submit" className="auth-submit" disabled={loading}>
                        {loading
                            ? <><span className="spinner" /> {mode === 'login' ? 'Signing in…' : 'Creating account…'}</>
                            : mode === 'login' ? '🔑 Sign In' : '🚀 Create Account'}
                    </button>
                </form>

                {/* Demo helper */}
                <div className="auth-demo">
                    <p>🧪 <strong>Dev Mode</strong> — only 8-char minimum enforced</p>
                    <div className="demo-creds">
                        <code>demo@pagetutor.ai</code>
                        <code>demo1234</code>
                    </div>
                    <button
                        type="button"
                        className="demo-fill-btn"
                        onClick={() => {
                            switchMode('login');
                            setForm(f => ({ ...f, email: 'demo@pagetutor.ai', password: 'demo1234' }));
                        }}
                    >
                        ⚡ Fill Demo Credentials
                    </button>
                </div>

                <p className="auth-footer">
                    Built by <strong>Mustakim Shaikh</strong> ·{' '}
                    <a href="https://github.com/MustakimShaikh01" target="_blank" rel="noreferrer">GitHub</a>
                </p>
            </div>
        </div>
    );
}
