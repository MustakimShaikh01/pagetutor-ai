/**
 * PageTutor AI - Dashboard Page
 * Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
 */

'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useDropzone } from 'react-dropzone';
import { useRouter } from 'next/navigation';

const API = 'http://localhost:8000/api/v1';

/* ── auth helper ────────────────────────────────── */
function getToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('token');
}
function authHeaders(): HeadersInit {
    const t = getToken();
    return t ? { Authorization: `Bearer ${t}` } : {};
}

/* ── types ──────────────────────────────────────── */
interface Job {
    job_id: string;
    job_type: string;
    status: 'pending' | 'queued' | 'processing' | 'completed' | 'failed';
    progress: number;
    created_at: string;
    error_message?: string;
}

const JOB_ICONS: Record<string, string> = {
    full_pipeline: '🎓',
    summarize: '📝',
    flashcards: '🃏',
    quiz: '❓',
    tts: '🔊',
    video: '🎥',
    ppt: '📊',
    chat: '💬',
    segment: '✂️',
};

const STATUS_COLOR: Record<Job['status'], string> = {
    pending: '#f59e0b',
    queued: '#818cf8',
    processing: '#06b6d4',
    completed: '#10b981',
    failed: '#ef4444',
};

/* ══════════════════════════════════════════════════
   Upload Section
═══════════════════════════════════════════════════ */
function UploadSection({ onUpload }: { onUpload: (docId: string) => void }) {
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [error, setError] = useState<string | null>(null);

    const onDrop = useCallback(async (files: File[]) => {
        const file = files[0];
        if (!file) return;
        setUploading(true); setError(null); setProgress(0);

        const tick = setInterval(() => setProgress(p => Math.min(p + 8, 85)), 200);
        try {
            const fd = new FormData();
            fd.append('file', file);
            fd.append('language', 'en');

            const res = await fetch(`${API}/upload/pdf`, {
                method: 'POST',
                headers: { ...authHeaders() },
                body: fd,
                credentials: 'include',
            });
            clearInterval(tick); setProgress(100);

            if (!res.ok) {
                const err = await res.json();
                throw new Error(
                    Array.isArray(err.detail)
                        ? err.detail.map((e: any) => e.msg).join('. ')
                        : err.detail || 'Upload failed'
                );
            }
            const data = await res.json();
            onUpload(data.document_id);
        } catch (e) {
            clearInterval(tick);
            setError(e instanceof Error ? e.message : 'Upload failed');
        } finally {
            setUploading(false);
            setTimeout(() => setProgress(0), 1500);
        }
    }, [onUpload]);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: { 'application/pdf': ['.pdf'] },
        maxFiles: 1,
        disabled: uploading,
    });

    return (
        <div>
            <div
                {...getRootProps()}
                className={`dropzone ${isDragActive ? 'active' : ''}`}
                style={{ cursor: uploading ? 'not-allowed' : 'pointer' }}
            >
                <input {...getInputProps()} />
                {uploading ? (
                    <div>
                        <div style={{ fontSize: '3rem', marginBottom: '16px' }}>⚡</div>
                        <p style={{ fontSize: '1.1rem', marginBottom: '16px', color: '#f1f5f9' }}>
                            Uploading PDF…
                        </p>
                        <div className="progress-bar" style={{ maxWidth: '300px', margin: '0 auto' }}>
                            <div className="progress-fill" style={{ width: `${progress}%` }} />
                        </div>
                        <p style={{ marginTop: '10px', fontSize: '0.85rem' }}>{progress}%</p>
                    </div>
                ) : isDragActive ? (
                    <div>
                        <div style={{ fontSize: '3rem', marginBottom: '12px' }}>📂</div>
                        <p style={{ color: 'var(--c-indigo)', fontWeight: 600 }}>Drop your PDF here!</p>
                    </div>
                ) : (
                    <div>
                        <div style={{ fontSize: '4rem', marginBottom: '16px' }}>📄</div>
                        <h3 style={{ marginBottom: '12px' }}>Upload a PDF to Get Started</h3>
                        <p style={{ marginBottom: '20px', fontSize: '0.95rem' }}>
                            Drag & drop or click to browse
                        </p>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap' }}>
                            {['Max 50 MB', '500 pages', 'Any language'].map(t => (
                                <span key={t} className="upload-tag">{t}</span>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {error && (
                <div className="dash-error">⚠️ {error}</div>
            )}
        </div>
    );
}

/* ══════════════════════════════════════════════════
   Job Card
═══════════════════════════════════════════════════ */
function JobCard({ job }: { job: Job }) {
    const icon = JOB_ICONS[job.job_type] ?? '📄';
    const color = STATUS_COLOR[job.status] ?? '#94a3b8';
    const label = job.job_type.replace(/_/g, ' ');

    return (
        <div className="job-card">
            <div className="job-card-left">
                <span className="job-icon">{icon}</span>
                <div>
                    <div className="job-title">{label}</div>
                    <div className="job-time">{new Date(job.created_at).toLocaleString()}</div>
                    {job.status === 'failed' && job.error_message && (
                        <div className="job-error-msg">⚠ {job.error_message}</div>
                    )}
                </div>
            </div>

            <div className="job-card-right">
                <span className="job-status-badge" style={{ background: `${color}22`, color, border: `1px solid ${color}55` }}>
                    {job.status === 'processing' && <span className="dot-pulse" />}
                    {job.status}
                </span>

                {(job.status === 'queued' || job.status === 'processing') && (
                    <div style={{ marginTop: '6px', width: '120px' }}>
                        <div className="progress-bar">
                            <div className="progress-fill" style={{ width: `${job.progress}%` }} />
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', marginTop: '3px', textAlign: 'right' }}>
                            {job.progress}%
                        </div>
                    </div>
                )}

                {job.status === 'completed' && (
                    <Link href={`/results/${job.job_id}`} className="btn btn-primary btn-sm" style={{ marginTop: '6px' }}>
                        View →
                    </Link>
                )}
            </div>
        </div>
    );
}

/* ══════════════════════════════════════════════════
   Dashboard Page
═══════════════════════════════════════════════════ */
export default function DashboardPage() {
    const router = useRouter();
    const [jobs, setJobs] = useState<Job[]>([]);
    const [uploadedDocId, setDoc] = useState<string | null>(null);
    const [creatingJob, setCreating] = useState(false);
    const [jobError, setJobError] = useState<string | null>(null);
    const [user, setUser] = useState<any>(null);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    /* ── fetch user profile ─ */
    useEffect(() => {
        const token = getToken();
        if (!token) { router.push('/auth'); return; }
        fetch(`${API}/auth/me`, { headers: authHeaders() })
            .then(r => r.ok ? r.json() : null)
            .then(d => d && setUser(d))
            .catch(() => { });
    }, [router]);

    /* ── fetch existing jobs ─ */
    useEffect(() => {
        fetch(`${API}/jobs/`, { headers: authHeaders() })
            .then(r => r.ok ? r.json() : [])
            .then(d => setJobs(Array.isArray(d) ? d : []))
            .catch(() => { });
    }, []);

    /* ── live-poll active jobs every 3 s ─ */
    useEffect(() => {
        const poll = async () => {
            setJobs(prev => {
                const active = prev.filter(j => j.status === 'queued' || j.status === 'processing');
                if (!active.length) return prev;
                // fire requests but update state asynchronously
                Promise.all(
                    active.map(j =>
                        fetch(`${API}/jobs/${j.job_id}`, { headers: authHeaders() })
                            .then(r => r.ok ? r.json() : null)
                            .catch(() => null)
                    )
                ).then(results => {
                    setJobs(current =>
                        current.map(j => {
                            const fresh = results.find(r => r?.job_id === j.job_id);
                            return fresh ? { ...j, ...fresh } : j;
                        })
                    );
                });
                return prev;
            });
        };

        pollRef.current = setInterval(poll, 3000);
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, []);

    /* ── create job ─ */
    const createJob = async () => {
        if (!uploadedDocId) return;
        setCreating(true); setJobError(null);
        try {
            const res = await fetch(`${API}/jobs/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                credentials: 'include',
                body: JSON.stringify({ document_id: uploadedDocId, job_type: 'full_pipeline', language: 'en' }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to create job');
            }
            const job = await res.json();
            setJobs(prev => [job, ...prev]);
            setDoc(null);
        } catch (e) {
            setJobError(e instanceof Error ? e.message : 'Job creation failed');
        } finally {
            setCreating(false);
        }
    };

    /* ── logout ─ */
    const logout = () => {
        localStorage.removeItem('token');
        router.push('/auth');
    };

    /* ── render ─ */
    const activeJobs = jobs.filter(j => j.status === 'queued' || j.status === 'processing');

    return (
        <main className="dash-root">
            {/* Navbar */}
            <nav className="navbar">
                <div className="container flex items-center justify-between">
                    <Link href="/" className="dash-brand">
                        <div className="dash-brand-icon">🎓</div>
                        <span>PageTutor AI</span>
                    </Link>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        {user && (
                            <span className="dash-user-chip">
                                👤 {user.full_name || user.email}
                                <span className="tier-tag">{user.tier}</span>
                            </span>
                        )}
                        <Link href="/logs" className="btn btn-secondary btn-sm">
                            📋 Logs
                        </Link>
                        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
                            API Docs
                        </a>
                        <button className="btn btn-secondary btn-sm" onClick={logout}>
                            Logout
                        </button>
                    </div>
                </div>
            </nav>

            <div className="container dash-content">

                {/* Welcome row */}
                <div className="dash-welcome">
                    <div>
                        <h1>Welcome back{user ? `, ${user.full_name?.split(' ')[0]}` : ''}! 👋</h1>
                        <p>Upload a PDF and let AI turn it into a full learning course.</p>
                    </div>
                    {activeJobs.length > 0 && (
                        <div className="dash-active-badge">
                            <span className="dot-pulse small" />
                            {activeJobs.length} job{activeJobs.length > 1 ? 's' : ''} in progress
                        </div>
                    )}
                </div>

                <div className="dash-grid">
                    {/* Left — upload + create */}
                    <div>
                        <div className="dash-section-card">
                            <h2 className="dash-section-title">📤 Upload PDF</h2>
                            <UploadSection onUpload={setDoc} />

                            {uploadedDocId && (
                                <div className="doc-ready-row">
                                    <div className="doc-ready-info">
                                        <span className="doc-ready-dot" />
                                        <span>PDF ready — <code>{uploadedDocId.slice(0, 8)}…</code></span>
                                    </div>
                                    <button
                                        className="btn btn-primary"
                                        onClick={createJob}
                                        disabled={creatingJob}
                                        style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
                                    >
                                        {creatingJob ? <><span className="spinner-sm" /> Processing…</> : '🚀 Start Full Pipeline'}
                                    </button>
                                    {jobError && <div className="dash-error">{jobError}</div>}
                                </div>
                            )}
                        </div>

                        {/* Feature list */}
                        <div className="dash-section-card" style={{ marginTop: '24px' }}>
                            <h2 className="dash-section-title">✨ What You Get</h2>
                            <div className="features-grid">
                                {[
                                    ['📝', 'AI Summary', 'Concise structured summary'],
                                    ['🃏', 'Flashcards', 'Study cards for quick revision'],
                                    ['❓', 'Quiz', 'Auto-generated MCQ questions'],
                                    ['🔊', 'TTS Audio', 'Multi-language narration'],
                                    ['🎥', 'Video Lecture', 'Animated video from PDF'],
                                    ['📊', 'PowerPoint', 'Presentation-ready slides'],
                                ].map(([icon, title, desc]) => (
                                    <div key={title as string} className="feature-chip">
                                        <span>{icon}</span>
                                        <div>
                                            <div className="feature-chip-title">{title}</div>
                                            <div className="feature-chip-desc">{desc}</div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Right — jobs */}
                    <div className="dash-section-card">
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
                            <h2 className="dash-section-title" style={{ marginBottom: 0 }}>🕐 Recent Jobs</h2>
                            <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                                Auto-refreshes every 3s
                            </span>
                        </div>

                        {jobs.length === 0 ? (
                            <div className="jobs-empty">
                                <div style={{ fontSize: '3rem', marginBottom: '12px' }}>📭</div>
                                <p>No jobs yet. Upload a PDF above to start!</p>
                            </div>
                        ) : (
                            <div className="jobs-list">
                                {jobs.map(j => <JobCard key={j.job_id} job={j} />)}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </main>
    );
}
