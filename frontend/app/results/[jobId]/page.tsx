/**
 * PageTutor AI — Job Results Page
 * /results/[jobId]
 */
'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, useParams } from 'next/navigation';

const API = 'http://localhost:8000/api/v1';

function getToken() {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('token');
}
function authH(): HeadersInit {
    const t = getToken();
    return t ? { Authorization: `Bearer ${t}` } : {};
}

/* ── types ── */
interface JobResult {
    job_id: string;
    document_id: string;
    summary?: string;
    learning_points?: string[];
    segments?: any[];
    flashcards?: any[];
    quiz?: any[];
    ppt_url?: string;
    audio_url?: string;
    video_url?: string;
}

interface JobStatus {
    job_id: string;
    job_type: string;
    status: string;
    progress: number;
    created_at: string;
    completed_at?: string;
    error_message?: string;
}

/* ── Lightweight markdown renderer ── */
function renderMarkdown(text: string): string {
    return text
        // ### Heading 3 → <h3>
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        // ## Heading 2 → <h2>
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        // # Heading 1 → <h1>
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        // **bold** → <strong>
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        // *italic* → <em>
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        // `code` → <code>
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // bullet points
        .replace(/^[•\-\*] (.+)$/gm, '<li>$1</li>')
        // double newline → paragraph break
        .replace(/\n\n/g, '</p><p>')
        // wrap in paragraph
        .replace(/^(?!<[hli])(.+)$/gm, (m) => m.trim() ? m : '')
        .trim();
}

