import re
from typing import Any
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import as_declarative, declared_attr

@as_declarative()
class Base:
    id: Any
    __name__: str
    
    # Generate __tablename__ automatically in snake_case (e.g. UserRole -> user_role)
    @declared_attr
    def __tablename__(cls) -> str:
        return re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
