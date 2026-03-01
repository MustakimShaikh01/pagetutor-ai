/**
 * PageTutor AI - Landing Page (Home)
 * Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
 *
 * SSR page with:
 * - Hero section with gradient headline
 * - Feature showcase (all 9 features)
 * - How it works section
 * - Pricing tiers
 * - Stats / social proof
 * - CTA sections
 */

import Link from 'next/link';
import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'PageTutor AI — Turn Any PDF Into a Complete Learning Course',
    description:
        'Upload any PDF and instantly get AI-generated summaries, quizzes, flashcards, narrated video lectures, and chat capabilities. Start free today.',
};

// ============================================================
// Feature Data
// ============================================================
const FEATURES = [
    {
        icon: '📄',
        title: 'Structured Summary',
        description: 'AI extracts key insights and generates section-by-section summaries with learning points.',
        color: 'rgba(99, 102, 241, 0.15)',
        borderColor: 'rgba(99, 102, 241, 0.3)',
    },
    {
        icon: '🗂️',
        title: 'Topic Segmentation',
        description: 'Automatically segments your PDF into logical chapters and topic blocks.',
        color: 'rgba(139, 92, 246, 0.15)',
        borderColor: 'rgba(139, 92, 246, 0.3)',
    },
    {
        icon: '📊',
        title: 'Auto-Generated PPT',
        description: 'Exports a ready-to-present PowerPoint based on document structure.',
        color: 'rgba(6, 182, 212, 0.15)',
        borderColor: 'rgba(6, 182, 212, 0.3)',
    },
    {
        icon: '🗣️',
        title: 'Multi-Language TTS',
        description: 'Narrates your content in 10+ languages including English, Hindi, French, Spanish.',
        color: 'rgba(16, 185, 129, 0.15)',
        borderColor: 'rgba(16, 185, 129, 0.3)',
    },
    {
        icon: '🎥',
        title: 'Full Video Lecture',
        description: 'Generates a narrated slideshow video you can share and embed anywhere.',
        color: 'rgba(245, 158, 11, 0.15)',
        borderColor: 'rgba(245, 158, 11, 0.3)',
    },
    {
        icon: '🃏',
        title: 'Smart Flashcards',
        description: 'Creates spaced-repetition ready flashcards for effective memorization.',
        color: 'rgba(239, 68, 68, 0.15)',
        borderColor: 'rgba(239, 68, 68, 0.3)',
    },
    {
        icon: '📝',
        title: 'AI Quiz Generator',
        description: 'Generates MCQs, true/false, and fill-in-the-blank questions with explanations.',
        color: 'rgba(99, 102, 241, 0.15)',
        borderColor: 'rgba(99, 102, 241, 0.3)',
    },
    {
        icon: '💬',
        title: 'Chat with PDF',
        description: 'Ask any question about your document and get grounded, context-aware answers.',
        color: 'rgba(6, 182, 212, 0.15)',
        borderColor: 'rgba(6, 182, 212, 0.3)',
    },
    {
        icon: '🧠',
        title: 'Learning Points',
        description: 'Key takeaways extracted per page for quick review and retention.',
        color: 'rgba(16, 185, 129, 0.15)',
        borderColor: 'rgba(16, 185, 129, 0.3)',
    },
];

const PRICING = [
    {
        name: 'Free',
        price: '$0',
        period: 'forever',
        features: ['5 PDF jobs/day', '50MB max file', '500 pages max', 'All features', 'Community support'],
        cta: 'Start Free',
        highlighted: false,
    },
    {
        name: 'Pro',
        price: '$19',
        period: '/month',
        features: ['100 PDF jobs/day', '50MB max file', '500 pages max', 'Priority queue', 'API access', 'Email support'],
        cta: 'Start Pro Trial',
        highlighted: true,
    },
    {
        name: 'Enterprise',
        price: 'Custom',
        period: '',
        features: ['Unlimited jobs', 'Custom limits', 'Dedicated workers', 'SSO/SAML', 'SLA guarantee', 'Dedicated support'],
        cta: 'Contact Sales',
        highlighted: false,
    },
];

const STATS = [
    { value: '10M+', label: 'Pages Processed' },
    { value: '500K+', label: 'Users' },
    { value: '10+', label: 'Languages' },
    { value: '99.9%', label: 'Uptime SLA' },
];

