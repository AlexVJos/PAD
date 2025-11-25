# Microservices Library Platform

This repository refactors the original monolithic Django application into a microservices-based architecture while preserving the template-driven UI. The system now consists of six independently deployable services:

| Service | Stack | Responsibility |
| --- | --- | --- |
| `gateway` | Django + templates | Authentication, HTML UI, orchestration |
| `user-service` | FastAPI + SQLModel | User registration and JWT authentication |
| `catalog-service` | FastAPI + SQLModel | Book catalog CRUD and inventory updates |
| `loan-service` | FastAPI + SQLModel | Loan lifecycle, catalog coordination, event publication |
| `notification-service` | FastAPI + SQLModel | Asynchronous notification log fed by RabbitMQ |
| `analytics-service` | FastAPI + SQLModel | Aggregated KPIs updated from RabbitMQ events |

RabbitMQ acts as the shared message broker. Synchronous calls happen over HTTP, while cross-cutting concerns (notifications, analytics, future automation) are fulfilled through the `loan.created` and `loan.returned` events emitted by the loan service.

## Running locally

```bash
docker compose up --build
```

Published ports:

- `8000` – Django gateway
- `8001` – User API
- `8002` – Catalog API
- `8003` – Loan API
- `8004` – Notification API
- `8005` – Analytics API
- `5672` / `15672` – RabbitMQ (AMQP / management UI)

Environment variables can override each service URL; see `PAD/settings.py` and `docker-compose.yaml` for defaults.

## Service APIs (highlights)

- **User Service**
  - `POST /users/` – register
  - `POST /auth/login` – returns JWT + profile
  - `GET /users/{id}` – fetch profile

- **Catalog Service**
  - `GET /books/?search=` – list & filter
  - `POST /books/` / `PUT /books/{id}` / `DELETE /books/{id}`
  - `POST /books/{id}/reserve|release` – inventory adjustments

- **Loan Service**
  - `GET /loans/?user_id=` – per-user view for UI
  - `POST /loans/` – create loan (checks catalog sync)
  - `POST /loans/{id}/return` – return (validates user)
  - Emits `loan.created` / `loan.returned` events via RabbitMQ

- **Notification & Analytics Services**
  - Background consumers that subscribe to the topic exchange `library.events`
  - REST endpoints expose notification history and KPI summaries for the UI

## UI Gateway

The Django app now functions purely as an orchestrating gateway:

- Forms delegate to the relevant microservice over HTTP via `core/clients.py`
- Session authentication relies on the user service; Django stores a mirrored, passwordless user to keep `LoginRequiredMixin` working with templates
- `templates/` are unchanged stylistically, but data now comes from the downstream APIs

## Development tips

- Update dependencies through the shared `requirements.txt`
- When developing a single service outside Docker, run `uvicorn services.<service>.app:app --reload --port <port>`
- Use the RabbitMQ management UI (`http://localhost:15672`) to inspect event traffic when debugging asynchronous flows

## Testing the flow

1. Start the stack with `docker compose up --build`
2. Visit `http://localhost:8000`
3. Register a user (handled by `user-service`)
4. Add books (catalog service)
5. Borrow/return books; observe notifications and analytics counters update without page refresh via message-driven consumers

This structure satisfies the requirements for service isolation, per-service data stores, asynchronous communication, and template-driven UI. Extend the pattern with new services by following the `services/<name>` blueprint and wiring them through the gateway and message broker.

