# ============================================================
# PageTutor AI - Complete System Architecture & Design
# Author: Mustakim Shaikh (https://github.com/MustakimShaikh01)
# ============================================================

# 🏗️ PageTutor AI — Complete System Architecture

**Author:** Mustakim Shaikh  
**GitHub:** https://github.com/MustakimShaikh01  
**Version:** 1.0.0

---

## 📐 Architecture Overview

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────┐
│           Cloudflare CDN + WAF                  │
│  DDoS protection, Edge caching, WAF rules        │
└──────────────────────┬──────────────────────────┘
                       │ HTTPS Only
                       ▼
┌─────────────────────────────────────────────────┐
│        Nginx Load Balancer (2 instances)         │
│  Round-robin LB · Rate limiting zones            │
│  SSL termination · Gzip compression              │
└────────┬──────────────────────────┬─────────────┘
         │                          │
         ▼                          ▼
┌─────────────────┐     ┌──────────────────────────┐
│  Next.js SSR    │     │  FastAPI Gateway          │
│  Frontend       │     │  (4 Uvicorn Workers)      │
│  (SEO optimized)│     │  Auth, Upload, Jobs, Chat │
└─────────────────┘     └──────┬───────────────────┘
                               │
              ┌────────────────┼─────────────────────┐
              │                │                      │
              ▼                ▼                      ▼
    ┌──────────────┐  ┌────────────────┐  ┌──────────────────┐
    │ Auth Service │  │  Upload Service│  │  Rate Limiter    │
    │ JWT/OAuth    │  │  S3 + Hash     │  │  Redis Sliding   │
    │ HttpOnly     │  │  Dedup         │  │  Window          │
    │ Cookie Auth  │  │  Lifecycle     │  │                  │
    └──────────────┘  └───────┬────────┘  └──────────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │   Job Orchestrator    │
                  │   (Celery + Redis)    │
                  │   Priority Queues:    │
                  │   - High (Paid)       │
                  │   - Normal            │
                  │   - Low (Free)        │
                  └──────┬────────────────┘
                         │
         ┌───────────────┼──────────────────┐
         ▼               ▼                  ▼
┌────────────────┐ ┌──────────────┐ ┌──────────────┐
│  LLM Workers   │ │ Media Workers│ │ Embed Workers│
│  (GPU-based)   │ │ (CPU-based)  │ │ (CPU/Small   │
│  vLLM + batch  │ │ TTS + Video  │ │  GPU)        │
│  Mistral 7B    │ │ PPT gen      │ │ Embeddings   │
│  4-bit quant   │ │ moviepy      │ │ PageIndex    │
└───────┬────────┘ └──────┬───────┘ └─────┬────────┘
        │                 │                │
        └─────────────────┼────────────────┘
                          │
        ┌─────────────────┼─────────────────────┐
        ▼                 ▼                      ▼
┌──────────────┐  ┌──────────────┐    ┌──────────────────┐
│  PostgreSQL  │  │   Qdrant     │    │   MinIO / S3     │
│  (Primary DB)│  │ (Vector DB)  │    │ (Object Storage) │
│  Users/Jobs  │  │ PageIndex    │    │ PDFs/PPT/Video   │
│  Documents   │  │ Embeddings   │    │ Audio/Results    │
│  Billing     │  │ 768-dim vec  │    │ 48h lifecycle    │
└──────────────┘  └──────────────┘    └──────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────┐
│              Redis (6 Databases)                       │
│  DB0: Cache    DB1: Celery Broker  DB2: Results       │
│  DB3: Rate Limiting  DB4: Sessions  DB5: Quotas       │
└──────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────┐
│         Observability Stack                          │
│  Prometheus → Grafana (metrics)                      │
│  Loki / ELK (structured logs)                        │
│  Sentry (error tracking)                             │
│  Flower (Celery monitoring)                          │
└──────────────────────────────────────────────────────┘
```

---

## 🔢 Scaling Math — 1000 Concurrent Users

### GPU Requirements

```
Problem: 1000 concurrent users
Assumption: 10% active at any moment = 100 active LLM requests

vLLM continuous batching:
- Mistral 7B 4-bit = ~4GB VRAM
- A10G GPU = 24GB VRAM
- Per GPU: 24GB / 4GB = 6 model slots
- Dynamic batching: 8 requests/batch = ~8 tokens/sec/request
- With 4 A10G GPUs: 4 × 6 × 8 = 192 concurrent LLM operations

