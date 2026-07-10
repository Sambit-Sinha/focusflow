# =============================================================================
# database.py — Creates the database engine and session factory.
#
# This file is the bridge between Python and PostgreSQL. Nothing actually
# connects to the database when this file is imported — the connection is
# only opened when a request arrives and a route function asks for one.
#
# Three key objects created here:
#   engine       — the connection pool (manages multiple DB connections)
#   SessionLocal — a factory that produces individual DB sessions per request
#   Base         — the parent class all ORM model classes inherit from
# =============================================================================

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

# DATABASE_URL is the full connection string, e.g.:
# postgresql://neondb_owner:password@host/neondb?sslmode=require
# It tells SQLAlchemy: which database driver to use (postgresql via psycopg2),
# which server to connect to, the credentials, and any options (sslmode=require
# forces an encrypted connection — required by Neon).
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Fail immediately at startup rather than failing later mid-request.
    # A clear error is much easier to debug than a mysterious crash later.
    raise RuntimeError("DATABASE_URL is not set in .env")

# create_engine builds the connection pool.
#
# pool_pre_ping=True: before handing a connection to your code, SQLAlchemy
# sends a lightweight "SELECT 1" to check the connection is still alive.
# Without this, a connection that timed out (e.g., Neon paused and resumed)
# would be handed to your code and immediately fail. With it, stale connections
# are detected and replaced automatically.
#
# connect_args={"prepare_threshold": None}: disables PostgreSQL's server-side
# prepared statements. This is REQUIRED when using a connection pooler like
# Neon's Supavisor (Transaction mode). Prepared statements are session-scoped,
# but connection poolers recycle connections between different users — a
# prepared statement from user A could be reused incorrectly by user B.
# Setting prepare_threshold=None tells psycopg2 to never use them.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"prepare_threshold": None},
)

# SessionLocal is a class (not a session itself). Calling SessionLocal()
# creates a new database session — a unit of work that tracks all your
# database changes until you call commit() or rollback().
#
# autocommit=False: changes are NOT written to the DB until you explicitly
# call db.commit(). This gives you the chance to rollback if something fails.
#
# autoflush=False: SQLAlchemy won't automatically send pending changes to
# the DB before a query. We control this manually.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class for all ORM models (User, Task, Completion, etc.).
# When you write "class User(Base)", SQLAlchemy knows that User represents a
# database table and maps its Column definitions to actual DB columns.
Base = declarative_base()


def get_db():
    """
    Dependency function — provides a database session to FastAPI route handlers.

    FastAPI's dependency injection (Depends(get_db)) calls this function
    for every incoming request, passes the session to the route handler,
    and then automatically closes the session when the request is done.

    The try/finally pattern guarantees the session is always closed, even
    if the route handler raises an exception. Unclosed sessions waste
    database connections (connection pools have a limit).

    Usage in a route:
        def my_route(db: Session = Depends(get_db)):
            users = db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db       # hand the session to the route handler
    finally:
        db.close()     # always runs, even if an exception was raised above