// ============================================================
// Page Component
// ============================================================
export default function HomePage() {
    return (
        <main>
            {/* Navigation */}
            <nav className="navbar">
                <div className="container flex items-center justify-between">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{
                            width: '36px', height: '36px',
                            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                            borderRadius: '10px',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: '1.2rem',
                        }}>🎓</div>
                        <span style={{ fontFamily: 'var(--font-display)', fontWeight: '700', fontSize: '1.2rem' }}>
                            PageTutor AI
                        </span>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <Link href="/auth" className="btn btn-secondary btn-sm">Login</Link>
                        <Link href="/auth" className="btn btn-primary btn-sm">Get Started Free</Link>
                    </div>
                </div>
            </nav>

            {/* Hero Section */}
            <section style={{ paddingTop: '140px', paddingBottom: '100px', textAlign: 'center' }}>
                <div className="container">
                    <div style={{
                        display: 'inline-flex', alignItems: 'center', gap: '8px',
                        padding: '8px 20px',
                        background: 'rgba(99, 102, 241, 0.1)',
                        border: '1px solid rgba(99, 102, 241, 0.3)',
                        borderRadius: '9999px',
                        fontSize: '0.85rem', color: '#a5b4fc',
                        marginBottom: '32px',
                    }}>
                        <span>🚀</span>
                        <span>Enterprise-grade AI PDF Platform · Open Source Models</span>
                    </div>

                    <h1 style={{ marginBottom: '24px', maxWidth: '900px', margin: '0 auto 24px' }}>
                        Turn Any PDF Into a{' '}
                        <span className="gradient-text">Complete Learning Course</span>
                        {' '}With AI
                    </h1>

                    <p style={{
                        fontSize: '1.2rem', color: 'var(--color-text-secondary)',
                        maxWidth: '680px', margin: '0 auto 48px', lineHeight: '1.7',
                    }}>
                        Upload any document and instantly get AI summaries, quizzes, flashcards,
                        multi-language narration, video lectures, and intelligent chat — all in minutes.
                    </p>

                    <div style={{ display: 'flex', gap: '16px', justifyContent: 'center', flexWrap: 'wrap' }}>
                        <Link href="/auth" className="btn btn-primary btn-lg">
                            🎯 Start for Free
                        </Link>
                        <Link href="/docs" className="btn btn-secondary btn-lg">
                            📚 View API Docs
                        </Link>
                    </div>

                    {/* Stats */}
                    <div style={{
                        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
                        gap: '24px', marginTop: '80px',
                        maxWidth: '700px', margin: '80px auto 0',
                    }}>
                        {STATS.map((stat) => (
                            <div key={stat.value} style={{ textAlign: 'center' }}>
                                <div style={{
                                    fontSize: '2rem', fontWeight: '800',
                                    background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                                    WebkitBackgroundClip: 'text',
                                    WebkitTextFillColor: 'transparent',
                                    backgroundClip: 'text',
                                    fontFamily: 'var(--font-display)',
                                }}>{stat.value}</div>
                                <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
                                    {stat.label}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Features Grid */}
            <section style={{ padding: '80px 0' }}>
                <div className="container">
                    <div style={{ textAlign: 'center', marginBottom: '60px' }}>
                        <h2>Everything You Need to Learn Faster</h2>
                        <p style={{ marginTop: '16px', fontSize: '1.1rem' }}>
                            9 powerful AI features, one simple upload
                        </p>
                    </div>
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                        gap: '24px',
                    }}>
                        {FEATURES.map((feature) => (
                            <div
                                key={feature.title}
                                className="glass-card"
                                style={{ padding: '28px' }}
                            >
                                <div className="feature-icon" style={{
                                    background: feature.color,
                                    border: `1px solid ${feature.borderColor}`,
                                }}>
                                    {feature.icon}
                                </div>
                                <h3 style={{ fontSize: '1.1rem', marginBottom: '10px' }}>{feature.title}</h3>
                                <p style={{ fontSize: '0.9rem', lineHeight: '1.6' }}>{feature.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* How it Works */}
            <section style={{ padding: '80px 0', background: 'rgba(255,255,255,0.02)' }}>
                <div className="container" style={{ textAlign: 'center' }}>
                    <h2 style={{ marginBottom: '60px' }}>
                        From Upload to <span className="gradient-text">Complete Lecture</span> in Minutes
                    </h2>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '32px' }}>
                        {[
                            { step: '01', icon: '📤', title: 'Upload PDF', desc: 'Drag & drop any PDF up to 50MB' },
                            { step: '02', icon: '⚡', title: 'AI Processes', desc: 'Our AI reads, summarizes, and indexes every page' },
                            { step: '03', icon: '🎁', title: 'Get Outputs', desc: 'Summary, quiz, flashcards, video, and more' },
                            { step: '04', icon: '💬', title: 'Chat & Learn', desc: 'Ask any question about your document' },
                        ].map((item) => (
                            <div key={item.step} className="glass-card" style={{ padding: '32px 24px' }}>
                                <div style={{
                                    fontSize: '0.75rem', color: 'var(--color-accent-1)',
                                    fontWeight: '700', letterSpacing: '0.1em',
                                    marginBottom: '16px',
                                }}>STEP {item.step}</div>
                                <div style={{ fontSize: '2.5rem', marginBottom: '16px' }}>{item.icon}</div>
                                <h3 style={{ fontSize: '1rem', marginBottom: '8px' }}>{item.title}</h3>
                                <p style={{ fontSize: '0.85rem' }}>{item.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Pricing */}
            <section style={{ padding: '80px 0' }}>
                <div className="container" style={{ textAlign: 'center' }}>
                    <h2 style={{ marginBottom: '16px' }}>Simple, Transparent Pricing</h2>
                    <p style={{ marginBottom: '60px' }}>Start free, upgrade when you need more power</p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px', maxWidth: '960px', margin: '0 auto' }}>
                        {PRICING.map((plan) => (
                            <div
                                key={plan.name}
                                className="glass-card"
                                style={{
                                    padding: '36px 28px',
                                    border: plan.highlighted ? '1px solid rgba(99, 102, 241, 0.6)' : undefined,
                                    boxShadow: plan.highlighted ? 'var(--shadow-glow-indigo)' : undefined,
                                }}
                            >
                                {plan.highlighted && (
                                    <div style={{
                                        display: 'inline-block',
                                        padding: '4px 16px',
                                        background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                                        borderRadius: '9999px',
                                        fontSize: '0.75rem', fontWeight: '700',
                                        color: '#fff', marginBottom: '16px',
                                        letterSpacing: '0.05em',
                                    }}>MOST POPULAR</div>
                                )}
                                <div style={{ fontFamily: 'var(--font-display)', fontWeight: '700', fontSize: '1.1rem', marginBottom: '8px' }}>
                                    {plan.name}
                                </div>
                                <div style={{ marginBottom: '24px' }}>
                                    <span style={{ fontSize: '2.5rem', fontWeight: '800', color: '#f1f5f9' }}>{plan.price}</span>
                                    <span style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>{plan.period}</span>
                                </div>
                                <ul style={{ listStyle: 'none', marginBottom: '28px', textAlign: 'left' }}>
                                    {plan.features.map((f) => (
                                        <li key={f} style={{ fontSize: '0.9rem', padding: '6px 0', color: 'var(--color-text-secondary)', display: 'flex', gap: '8px' }}>
                                            <span style={{ color: '#10b981' }}>✓</span> {f}
                                        </li>
                                    ))}
                                </ul>
                                <Link
                                    href="/auth"
                                    className={`btn ${plan.highlighted ? 'btn-primary' : 'btn-secondary'}`}
                                    style={{ width: '100%', justifyContent: 'center' }}
                                >
                                    {plan.cta}
                                </Link>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA Banner */}
            <section style={{ padding: '80px 0' }}>
                <div className="container">
                    <div style={{
                        background: 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))',
                        border: '1px solid rgba(99, 102, 241, 0.3)',
                        borderRadius: '28px',
                        padding: '60px',
                        textAlign: 'center',
                    }}>
                        <h2 style={{ marginBottom: '16px' }}>
                            Ready to Transform How You Learn?
                        </h2>
                        <p style={{ marginBottom: '36px', fontSize: '1.1rem' }}>
                            Join thousands of students and educators turning PDFs into interactive learning experiences.
                        </p>
                        <Link href="/auth" className="btn btn-primary btn-lg">
                            🚀 Get Started — It's Free
                        </Link>
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer style={{
                borderTop: '1px solid var(--color-border)',
                padding: '40px 0',
                textAlign: 'center',
                color: 'var(--color-text-muted)',
                fontSize: '0.85rem',
            }}>
                <div className="container">
                    <p>
                        Built with ❤️ by{' '}
                        <a href="https://github.com/MustakimShaikh01" target="_blank" rel="noopener noreferrer">
                            Mustakim Shaikh
                        </a>
                        {' '}·{' '}
                        <Link href="/docs">API Docs</Link>
                        {' '}·{' '}
                        <Link href="/privacy">Privacy</Link>
                        {' '}·{' '}
                        <Link href="/terms">Terms</Link>
                    </p>
                    <p style={{ marginTop: '8px' }}>
                        © {new Date().getFullYear()} PageTutor AI. All rights reserved.
                    </p>
                </div>
            </footer>
        </main>
    );
}