Result: 4 A10G GPUs handle 1000 users (10% concurrency)
Cost: ~$4/hr spot × 4 = $16/hr GPU cost

GPU Reduction Strategies:
1. 4-bit quantization: Halves VRAM vs float16
2. Float16 embeddings: 768 floats × 2 bytes = 1.5KB per vector
3. Dynamic batching: Multiple requests share one GPU forward pass
4. Result caching: Identical documents share outputs (Redis TTL)
5. Off-peak scheduling: Queue free-tier jobs for off-peak hours
6. vLLM prefix caching: System prompts cached across requests
```

### Queue Depth Analysis

```
Free tier:    5 jobs/day × 70% of users = 350 jobs/day
Paid tier:   100 jobs/day × 30% of users = 300 jobs/day
Peak hour:   10% of daily jobs = 65 jobs/hour ≈ 1.1 jobs/min
Worker throughput: 4 workers × 1 job/5min = 0.8 jobs/min

Action: Scale media workers to 8 during peak hours
HPA triggers: when queue_depth > 50 → scale +2 workers
```

---

## 💾 Storage Estimation (1000 Users/Day)

```
Per PDF upload:
  - Raw PDF: 2MB average × 1000 = 2GB/day
  - PageIndex embeddings: 1.5KB/page × 50 pages = 75KB/doc
  - PPT output: 1MB average
  - Audio (TTS): 5MB for 5-min narration
  - Video: 50MB compressed (H.264 1080p, 10min)
  - Quiz/Flashcards: 50KB JSON
  - Summary: 10KB text

Total per user per job (full_pipeline):
  2MB + 75KB + 1MB + 5MB + 50MB + 0.1MB = ~58MB

1000 users × 58MB = 58GB/day gross
After 48h cleanup: only PageIndex + summaries remain
PageIndex per doc: 75KB × 1000 = 75MB/day persistent

After cleanup: ~75MB/day persistent storage
Raw storage (before cleanup): 58GB, all deleted within 48h

Estimated monthly S3 cost:
  - Storage: 75MB × 30 = 2.25GB @ $0.023/GB = $0.05/month
  - Transfer (CDN hit rate 90%): 30GB × $0.09 = $2.70/month
  - Requests: ~$1/month
Total S3: ~$4/month for 1000 users
```

---

## 💰 Monthly Cost Estimate (1000 Concurrent Users)

```
Infrastructure (AWS us-east-1):

Compute:
  API servers: 2× t3.large (autoscale 2-8) = $120/mo
  Media workers: 4× c5.2xlarge          = $400/mo
  GPU workers: 2× g5.xlarge (spot 70% saving) = $250/mo
  PostgreSQL: db.t3.large (RDS)           = $80/mo
  Redis: cache.t3.medium (ElastiCache)   = $50/mo

Storage:
  S3: ~10GB persistent + 50GB transient  = $5/mo
  RDS storage: 20GB SSD                  = $3/mo
  Qdrant: 1× r5.large (2M vectors)      = $90/mo

CDN:
  CloudFront: 500GB transfer             = $45/mo
  
Monitoring:
  Grafana Cloud Free tier + Sentry $25   = $25/mo

Total: ~$1,068/month

With spot + reserved instances (3yr):
  ~40% savings = ~$640/month for 1000 concurrent users
  = $0.64/user/month

Break-even Free Tier Cost: $0.64/user
Paid Tier Revenue ($19/mo × 300 paid): $5,700/mo
Profit: $5,700 - $1,068 = $4,632/mo (for 1000 total users)
```

---

## 🔒 Security Architecture

### Authentication Flow
```
1. User POSTs to /api/v1/auth/login
2. Backend validates credentials against bcrypt hash
3. Backend generates:
   - access_token (JWT, 60 min, HS256)
   - refresh_token (JWT, 30 days)
4. Both tokens SET as HttpOnly cookies:
   - access_token: SameSite=lax, Secure, HttpOnly, path=/
   - refresh_token: SameSite=lax, Secure, HttpOnly, path=/api/v1/auth/refresh
