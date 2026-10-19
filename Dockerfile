# V4: imagem única dos serviços do BookNet (Catálogo, Usuários e Empréstimos).
# O mesmo código vira três contêineres; o docker-compose.yml escolhe qual serviço
# cada um executa. Construir: docker build -t booknet-servicos .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependências primeiro: enquanto requirements.txt não mudar, o Docker reaproveita
# esta camada e as reconstruções ficam rápidas.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY backend ./backend

# Os serviços não precisam de privilégios de administrador dentro do contêiner.
RUN useradd --create-home --uid 10001 booknet
USER booknet

EXPOSE 8001 8002 8003

# Padrão: Serviço de Catálogo. O compose troca o comando para os outros serviços.
CMD ["python", "-m", "uvicorn", "backend.servicos.catalogo:app", "--host", "0.0.0.0", "--port", "8001"]
