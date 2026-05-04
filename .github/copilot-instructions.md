# Copilot Instructions

## General Development Principles

### Code Changes
- **Minimize changes**: Only modify code that is directly relevant to the task
- **Targeted edits**: Make the smallest possible changes to achieve the goal
- **Refactoring**: Allowed when it meaningfully improves code quality, maintainability, or performance
- **Preserve behavior**: Existing functionality must not break unless explicitly requested

### Code Quality
- Write clean, readable, and idiomatic code
- Follow existing code patterns and conventions in the project
- Maintain consistent formatting with the existing codebase
- Add comments only when the code's intent is not self-evident

### Testing
- New features and modules should be covered by appropriate tests
- Bug fixes should include tests to prevent regression when applicable
- Follow project-specific testing guidelines (see backend/frontend instructions)

### Documentation
- Update relevant documentation when making functional changes
- Keep inline documentation concise and meaningful
- Document complex algorithms or non-obvious design decisions

### API Consistency
- **When modifying API endpoints** (either in backend or frontend):
  - Ensure changes are synchronized between backend implementation and frontend consumption
  - Update both sides to maintain API contract compatibility
  - Verify request/response schemas match on both ends
  - Test the complete request/response cycle after changes
- Backend API changes require corresponding frontend updates and vice versa
- Breaking API changes must be communicated and coordinated

## Project Layout

- **`/frontend`** – all frontend code
- **`/backend`** – all backend code
- **`/docs`** – all documentation
  - **`/docs/manual`** – end-user documentation
  - **`/docs/dev`** – developer documentation (architecture, API contracts, setup guides, etc.)

Do not place source code outside these directories.

## Technology Constraints

### Backend
- Python >= 3.10 (minimum version)
- FastAPI, Pydantic
- Alembic for PostgreSQL schema migrations
- No new dependencies without explicit approval

### Frontend
- Vue 3 with Material Design 3 (Google's official MD3 library)
- Vite as build tool
- No additional frameworks without explicit approval

## Docker Environment

The application runs in Docker containers. Configuration is managed via `.env` file based on `.env.example` if present.

### Networking
- Services communicate over the internal Docker Compose network
- Ports are **exposed** within the Compose network only – never published to the host unless explicitly required for development access
- External port bindings (`ports:`) must be kept to the minimum necessary

### Database
- If a database is required, use **PostgreSQL** as a dedicated Docker Compose service
- The database container is only accessible from within the Compose network – never bind its port to the host in production configurations
- **Only the backend may connect to the database.** The frontend must never communicate with the database directly, not even indirectly via a shared connection string
- Database credentials and connection URLs are managed via environment variables, never hard-coded