5. Browser automatically sends cookies on all requests
6. API extracts token from cookie (falls back to Authorization header)
7. JWT decoded → user_id extracted → DB lookup → user object
```

### Security Layers
```
Layer 1: Cloudflare WAF (DDoS, bot protection)
Layer 2: Nginx rate limiting (100 req/min per IP)
Layer 3: API Gateway JWT validation
Layer 4: FastAPI dependency injection auth (per-route)
Layer 5: ORM-level ownership checks (document.owner_id = user.id)
Layer 6: Row-level security (future PostgreSQL RLS)
```

### File Security
```
1. MIME type validation (must start with %PDF bytes)
2. SHA-256 deduplication (prevents re-upload of same content)
3. Max size: 50MB enforced at Nginx AND FastAPI
4. S3 Server-Side Encryption (AES-256)
5. Pre-signed URLs (expire in 48h) instead of public URLs
6. S3 bucket policy: deny public access
7. VPC endpoint: traffic stays within AWS network
```

---

## 📡 PageIndex Design

### Data Structure
```python
PageIndex {
    id: UUID                    # Unique per chunk
    document_id: UUID           # Parent document
    page_number: int            # Source page
    topic: str                  # Extracted heading/topic
    summary: str                # First 300 chars of page
    importance_score: float     # 0.0 - 1.0 (ML-computed)
    token_count: int            # Approximate tokens
    qdrant_point_id: UUID       # Reference to vector in Qdrant
    chunk_index: int            # 0 for page-level, 1+ for sub-chunks
    chunk_total: int            # Total chunks for this page
    meta: JSONB                 # Flexible metadata
}
```

### Chunking Strategy
```
Algorithm:
1. Extract text per page (pdfplumber)
2. Count words → estimate tokens (1 word ≈ 1.3 tokens)
3. If page ≤ 512 tokens: single chunk
4. If page > 512 tokens: split with 128-token overlap

Overlap purpose:
  - Preserves sentence context at boundaries
  - Prevents mid-sentence cuts losing meaning
  - 128-token overlap = ~1-2 sentences

Example (700-token page → 2 chunks):
  Chunk 1: tokens 0-512
  Chunk 2: tokens 384-700 (128 overlap from end of chunk 1)
```

### Hierarchical Indexing
```
Level 1: Document (metadata only, no vector)
Level 2: Page     (chunk_index=0, summary vector)
Level 3: Chunk    (chunk_index>0, detailed vectors)

RAG retrieval uses Level 3 for precision,
falls back to Level 2 for broader context.
```

---

## 🎯 SEO Strategy

### Content Strategy
```
1. Each processed document → public summary page
   URL: /learn/{slug}/{document-id}
   Content: AI-generated summary, learning points, topic list
   
2. Auto-generated blog posts via AI
   URL: /blog/how-to-learn/{topic-slug}
   
3. Public lecture directory
   URL: /lectures/[category]/[topic]
   
4. Sitemap: auto-generated, submitted to Google
   https://pagetutor.ai/sitemap.xml
```

### Technical SEO
```
- Next.js SSR: All pages fully rendered on server
- Core Web Vitals optimized: LCP < 2.5s, FID < 100ms
- Semantic HTML: h1 per page, proper heading hierarchy
- Schema.org: SoftwareApplication, LearningResource, FAQPage
- Open Graph: og:title, og:description, og:image per page
- Canonical URLs: prevent duplicate content
- robots.txt: allow all, disallow /admin, /api
- Image optimization: WebP, lazy loading, explicit dimensions
```

### Growth Strategy
```
Phase 1 (Month 1-3): SEO foundation
  - 100 AI-generated "how to learn X" blog posts
  - Optimize for "PDF summarizer AI" keywords
  - Submit to Product Hunt, HackerNews

Phase 2 (Month 4-6): Viral features
  - Public lecture share pages (shareable URLs)
  - Chrome extension (summarize any PDF in browser)
  - Free public directory of summarized textbooks

Phase 3 (Month 7-12): Platform
  - API marketplace (Rapid API listing)
  - Teacher accounts (bulk upload, class management)
  - Referral program ($5 credit per referral)
