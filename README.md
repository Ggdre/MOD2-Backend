## Maintenance Dispatch Backend

Backend service for a dual-role (customer/worker) maintenance marketplace similar to Uber but focused on urgent repair work. Built with Django and Django REST Framework, it supports traditional login, Google sign-in, role-based authorization, worker availability/dispatching, and notification workflows. The project targets Render for deployment and PostgreSQL (Aiven) as the primary database.

### Features
- JWT authentication plus Google ID token sign-in
- Role-aware endpoints for customers, workers, and admins
- Worker availability, distance-based request matching, and acceptance flow
- Emergency and standard request priorities with activity history
- Admin dashboard metrics for users and requests
- In-app notifications for request lifecycle events
- OpenAPI schema (`/api/schema/`) and Swagger UI (`/api/docs/`)

### Project Structure
- `config/` – Django project configuration, settings, and routing
- `accounts/` – Custom user model, registration/login, worker availability
- `services/` – Service request models, dispatch logic, dashboard metrics
- `notifications/` – Notification model, serializers, and dispatch helpers

### Requirements
- Python 3.11+ (recommended)
- PostgreSQL 14+ (Render or Aiven managed instance)
- Google Cloud OAuth client (for customer/worker sign-in)

### Quick Start
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
cp env.example .env  # then edit with real values
python manage.py migrate
python manage.py runserver
```

### Environment Variables
Update your `.env` (or Render environment) with:

| Variable | Description |
| --- | --- |
| `DJANGO_SECRET_KEY` | Strong secret key for Django crypto |
| `DJANGO_DEBUG` | `True`/`False` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts (`localhost,127.0.0.1`) |
| `DATABASE_URL` | e.g. `postgres://avnadmin:{password}@pg-2a66ac7e-nullreverse3368-853e.k.aivencloud.com:21443/defaultdb?sslmode=require` |
| `CORS_ALLOWED_ORIGINS` | Frontend origins (`https://app.example.com`) |
| `GOOGLE_CLIENT_IDS` | Google OAuth client IDs separated by commas |
| `CORS_ALLOWED_ORIGIN_REGEXES` | Optional regex list for wildcards |
| `CORS_ALLOW_ALL_ORIGINS` | `True` to allow any origin (development only) |

### Deployment (Render)
- `render.yaml` defines a Python web service using Gunicorn (`Procfile`)
- Configure Render environment variables (especially `DATABASE_URL`, `DJANGO_SECRET_KEY`, Google client IDs)
- Ensure the PostgreSQL URL includes `sslmode=require` for Aiven-hosted instances
- Add migrations during deployment (`render` will run `python manage.py migrate` automatically if configured)

### API Highlights
- `POST /api/auth/register/` – customer/worker registration (JWT response)
- `POST /api/auth/login/` – JWT pair
- `POST /api/auth/google/` – Google ID token exchange
- `GET/PATCH /api/auth/me/` – profile management
- `PATCH /api/auth/workers/availability/` – toggle worker availability + location
- `POST /api/services/requests/` – create service request (customer only)
- `GET /api/services/requests/pending/` – worker nearby requests
- `POST /api/services/requests/{id}/accept/` – worker accept request
- `POST /api/services/requests/{id}/start/` – worker start
- `POST /api/services/requests/{id}/complete/` – worker complete
- `POST /api/services/requests/{id}/cancel/` – cancel (customer/admin/assigned worker)
- `GET /api/services/dashboard/` – admin metrics
- `GET /api/notifications/` – user notifications
- `POST /api/notifications/mark-read/` – mark read or mark all read

### Running Checks & Tests
```bash
python manage.py check
python manage.py test  # (add tests as the project grows)
```

### Next Steps
- Configure Google OAuth consent screen and download client IDs
- Integrate a real-time notification channel (Pusher, Firebase, etc.) if needed
- Add rate limiting and throttling for public endpoints
- Create frontend/mobile clients that consume the documented API

