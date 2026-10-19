# Serviço de Catálogo · porta 8001

**Responsabilidade:** livros, exemplares e disponibilidade. É o dono das tabelas `livros` e `exemplares`.

**Código:** [`backend/servicos/catalogo.py`](../backend/servicos/catalogo.py) e [`backend/routers/catalogo.py`](../backend/routers/catalogo.py).

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.servicos.catalogo:app --port 8001
```

Documentação interativa: http://127.0.0.1:8001/docs

| Quem chama | Rota | Para quê |
| --- | --- | --- |
| Cliente Web | `GET/POST /livros`, `GET/PUT /livros/{id}` | Pesquisar, cadastrar e alterar livros. |
| Cliente Web | `GET/POST /livros/{id}/exemplares`, `GET /exemplares/{id}` | Exemplares e disponibilidade. |
| Serviço de Empréstimos | `POST /interno/exemplares/{id}/retirada` | Reserva **atômica** do exemplar: só um pedido simultâneo vence (falha 2). |
| Serviço de Empréstimos | `POST /interno/exemplares/{id}/liberacao` | Devolução ou compensação; pode ser repetida sem efeito colateral (idempotente). |

As rotas `/interno` exigem o cabeçalho `X-Servico-Token` (variável `BOOKNET_TOKEN_INTERNO`) e respondem `403` a qualquer outro chamador.

Canal de eventos: `ws://…:8001/ws/eventos` (`livro.criado`, `livro.atualizado`, `exemplar.criado`).