```

---

## 🛡️ Audit Logging Schema

### Log Record
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-uuid-or-null",
  "event_type": "job_created",
  "event_category": "job",
  "resource_type": "job",
  "resource_id": "job-uuid",
  "ip_address": "203.0.113.1",
  "user_agent": "Mozilla/5.0...",
  "request_id": "req-uuid",
  "details": {
    "job_type": "full_pipeline",
    "document_id": "doc-uuid",
    "priority": "normal"
  },
  "success": true,
  "error_code": null,
  "contains_pii": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Event Types
```
Authentication:
  user_registered, login_success, login_failed,
  logout, password_changed, oauth_login

Document:
  document_uploaded, document_deleted, duplicate_detected

Job:
  job_created, job_queued, job_started, job_completed,
  job_failed, job_cancelled

Inference:
  inference_start, inference_end, token_usage

Billing:
  subscription_created, payment_succeeded, payment_failed,
  subscription_cancelled

Admin:
  user_banned, role_changed, tier_changed, admin_login
```

### GDPR Compliance
```
Retention: 90 days (configurable)
Purge: Automatic daily job via Celery beat
PII Flagging: contains_pii=true for login/personal events
Right to Erasure: DELETE /admin/users/{id} cascades all logs
Data Export: GET /api/v1/user/data-export (GDPR Article 20)
```

---

## 📊 Observability Metrics

### Key Metrics
```
Prometheus counters/histograms:
  pagetutor_requests_total{method, endpoint, status}
  pagetutor_request_duration_seconds{method, endpoint}
  pagetutor_jobs_total{job_type, status}
  pagetutor_active_users_gauge
  pagetutor_queue_depth{queue_name}
  pagetutor_gpu_utilization_percent
  pagetutor_tokens_used_total{model}
  pagetutor_storage_bytes_used
  pagetutor_cost_per_request_usd
```

### Grafana Dashboards
```
Dashboard 1: User Activity
  - Active users (1h, 24h, 7d)
  - Job creation rate
  - Feature usage breakdown

Dashboard 2: System Performance
  - API latency P50/P95/P99
  - Error rate
  - Queue depth trends
  - Worker utilization

Dashboard 3: GPU/LLM
  - GPU memory usage
  - Token throughput
  - Batch size distribution
  - LLM timeout rate

Dashboard 4: Business
  - Free vs paid ratio
  - Daily job count
  - Storage consumption
  - Cost per user
```

---

## 📅 MVP Roadmap

### 8-Week MVP
```
Week 1-2: Foundation
  - [x] PostgreSQL schema + Alembic migrations
  - [x] FastAPI structure + Swagger
  - [x] JWT auth with HttpOnly cookies
  - [x] S3 upload with SHA-256 dedup
  - [x] Redis rate limiting

Week 3-4: Core AI Features
  - [x] PDF text extraction (pdfplumber)
  - [x] Embedding + Qdrant indexing
  - [x] LLM summarization (vLLM)
  - [x] Topic segmentation
  - [x] Flashcard + Quiz generation

Week 5: Media Pipeline
  - [x] PPT generation (python-pptx)
  - [x] TTS narration (Coqui TTS)
  - [x] Video generation (moviepy)
  - [x] S3 upload + pre-signed URLs

Week 6: Chat + Celery
  - [x] RAG chat with PDF
  - [x] Redis session management
  - [x] Celery worker setup
  - [x] Priority queue (free vs paid)

Week 7: Frontend + SEO
  - [x] Next.js SSR landing page
  - [x] Dashboard UI
  - [x] Upload + progress tracking
  - [x] SEO metadata + schema.org

Week 8: DevOps + Launch
  - [x] Docker Compose (all services)
  - [x] GitHub Actions CI/CD
  - [x] Nginx load balancer
  - [x] Prometheus + Grafana
  - [ ] Beta launch (Product Hunt)
```

### Phase 2 (Month 3-6)
```
- Chrome extension (one-click PDF summarize)
- Mobile app (React Native)
- Public lecture marketplace
- Teacher/classroom accounts
- Bulk upload API
- Webhook notifications
- Advanced analytics dashboard
- Multi-tenant architecture
- SAML/SSO for enterprises
```

### Phase 3 (Month 7-12)
```
- Custom AI model fine-tuning per domain
- Real-time collaborative annotations
- Integration: Notion, Google Drive, Dropbox
- White-label enterprise licensing
- Multi-GPU cluster with auto-scaling
- Global CDN edge caching for vectors
- AI-powered learning path recommendations
- Certificate of completion system
```
