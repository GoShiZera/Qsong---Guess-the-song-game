# Direcionamento do Projeto — Guess The Song

> **Guia completo para qualquer agente contribuir em qualquer fase do projeto.**
> Leia este arquivo inteiro antes de começar a trabalhar.

---

## 1. Visão Geral do Produto

**Guess The Song** — Jogo web de adivinhação musical.
- Jogador informa uma playlist pública do Spotify (via URL ou ID)
- Backend busca faixas via **Client Credentials Flow** (app-only, sem login do usuário)
- Cada faixa é matchada com a Deezer para obter preview de 30s
- Jogo: 7 tentativas por música, trecho de áudio aumenta progressivamente (0.1s → 2.5s)
- Palpite via autocomplete local (dropdown com nomes das faixas do pool)
- Validação no backend (anti-trapaça: resposta nunca exposta ao client antes da revelação)
- Resultado final: acertos/erros + detalhamento por round

**Stack:** FastAPI + HTML/CSS/JS puro (static files) + Spotify Web API (metadados) + Deezer API (áudio) + Render free tier

---

## 2. Decisões Arquiteturais Fixas

| Tópico | Decisão | Justificativa |
|--------|---------|---------------|
| **Auth Spotify** | Client Credentials Flow (app-only) | Jogador não conecta conta; playlist pública acessível sem user token |
| **Entrada playlist** | Query param `playlist_id` OU `url` (regex extrai ID) | UX simples: link direto jogável |
| **Token Spotify** | Cache em memória TTL 55min (expira em 1h) | Evita request desnecessário a `/api/token` |
| **Sessão** | Cookie assinado (`itsdangerous.TimestampSigner`, 7 dias) | Sem banco de dados; sobrevive a cold start do Render |
| **Estado de jogo** | Serializado no cookie (JSON) | Partida persiste se processo reiniciar |
| **Matching Deezer** | Fuzzy artist (`expected in found or found in expected`) + max `rank` | Evita covers/tributos; pega versão original |
| **Autocomplete** | 100% client-side via `<datalist>` nativo | Zero latência, sem round-trip backend |
| **Áudio** | Web Audio API (`AudioContext` + `AudioBufferSourceNode`) | Precisão de 0.1s impossível com `<audio>` |
| **Tentativas** | 7 fixas, durações: `[0.1, 0.2, 0.4, 0.8, 1.6, 2.0, 2.5]` | Spec imutável |
| **Anti-trapaça** | Resposta comparada só no backend; nunca enviada ao client antes da revelação | Permite futuro multiplayer |
| **Deploy** | Manual via prompt (commit → deploy Render) | Controle humano |
| **Testes** | TDD leve durante todo processo | Evita regressões graves |

---

## 3. Fluxo de Dados Completo (End-to-End)

```
1. GET /game/start?playlist_id=37i9dQZF1DXcBWIGoYBM5M
   │
   ├─► Extrai playlist_id (se veio URL: regex /playlist\/([a-zA-Z0-9]+)/)
   ├─► get_app_token() → Client Credentials (cache 55min)
   ├─► fetch_playlist_tracks(playlist_id) → paginação completa
   ├─► Extrai [{name, artist}] de cada faixa
   ├─► Para cada faixa: search_deezer(artist, name) → match validado
   ├─► Monta pool: [{name, artist, preview_url, duration_ms, deezer_id}]
   ├─► Salva pool + estado inicial no cookie (GameState)
   └─► Retorna {tracks: [{name, artist}], total: N}

2. Frontend recebe lista → popula <datalist> para autocomplete
   Jogador define rounds (opcional, default = len(pool)) → POST /round/start

3. POST /round/start
   ├─► Sorteia track do pool não jogada
   ├─► Sorteia start_offset ∈ [0, duration_ms - 2500]
   ├─► Salva current_track + start_offset + attempt=0 no cookie
   └─► Retorna {preview_url, start_time_ms, clip_duration_ms}

4. Frontend: Web Audio API toca trecho (start_time, clip_duration)
   Jogador escolhe no autocomplete → POST /round/guess {guess: "Nome da Música"}

5. POST /round/guess
   ├─► Normaliza guess e current_track.name (lower, strip, remove acentos)
   ├─► Se igual → correct=true, revela track, toca preview 30s, salva RoundResult
   ├─► Se diferente → attempt++, próximo clip_duration, salva GuessRecord
   ├─► Se attempt == 7 → esgotou, revela track, toca preview 30s, salva RoundResult
   └─► Retorna {correct, attempt, next_clip_duration?, revealed_track?, game_over?}

6. Repete 3-5 até rounds_total completos

7. GET /game/summary → retorna histórico completo para tela final
```

---

## 4. Estrutura de Arquivos (Contrato)

```
Qsong/
├── app/
│   ├── config.py              # Settings (dotenv) — PRONTO
│   ├── game_state.py          # serialize/deserialize + GameState models — PARCIAL
│   ├── main.py                # FastAPI + middleware sessão + static — PRONTO
│   ├── models.py              # Pydantic models (Track, PlaylistTrack, GameState, RoundResult, GuessRecord) — CRIAR
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py            # REMOVIDO (não usado) — pode apagar
│   │   └── game.py            # Endpoints reais — IMPLEMENTAR
│   └── services/
│       ├── __init__.py
│       ├── spotify.py         # Client Credentials + fetch playlist tracks — CRIAR
│       └── deezer.py          # search + matching logic — CRIAR
├── static/
│   ├── index.html             # SPA: entrada → jogo → resumo — CRIAR
│   ├── game.js                # Web Audio API + UI logic — CRIAR
│   └── style.css              # Tema escuro Spotify, responsivo — CRIAR
├── tests/
│   ├── test_config.py         # PRONTO
│   ├── test_game_state.py     # PRONTO
│   ├── test_spotify.py        # CRIAR (mock httpx)
│   ├── test_deezer.py         # CRIAR (matching logic)
│   └── test_game_engine.py    # CRIAR (TestClient round loop)
├── requirements.txt           # PRONTO
├── requirements-dev.txt       # PRONTO
├── .env.example               # PRONTO
├── pyproject.toml             # PRONTO (ruff, mypy, pytest)
├── .github/workflows/ci.yml   # PRONTO
├── projeto.md                 # Spec original (regras imutáveis)
└── direcionamento.md          # ESTE ARQUIVO
```

---

## 5. Models Pydantic (Criar em `app/models.py`)

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SpotifyTrack(BaseModel):
    name: str
    artist: str
    spotify_id: str
    duration_ms: int

class DeezerTrack(BaseModel):
    id: int
    title: str
    artist_name: str
    preview_url: str
    duration: int  # segundos
    rank: int

class PlayableTrack(BaseModel):
    name: str
    artist: str
    preview_url: str
    duration_ms: int
    deezer_id: int

class GameConfig(BaseModel):
    playlist_id: str
    rounds_total: Optional[int] = None  # None = usa len(pool)

class GuessRecord(BaseModel):
    attempt: int  # 1-7
    guess: str
    correct: bool
    clip_duration_ms: int

class RoundResult(BaseModel):
    track: PlayableTrack
    guesses: list[GuessRecord]
    correct: bool
    completed_at: datetime

class GameState(BaseModel):
    playlist_id: str
    pool: list[PlayableTrack]
    rounds_total: int
    round_atual: int = 0
    current_track: Optional[PlayableTrack] = None
    start_offset_ms: int = 0
    attempt: int = 0  # 0-6 (7 tentativas)
    guess_history: list[GuessRecord] = []
    round_history: list[RoundResult] = []
    created_at: datetime
    updated_at: datetime
```

---

## 6. Regras de Negócio Imutáveis (do `projeto.md`)

### Matching Spotify → Deezer
1. Busca: `artist:"{artista}" track:"{nome}"`
2. Filtro: `expected_artist.lower() in found_artist.lower() or found_artist.lower() in expected_artist.lower()`
3. Escolhe maior `rank`
4. Sem match válido → descarta silenciosamente (contar para log/debug)

### Sorteio de Áudio
- `start_offset` sorteado **uma vez por música** no `POST /round/start`
- Range: `0` a `duration_ms - 2500`
- Fixo durante todas as 7 tentativas daquela música
- Duração do clip por tentativa: `[100, 200, 400, 800, 1600, 2000, 2500]` ms

### Tentativas
- Exatamente 7 por música
- Skip = erro (consome tentativa, avança clip_duration)
- Sem pontuação numérica — só contagem acertos/erros

### Frontend Áudio
- **Obrigatório** Web Audio API
- `fetch(arrayBuffer)` → `decodeAudioData` → `AudioBufferSourceNode.start(when, offset, duration)`
- CSP: `connect-src *.dzcdn.net` (documentar no README/render.yaml)

---

## 7. Endpoints da API (Contrato)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/game/start?playlist_id=...` ou `?url=...` | Valida playlist, busca faixas, matching Deezer, cria GameState, retorna `{tracks: [{name, artist}], total}` |
| `POST` | `/round/start` | Inicia round: sorteia track + offset, retorna `{preview_url, start_time_ms, clip_duration_ms}` |
| `POST` | `/round/guess` | Body: `{guess: string}` → valida, retorna `{correct, attempt, next_clip_duration_ms?, revealed_track?, game_over?}` |
| `POST` | `/round/skip` | Mesmo efeito de guess errado |
| `GET` | `/game/summary` | Retorna `{acertos, erros, rounds: [RoundResult]}` |

---

## 8. Variáveis de Ambiente (`.env`)

```bash
SPOTIFY_CLIENT_ID=xxx
SPOTIFY_CLIENT_SECRET=xxx
SESSION_SECRET=gere-com-openssl-rand-hex-32
```

---

## 9. Comandos de Verificação (Rodar Sempre Antes de Commit)

```bash
python -m ruff check .
python -m mypy --explicit-package-bases app
python -m pytest -q
```

Todos devem passar.

---

## 10. Riscos Conhecidos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| **Dono do app sem Premium** | Alta (3 meses) | App para de funcionar | Fallback Exportify (CSV upload) — ativar só se expirar |
| **Rate limit Spotify Client Credentials** | Média | Falha ao buscar playlist | Cache token 55min; retry com backoff; log alerta |
| **Rate limit Deezer (buscas paralelas)** | Média | Matching falha/parcial | Semáforo 10 req simultâneas + retry exponencial (3x) |
| **Playlist privada/inacessível** | Baixa | Erro 404 para usuário | Validar no `/game/start`, retornar erro claro |
| **Cold start Render descarta partida** | Alta (15min inatividade) | Perde progresso | Cookie serializa GameState completo (já implementado base) |
| **CSP bloqueia fetch Deezer** | Baixa | Áudio não toca | Documentar `connect-src *.dzcdn.net` |
| **pydantic-core build falha no Windows** | Média | CI quebra | Usar wheel binário (já resolvido na Fase 0) |

---

## 11. Checklist por Fase

### Fase 1 — Spotify Service + `/game/start` ✅ PRÓXIMA
- [ ] `app/services/spotify.py`: `get_app_token()`, `fetch_playlist_tracks()`, `extract_metadata()`
- [ ] `app/models.py`: models acima
- [ ] `app/game_state.py`: expandir com `GameState` + serialização completa
- [ ] `app/routes/game.py`: `GET /game/start` (validação, busca, matching, retorna pool)
- [ ] Testes: `test_spotify.py` (mock httpx), `test_game_state.py` (GameState round-trip)

### Fase 2 — Deezer Matching
- [ ] `app/services/deezer.py`: `search_track()`, `match_spotify_to_deezer()`, semáforo + retry
- [ ] Integração em `/game/start`
- [ ] Testes: `test_deezer.py` (matching logic puro)

### Fase 3 — Game Engine
- [ ] `app/routes/game.py`: `POST /round/start`, `/round/guess`, `/round/skip`, `/game/summary`
- [ ] Lógica de tentativas, start_offset, normalização de palpite
- [ ] Testes: `test_game_engine.py` (TestClient round loop completo)

### Fase 4 — Frontend
- [ ] `static/index.html`: 3 views (entrada, jogo, resumo)
- [ ] `static/style.css`: tema Spotify, responsivo, acessível
- [ ] `static/game.js`: Web Audio API, autocomplete `<datalist>`, state machine UI

### Fase 5 — Integração
- [ ] Fluxo completo jogável manualmente
- [ ] Tela de resumo com detalhamento por round

### Fase 6 — Hardening
- [ ] Error handling global → `{error, message, code}` + toast UI
- [ ] Token refresh expirado → limpa sessão, redirect entrada
- [ ] CSP header documentado
- [ ] Acessibilidade (ARIA, contraste AA, foco visível)
- [ ] Cookie `Secure; HttpOnly; SameSite=Lax`

### Fase 7 — Testes & CI
- [ ] Coverage ≥80% serviços/core
- [ ] GitHub Actions: lint + typecheck + test em push/PR

---

## 12. Como Trabalhar Neste Projeto

1. **Leia** `projeto.md` (regras imutáveis) + este `direcionamento.md` (guia vivo)
2. **Escolha** a próxima tarefa não marcada no checklist da fase atual
3. **Implemente** com testes (TDD leve: teste falha → código → teste passa)
4. **Rode** os 3 comandos de verificação
5. **Commit** atômico por feature/teste
6. **Aguarde** prompt para deploy manual no Render

---

## 13. Para Agentes Futuros: Onde Paramos

**Última fase concluída:** Fase 0 (Setup)
- Config, middleware, sessão, rotas stub, testes base, CI passando

**Próxima tarefa:** Iniciar Fase 1 — `app/services/spotify.py` com Client Credentials Flow

**Arquivos a criar/modificar na Fase 1:**
1. `app/models.py` (novo)
2. `app/services/spotify.py` (novo)
3. `app/game_state.py` (expandir)
4. `app/routes/game.py` (implementar `/game/start`)
5. `tests/test_spotify.py` (novo)
6. `tests/test_game_state.py` (expandir para GameState)

---

## 14. Referências Rápidas

- **Spotify Client Credentials:** `POST https://accounts.spotify.com/api/token` (Basic auth client_id:secret, grant_type=client_credentials)
- **Spotify Playlist Tracks:** `GET https://api.spotify.com/v1/playlists/{id}/tracks?limit=100&offset=...` (paginação via `next`)
- **Deezer Search:** `GET https://api.deezer.com/search?q=artist:"X"+track:"Y"` (sem auth)
- **Web Audio API:** `AudioContext` → `fetch(url).arrayBuffer()` → `decodeAudioData()` → `AudioBufferSourceNode.start(0, offset, duration)`

---

*Este documento deve ser atualizado a cada fase concluída. Mantenha-o sincronizado com a realidade do código.*