from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Caminho para o ficheiro SQLite
DATABASE_URL = "sqlite:///sistema.db"

# Criar o motor da base de dados
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Criar uma sessão
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
