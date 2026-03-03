#  PageTutor AI

> **Enterprise-Grade AI-Powered PDF Learning Platform**  
> Built by **Mustakim Shaikh** | [GitHub](https://github.com/MustakimShaikh01)

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🌟 Overview

PageTutor AI transforms any uploaded PDF into a complete learning experience:

- 📄 **Structured Summary** — AI-generated section-by-section summaries
- 🧠 **Learning Points** — Key takeaways extracted per page
- 🗂️ **Topic Segmentation** — Automatic chapter/topic detection
- 📊 **Auto-Generated PPT** — Exportable PowerPoint presentations
- 🗣️ **Multi-Language TTS** — Narration in 10+ languages
- 🎥 **Full Video Lecture** — Narrated slideshow video
- 🃏 **Flashcards** — Spaced-repetition ready cards
- 📝 **Quiz** — Auto-generated MCQ + fill-in quizzes
- 💬 **Chat-with-PDF** — Context-aware RAG Q&A

---

## 🏗️ Architecture Overview

```
                         ┌─────────────────────────────┐
                         │       Cloudflare CDN/WAF    │
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │      Load Balancer (Nginx)  │
                         └──────┬──────────────┬───────┘
                                │              │
               ┌────────────────▼─┐       ┌───▼───────────────┐
               │  Next.js SSR     │       │  FastAPI Gateway  │
               │  Frontend        │       │  (API Gateway)    │
               └──────────────────┘       └───┬───────────────┘
                                              │
              ┌───────────────────────────────┼───────────────────────┐
              │                               │                       │
      ┌───────▼──────┐              ┌─────────▼──────┐      ┌────────▼──────┐
      │  Auth Service│              │  Upload Service│      │ Rate Limiter  │
      │  (JWT/OAuth) │              │  (S3 + Hash)   │      │ (Redis)       │
      └──────────────┘              └─────────┬──────┘      └───────────────┘
                                              │
                                   ┌──────────▼──────────┐
                                   │   Job Orchestrator   │
                                   │   (Celery + Redis)   │
                                   └──────┬───────────────┘
                                          │
                   ┌──────────────────────┼──────────────────┐
                   │                      │                  │
         ┌─────────▼──────┐    ┌──────────▼──────┐  ┌───────▼──────┐
         │  LLM GPU Worker │   │ Media CPU Worker│  │ Embed Worker │
         │  (vLLM batch)   │   │  (TTS + Video)  │  │ (PageIndex)  │
         └─────────────────┘   └─────────────────┘  └──────────────┘
                   │                      │                   │
      ┌────────────┼──────────────────────┼───────────────────┼──────────┐
      │            │                      │                   │          │
  ┌───▼───┐  ┌─────▼────┐  ┌─────────────▼──┐  ┌────────────▼──┐  ┌────▼───┐
  │Postgres│ │  Qdrant  │  │   S3/MinIO     │  │    Redis      │  │  ELK   │
  │  DB    │ │ Vector DB│  │  Object Store  │  │   Cache/Queue │  │  Stack │
  └────────┘ └──────────┘  └────────────────┘  └───────────────┘  └────────┘
```

---

## 📁 Project Structure

```
pagetutor-ai/
├── backend/                    # FastAPI Backend
│   ├── app/
│   │   ├── api/               # Route handlers
│   │   │   ├── v1/
│   │   │   │   ├── auth.py
│   │   │   │   ├── upload.py
│   │   │   │   ├── jobs.py
│   │   │   │   ├── chat.py
│   │   │   │   ├── quiz.py
│   │   │   │   ├── flashcards.py
│   │   │   │   └── admin.py
│   │   ├── core/              # Core config & security
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   ├── rate_limiter.py
│   │   │   └── middleware.py
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── services/          # Business logic
│   │   ├── workers/           # Celery tasks
│   │   └── utils/             # Helpers
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                   # Next.js 14 SSR Frontend
├── workers/                    # Celery worker configs
├── infra/                      # Kubernetes + Docker configs
├── docs/                       # Swagger + Architecture docs
└── docker-compose.yml
```

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+
- Python 3.11+

### Local Development

```bash
# Clone repository
git clone https://github.com/MustakimShaikh01/pagetutor-ai
cd pagetutor-ai

# Start all services
docker-compose up -d

# Access services
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
# Admin:    http://localhost:8000/admin
```

---

## 📖 API Documentation

Full Swagger UI available at: `http://localhost:8000/docs`  
ReDoc available at: `http://localhost:8000/redoc`

---

## 👨‍💻 Author

**Mustakim Shaikh**  
GitHub: [https://github.com/MustakimShaikh01](https://github.com/MustakimShaikh01)

---

## 📄 License

MIT License © 2024 Mustakim Shaikh
# pagetutor-ai
https://github.com/MustakimShaikh01/pagetutor-ai/blob/main/asset/screencapture-localhost-3000-2026-03-03-13_34_51.png
