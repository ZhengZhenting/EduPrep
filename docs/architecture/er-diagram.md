# Entity Relationship Diagram

Database: PostgreSQL · ORM: SQLAlchemy (`backend/models.py`) · 7 tables.

All foreign keys use `ON DELETE CASCADE`. Deleting a user cascades through
courses → pdf_files → messages / notes / memory / quiz_progress.

```mermaid
erDiagram
    USER ||--o{ COURSE : "owns"
    COURSE ||--o{ PDF_FILE : "contains"
    PDF_FILE ||--o{ MESSAGE : "has"
    PDF_FILE ||--o{ NOTE : "has"
    PDF_FILE ||--|| MEMORY : "has (1:1)"
    PDF_FILE ||--o{ QUIZ_PROGRESS : "has"

    USER {
        int id PK
        string email UK "not null, indexed"
        string name "not null"
        string password_hash "bcrypt, not null"
        datetime created_at
    }

    COURSE {
        int id PK
        int user_id FK "-> user.id, cascade"
        string title "not null"
        datetime created_at
    }

    PDF_FILE {
        int id PK
        int course_id FK "-> course.id, cascade"
        string filename "not null"
        int chunk_count "default 0"
        datetime created_at
    }

    MESSAGE {
        int id PK
        int pdf_file_id FK "-> pdf_file.id, cascade"
        string role "user / assistant"
        text content "assistant: pdf_answer only"
        string source_type "pdf / pdf+web"
        jsonb sources "{pages, urls, web_supplement}"
        datetime created_at "indexed"
    }

    NOTE {
        int id PK
        int pdf_file_id FK "-> pdf_file.id, cascade"
        string type "summary / answer / quiz_explanation"
        text content "not null"
        datetime created_at
    }

    MEMORY {
        int id PK
        int pdf_file_id FK "-> pdf_file.id, unique, cascade"
        jsonb weak_concepts "default []"
        string learning_style "default ''"
        text history_summary "default ''"
        int last_compressed_at "default 0"
        datetime updated_at "onupdate now()"
    }

    QUIZ_PROGRESS {
        int id PK
        int pdf_file_id FK "-> pdf_file.id, cascade"
        int score "not null"
        int total "not null"
        float percentage "not null"
        jsonb wrong_questions "default []"
        datetime created_at
    }
```

## Notes

- `MEMORY` is **1:1** with `PDF_FILE` (`pdf_file_id` is unique) — one conversation
  memory row per PDF.
- `MESSAGE`, `NOTE`, `QUIZ_PROGRESS` are **1:N** with `PDF_FILE`.
- `MESSAGE.sources` is a JSONB object `{pages, urls, web_supplement}`; for
  assistant rows, `content` holds the PDF answer and the web supplement lives in
  `sources.web_supplement` (see [ADR 0002](../adr/0002-llm-decided-web-search.md)).
- Ownership is always derived through the chain
  `record → pdf_file → course → user.id`; all queries are scoped by the
  authenticated user.
