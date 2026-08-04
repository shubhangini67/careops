"""One simple class : Base. Every model inherits from it. 
Alembic looks at Base.metadata to know what tables exist. 
 it is the root of the entire data layer."""

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass