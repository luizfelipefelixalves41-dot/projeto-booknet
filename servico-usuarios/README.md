# Serviço de Usuários · porta 8002

**Responsabilidade:** alunos e bibliotecários. É o dono da tabela `usuarios`.

**Código:** [`backend/servicos/usuarios.py`](../backend/servicos/usuarios.py) e [`backend/routers/usuarios.py`](../backend/routers/usuarios.py).

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.servicos.usuarios:app --port 8002
```

Documentação interativa: http://127.0.0.1:8002/docs

| Quem chama | Rota | Para quê |
| --- | --- | --- |
| Cliente Web | `GET/POST /usuarios`, `PUT /usuarios/{id}` | Pesquisar, cadastrar e alterar usuários. |
| Cliente Web e Serviço de Empréstimos | `GET /usuarios/{id}` | Consultar um usuário. Empréstimos usa essa rota para saber se o usuário existe e está ativo. |

Canal de eventos: `ws://…:8002/ws/eventos` (`usuario.criado`, `usuario.atualizado`).
