from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Delegacao(Base):
    __tablename__ = 'delegacoes'
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    denuncias = relationship("Denuncia", back_populates="delegacao")

class TipoDenuncia(Base):
    __tablename__ = 'tipos_denuncia'
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    denuncias = relationship("Denuncia", back_populates="tipo")

class Denuncia(Base):
    __tablename__ = 'denuncias'
    id = Column(Integer, primary_key=True)
    tipo_id = Column(Integer, ForeignKey('tipos_denuncia.id'), nullable=False)
    delegacao_id = Column(Integer, ForeignKey('delegacoes.id'), nullable=False)
    descricao = Column(Text, nullable=False)
    data_submissao = Column(Date, nullable=False)
    codigo = Column(String(20), unique=True, nullable=False)
    tipo = relationship("TipoDenuncia", back_populates="denuncias")
    delegacao = relationship("Delegacao", back_populates="denuncias")

class TipoReclamacao(Base):
    __tablename__ = 'tipos_reclamacao'
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    reclamacoes = relationship("Reclamacao", back_populates="tipo")

class Reclamacao(Base):
    __tablename__ = 'reclamacoes'
    id = Column(Integer, primary_key=True)
    tipo_id = Column(Integer, ForeignKey('tipos_reclamacao.id'), nullable=False)
    delegacao_id = Column(Integer, ForeignKey('delegacoes.id'), nullable=False)
    descricao = Column(Text, nullable=False)
    data_submissao = Column(Date, nullable=False)
    codigo = Column(String(20), unique=True, nullable=False)
    tipo = relationship("TipoReclamacao", back_populates="reclamacoes")
    delegacao = relationship("Delegacao")

class Colaborador(Base):
    __tablename__ = 'colaboradores'
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    email = Column(String(100), nullable=True)
    telefone = Column(String(20), nullable=True)
    funcao = Column(String(100), nullable=True)
    delegacao_id = Column(Integer, ForeignKey('delegacoes.id'))
    delegacao = relationship("Delegacao")

from database import engine
Base.metadata.create_all(bind=engine)
