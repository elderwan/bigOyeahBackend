# FitBooking — Backend API

FastAPI + SQLAlchemy (aiomysql) backend for FitBooking platform.

## Quick Start

```bash
# 1. Activate virtual environment
.venv\Scripts\activate   # Windows

# 2. Run backend development server
uvicorn app.main:app --reload --port 8000
```

- API Base URL: `http://localhost:8000/api/v1`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Documentation

All project documentation, API references, testing guides, and database designs have been organized into the [`doc/`](./doc) directory:

- [API Reference](./doc/API_REFERENCE.md)
- [API Testing Guide](./doc/API_TESTING.md)
- [Backend Improvements & Specifications](./doc/BACKEND_IMPROVEMENT_SPECIFICATION.md)
- [Full Document Index](./doc/README.md)