/* ── helpers ── */
function Section({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
    return (
        <div className="result-section">
            <h2 className="result-section-title">{icon} {title}</h2>
            {children}
        </div>
    );
}

/* ══════════════════════════════ */
export default function ResultsPage() {
    const router = useRouter();
    const params = useParams();
    const jobId = params?.jobId as string;

    const [job, setJob] = useState<JobStatus | null>(null);
    const [result, setResult] = useState<JobResult | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [activeTab, setActiveTab] = useState('summary');
    const [flipped, setFlipped] = useState<Record<number, boolean>>({});

    useEffect(() => {
        if (!jobId) return;
        const token = getToken();
        if (!token) { router.push('/auth'); return; }
        loadData();
    }, [jobId]);

    const loadData = async () => {
        setLoading(true);
        try {
            // Get job status
            const sjob = await fetch(`${API}/jobs/${jobId}`, { headers: authH() });
            if (!sjob.ok) throw new Error('Job not found');
            const jobData = await sjob.json();
            setJob(jobData);

            if (jobData.status === 'completed') {
                const sr = await fetch(`${API}/jobs/${jobId}/result`, { headers: authH() });
                if (sr.ok) {
                    setResult(await sr.json());
                }
            }
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const tabs = [
        { id: 'summary', label: '📝 Summary' },
        { id: 'points', label: '💡 Key Points' },
        { id: 'flashcards', label: '🃏 Flashcards' },
        { id: 'quiz', label: '❓ Quiz' },
    ];

    /* ── loading ── */
    if (loading) return (
        <div className="results-loading">
            <div className="results-spinner" />
            <p>Loading results…</p>
        </div>
    );

    /* ── error ── */
    if (error) return (
        <div className="results-error-page">
            <div style={{ fontSize: '4rem' }}>😕</div>
            <h2>Couldn't load results</h2>
            <p>{error}</p>
            <Link href="/dashboard" className="btn btn-primary">← Back to Dashboard</Link>
        </div>
    );

    /* ── job not complete ── */
    if (job && job.status !== 'completed') return (
        <div className="results-error-page">
            <div style={{ fontSize: '4rem' }}>
                {job.status === 'failed' ? '❌' : '⏳'}
            </div>
            <h2>
                {job.status === 'failed' ? 'Job Failed' :
                    job.status === 'processing' ? `Processing… ${job.progress}%` :
                        'Job Queued'}
            </h2>
            {job.status === 'failed' && <p className="result-error-detail">{job.error_message}</p>}
            {job.status !== 'failed' && (
                <>
                    <div className="results-progress-bar">
                        <div className="results-progress-fill" style={{ width: `${job.progress}%` }} />
                    </div>
                    <p style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', marginTop: '12px' }}>
                        This page auto-refreshes. Come back in a few seconds.
                    </p>
                    <button className="btn btn-secondary" onClick={loadData} style={{ marginTop: '16px' }}>
                        🔄 Refresh Now
                    </button>
                </>
            )}
            <Link href="/dashboard" className="btn btn-secondary" style={{ marginTop: '8px' }}>
                ← Dashboard
            </Link>
        </div>
    );

    if (!result) return (
        <div className="results-error-page">
            <div style={{ fontSize: '4rem' }}>📭</div>
            <h2>No results available</h2>
            <Link href="/dashboard" className="btn btn-primary">← Dashboard</Link>
        </div>
    );

    /* ── results ── */
    return (
        <div className="results-root">
            {/* Navbar */}
            <nav className="navbar">
                <div className="container flex items-center justify-between">
                    <Link href="/dashboard" className="dash-brand">
                        <div className="dash-brand-icon">🎓</div>
                        <span>PageTutor AI</span>
                    </Link>
                    <div className="flex gap-2 items-center">
                        <Link href="/dashboard" className="btn btn-secondary btn-sm">← Dashboard</Link>
                        <Link href="/logs" className="btn btn-secondary btn-sm">📋 Logs</Link>
                    </div>
                </div>
            </nav>

            <div className="container results-content">
                {/* Header */}
                <div className="results-header">
                    <div>
                        <div className="results-badge">✅ Completed</div>
                        <h1>Job Results</h1>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', marginTop: 6 }}>
                            Job ID: <code className="job-id-code">{jobId}</code>
                            {job?.completed_at && (
                                <> · Finished: {new Date(job.completed_at).toLocaleString()}</>
                            )}
                        </p>
                    </div>
                </div>

                {/* Tab bar */}
                <div className="results-tabs">
                    {tabs.map(t => (
                        <button
                            key={t.id}
                            className={`results-tab ${activeTab === t.id ? 'active' : ''}`}
                            onClick={() => setActiveTab(t.id)}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>

                {/* Tab content */}
                <div className="results-body">

                    {/* ── Summary ── */}
                    {activeTab === 'summary' && (
                        <Section icon="📝" title="AI Summary">
                            {result.summary ? (
                                <div
                                    className="result-markdown"
                                    dangerouslySetInnerHTML={{ __html: '<p>' + renderMarkdown(result.summary) + '</p>' }}
                                />
                            ) : (
                                <p className="result-empty">No summary generated.</p>
                            )}

                            {result.learning_points && result.learning_points.length > 0 && (
                                <div style={{ marginTop: 24 }}>
                                    <h3 className="result-sub-title">💡 Key Learning Points</h3>
                                    <ul className="result-points-list">
                                        {result.learning_points.map((pt, i) => (
                                            <li key={i} className="result-point">{pt}</li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </Section>
                    )}

                    {/* ── Key Points standalone ── */}
                    {activeTab === 'points' && (
                        <Section icon="💡" title="Key Learning Points">
                            {result.learning_points && result.learning_points.length > 0 ? (
                                <ul className="result-points-list">
                                    {result.learning_points.map((pt, i) => (
                                        <li key={i} className="result-point">
                                            <span className="point-num">{i + 1}</span>
                                            {pt}
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="result-empty">No learning points available.</p>
                            )}
                        </Section>
                    )}

                    {/* ── Flashcards ── */}
                    {activeTab === 'flashcards' && (
                        <Section icon="🃏" title="Flashcards">
                            {result.flashcards && result.flashcards.length > 0 ? (
                                <div className="flashcards-grid">
                                    {result.flashcards.map((card: any) => (
                                        <div
                                            key={card.card_id}
                                            className={`flashcard ${flipped[card.card_id] ? 'flipped' : ''}`}
                                            onClick={() => setFlipped(f => ({ ...f, [card.card_id]: !f[card.card_id] }))}
                                        >
                                            <div className="flashcard-inner">
                                                <div className="flashcard-front">
                                                    <span className="card-label">Q</span>
                                                    <p>{card.front}</p>
                                                    {card.topic && <span className="card-topic">{card.topic}</span>}
                                                </div>
                                                <div className="flashcard-back">
                                                    <span className="card-label">A</span>
                                                    <p>{card.back}</p>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p className="result-empty">No flashcards generated.</p>
                            )}
                            <p className="result-hint">💡 Click a card to flip it</p>
                        </Section>
                    )}

                    {/* ── Quiz ── */}
                    {activeTab === 'quiz' && (
                        <Section icon="❓" title="Quiz Questions">
                            {result.quiz && result.quiz.length > 0 ? (
                                <div className="quiz-list">
                                    {result.quiz.map((q: any, idx: number) => (
                                        <div key={q.question_id} className="quiz-card">
                                            <div className="quiz-q">
                                                <span className="quiz-num">Q{idx + 1}</span>
                                                {q.question}
                                            </div>
                                            {q.options && (
                                                <ul className="quiz-options">
                                                    {q.options.map((opt: string, i: number) => (
                                                        <li
                                                            key={i}
                                                            className={`quiz-option ${opt.startsWith(q.correct_answer) ? 'correct' : ''}`}
                                                        >
                                                            {opt}
                                                            {opt.startsWith(q.correct_answer) && (
                                                                <span className="correct-tag">✓ Correct</span>
                                                            )}
                                                        </li>
                                                    ))}
                                                </ul>
                                            )}
                                            {q.explanation && (
                                                <p className="quiz-explanation">💬 {q.explanation}</p>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p className="result-empty">No quiz questions generated.</p>
                            )}
                        </Section>
                    )}

                </div>
            </div>
        </div>
    );
}
