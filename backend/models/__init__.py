"""Modelos registrados nos metadados, sem acessar o banco ou o arquivo .env."""

from backend.models.base import Base
from backend.models.emprestimo import Emprestimo, StatusEmprestimo
from backend.models.exemplar import Exemplar, StatusExemplar
from backend.models.livro import Livro
from backend.models.usuario import TipoUsuario, Usuario

__all__ = [
    "Base",
    "Livro",
    "Exemplar",
    "StatusExemplar",
    "Usuario",
    "TipoUsuario",
    "Emprestimo",
    "StatusEmprestimo",
]
