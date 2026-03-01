/**
 * PageTutor AI - Next.js App Layout
 * Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
 *
 * Root layout with:
 * - SEO metadata
 * - Open Graph tags
 * - Schema.org structured data
 * - Site navigation
 * - Toast notifications
 */

import type { Metadata, Viewport } from 'next';
import { Toaster } from 'react-hot-toast';
import '../styles/globals.css';

// ============================================================
// SEO Metadata
// ============================================================
export const metadata: Metadata = {
    metadataBase: new URL('https://pagetutor.ai'),
    title: {
        default: 'PageTutor AI — Turn Any PDF Into a Complete Learning Course',
        template: '%s | PageTutor AI',
    },
    description:
        'PageTutor AI transforms any PDF into structured summaries, interactive quizzes, flashcards, TTS narration, video lectures, and AI chat. Build by Mustakim Shaikh.',
    keywords: [
        'AI PDF summarizer',
        'PDF to video lecture',
        'AI flashcard generator',
        'PDF quiz generator',
        'chat with PDF',
        'AI learning platform',
        'PDF to PPT',
        'multilingual TTS',
        'PageTutor AI',
    ],
    authors: [{ name: 'Mustakim Shaikh', url: 'https://github.com/MustakimShaikh01' }],
    creator: 'Mustakim Shaikh',
    publisher: 'PageTutor AI',

    // Open Graph (rich social previews)
    openGraph: {
        type: 'website',
        locale: 'en_US',
        url: 'https://pagetutor.ai',
        siteName: 'PageTutor AI',
        title: 'PageTutor AI — AI-Powered PDF Learning Platform',
        description: 'Transform any PDF into summaries, quizzes, flashcards, TTS, and video lectures.',
        images: [
            {
                url: '/og-image.png',
                width: 1200,
                height: 630,
                alt: 'PageTutor AI — Turn any PDF into a complete learning course',
            },
        ],
    },

    // Twitter Card
    twitter: {
        card: 'summary_large_image',
        site: '@pagetutor_ai',
        creator: '@MustakimShaikh',
        title: 'PageTutor AI — AI-Powered PDF Learning',
        description: 'Transform any PDF into summaries, quizzes, flashcards, TTS, and video lectures.',
        images: ['/og-image.png'],
    },

    // Canonical
    alternates: {
        canonical: 'https://pagetutor.ai',
    },

    // Robots
    robots: {
        index: true,
        follow: true,
        googleBot: {
            index: true,
            follow: true,
            'max-video-preview': -1,
            'max-image-preview': 'large',
            'max-snippet': -1,
        },
    },
};

export const viewport: Viewport = {
    themeColor: '#6366f1',
    colorScheme: 'dark',
    width: 'device-width',
    initialScale: 1,
};

// ============================================================
// Root Layout
// ============================================================
export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en" suppressHydrationWarning>
            <head>
                {/* Preconnect for performance */}
                <link rel="preconnect" href="https://fonts.googleapis.com" />
                <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />

                {/* Schema.org: SoftwareApplication structured data */}
                <script
                    type="application/ld+json"
                    dangerouslySetInnerHTML={{
                        __html: JSON.stringify({
                            '@context': 'https://schema.org',
                            '@type': 'SoftwareApplication',
                            name: 'PageTutor AI',
                            description:
                                'AI-powered platform that transforms PDFs into summaries, quizzes, flashcards, narration, and video lectures.',
                            url: 'https://pagetutor.ai',
                            applicationCategory: 'EducationApplication',
                            operatingSystem: 'Web',
                            offers: {
                                '@type': 'Offer',
                                price: '0',
                                priceCurrency: 'USD',
                                description: 'Free tier available',
                            },
                            author: {
                                '@type': 'Person',
                                name: 'Mustakim Shaikh',
                                url: 'https://github.com/MustakimShaikh01',
                            },
                            featureList: [
                                'PDF Summarization',
                                'Quiz Generation',
                                'Flashcard Creation',
                                'Text-to-Speech Narration',
                                'Video Lecture Generation',
                                'Chat with PDF (RAG)',
                                'PowerPoint Export',
                                'Multi-language Support',
                            ],
                        }),
                    }}
                />

                {/* Favicon */}
                <link rel="icon" href="/favicon.ico" />
                <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
            </head>
            <body>
                {/* Background grid pattern */}
                <div className="bg-grid" aria-hidden="true" />

                {/* Main content */}
                <div id="root" style={{ position: 'relative', zIndex: 1 }}>
                    {children}
                </div>

                {/* Toast notifications (top-right) */}
                <Toaster
                    position="top-right"
                    toastOptions={{
                        duration: 4000,
                        style: {
                            background: 'rgba(15, 15, 35, 0.95)',
                            backdropFilter: 'blur(20px)',
                            border: '1px solid rgba(255, 255, 255, 0.1)',
                            color: '#f1f5f9',
                            borderRadius: '12px',
                            fontSize: '0.9rem',
                        },
                        success: {
                            iconTheme: { primary: '#10b981', secondary: '#fff' },
                        },
                        error: {
                            iconTheme: { primary: '#ef4444', secondary: '#fff' },
                        },
                    }}
                />
            </body>
        </html>
    );
}
