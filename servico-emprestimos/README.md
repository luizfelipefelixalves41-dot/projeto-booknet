# Serviço de Empréstimos · porta 8003

**Responsabilidade:** empréstimos e devoluções. É o dono da tabela `emprestimos` e o único serviço que **conversa com os outros dois**.

**Código:** [`backend/servicos/emprestimos.py`](../backend/servicos/emprestimos.py), [`backend/routers/emprestimos.py`](../backend/routers/emprestimos.py) e [`backend/servicos_remotos.py`](../backend/servicos_remotos.py) (cliente HTTP com timeout).

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.servicos.emprestimos:app --port 8003
```

Documentação interativa: http://127.0.0.1:8003/docs

| Rota | Comportamento |
| --- | --- |
| `GET /emprestimos` | Lista os empréstimos, com filtros `usuario_id`, `status` e `atrasados`. Funciona mesmo com Usuários e Catálogo fora do ar. |
| `GET /emprestimos/{id}` | Consulta um empréstimo. |
| `POST /emprestimos` | Saga: consulta Usuários → confere limites → retira o exemplar no Catálogo → grava. Se a gravação falhar, compensa liberando o exemplar. |
| `POST /emprestimos/{id}/devolucao` | Marca a devolução e pede ao Catálogo a liberação do exemplar. Se o Catálogo não responder, nada é gravado e a devolução pode ser repetida. |

Endereços dos outros serviços: `BOOKNET_URL_USUARIOS` (padrão `http://127.0.0.1:8002`) e `BOOKNET_URL_CATALOGO` (padrão `http://127.0.0.1:8001`). O tempo limite de cada chamada é `BOOKNET_TIMEOUT_SERVICOS` (padrão 3 segundos).

Canal de eventos: `ws://…:8003/ws/eventos` (`emprestimo.criado`, `emprestimo.devolvido`).
