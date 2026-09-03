# codex-api-server

Docker Compose でそのまま起動できる、自分たち専用の「FastAPI + OpenAI Codex Python SDK API Server」です。

複数ユーザーからの利用を前提とし、APIクライアント認証は単一の環境変数APIキーではなく、SQLite + `client_id` + 複数APIキー + 監査ログで管理します。

---

## Architecture

```text
Client
→ Bearer API Key
→ FastAPI
→ SQLite auth/audit
→ Codex SDK
→ ChatGPT
```

```text
LAN Client A
LAN Client B
LAN Client C
       |
       | HTTP
       | Bearer API Key
       v
+---------------------------+
| FastAPI                   |
|                           |
| Authentication            |
| SQLite                    |
| Audit Log                 |
| Thread Ownership          |
+------------+--------------+
             |
             | Python SDK
             v
+---------------------------+
| OpenAI Codex Python SDK   |
+------------+--------------+
             |
             v
+---------------------------+
| Codex runtime              |
|                            |
| repo / shell / git / test  |
+------------+--------------+
             |
             v
     ChatGPT authentication
```

---

## 重要: 認証モデル

このシステムには、明確に異なる2種類の認証があります。

### A. Client → FastAPI

複数利用者を識別するための独自APIキーです。SQLite で管理し、各利用者には `client_id`(例: `alice`, `bob`, `ci-server`, `admin`)を割り当てます。

### B. FastAPI / Codex → OpenAI

Codex そのものの認証です。デフォルトは ChatGPT account authentication、必要な場合のみ OpenAI API key を fallback として使用できます。

**この2つを絶対に混同しないでください。**

---

## 重要: 複数ユーザーでもCodexアカウントは共有

このAPIサーバーでは、FastAPI の複数 `client_id` が、それぞれ別の ChatGPT アカウントになるわけではありません。

```text
alice ─┐
bob   ─┼─ FastAPI ─ Codex ─ 1つのCodex認証
ci    ─┘
```

したがって **Codex の使用量・利用制限は、バックエンドでログインしている Codex / ChatGPT アカウント側に集約されます。** `client_id` ごとの API key はあくまで「誰がこの API サーバーにアクセスできるか」「誰が何をしたか」を管理・監査するためのものであり、Codex 側のレート制限やプラン容量を分離するものではありません。

複数ユーザー向け本番サービスや組織利用でこのサーバーを使う場合は、使用する ChatGPT / OpenAI 契約がその利用形態に適しているか、現在の OpenAI 利用規約・プラン条件を確認してください。

---

## Codex SDK

`codex` CLI を FastAPI 側から直接 subprocess でラップするのではなく、公式 Python SDK (`openai-codex`) を利用しています。

実装時点でインストール・確認した内容:

- `openai-codex` version: **0.147.0**
- Codex runtime (`codex-cli`) version: **0.147.0**
- 公開 API は `python -m pydoc openai_codex` 等で実際に確認し、private API には依存していません。

### 仕様書との差分(重要)

指示書は `ApprovalMode` に複数のモードを想定していましたが、**実際にインストールした SDK (0.147.0) には `ApprovalMode.deny_all` と `ApprovalMode.auto_review` の2種類しか存在しません。** 存在しないモードを架空実装することはできないため、この2つから選択しています(詳細は後述)。

---

## 技術スタック

```text
Python 3.12
FastAPI
Uvicorn
Pydantic v2
pydantic-settings

openai-codex 0.147.0

SQLite (標準 sqlite3、SQLAlchemy不使用)

pytest / pytest-asyncio / httpx

Docker / Docker Compose
```

---

## ディレクトリ構成

```text
codex-api-server/
├── app/
│   ├── main.py               FastAPI app / lifespan
│   ├── config.py              pydantic-settings
│   ├── dependencies.py        認証 dependency, repository解決
│   ├── concurrency.py         global job limiter
│   ├── middleware.py          request-id / audit連携
│   ├── schemas.py              Pydantic request/response
│   ├── errors.py               統一エラースキーマ
│   ├── repository.py           DBアクセスの async facade
│   │
│   ├── codex/
│   │   ├── service.py          Codex SDK ラッパー(sandbox/承認/SSE正規化)
│   │   └── auth.py             Codex認証(chatgpt/api_key)
│   │
│   ├── security/
│   │   ├── api_keys.py         APIキー生成・HMAC・検証
│   │   └── principals.py       AuthenticatedPrincipal
│   │
│   ├── db/
│   │   ├── connection.py       sqlite3接続 + asyncio.to_thread
│   │   ├── migrations.py       スキーマ作成 + schema_version
│   │   ├── clients.py
│   │   ├── api_keys.py
│   │   ├── threads.py
│   │   └── audit.py
│   │
│   └── routes/
│       ├── health.py
│       ├── account.py
│       ├── threads.py
│       └── me.py
│
├── cli/
│   ├── users.py                 client(user)管理CLI
│   ├── api_keys.py               APIキー管理CLI
│   ├── audit.py                  監査ログ閲覧CLI
│   └── codex_auth.py             Codexログイン/ステータスCLI
│
├── tests/                        pytest (Codex/OpenAIへは接続しない)
├── data/                          SQLite永続化用(named volume mount先)
├── workspaces/                    リポジトリ配置用(bind mount)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── env.example
└── README.md
```

---

## SQLite Schema

### clients

| column | 説明 |
|---|---|
| id | 内部numeric ID |
| client_id | UNIQUE, `^[A-Za-z0-9._-]{1,64}$` |
| display_name | 表示名 |
| role | `user` \| `admin` |
| enabled | 有効/無効 |
| created_at / updated_at | ISO8601 |

### api_keys

| column | 説明 |
|---|---|
| id | 内部numeric ID |
| client_db_id | `clients.id` への FK |
| key_id | 非秘密の公開ID (`cak_...`) |
| key_hash | HMAC-SHA-256 digest (raw keyは保存しない) |
| enabled / created_at / last_used_at / expires_at / revoked_at | ライフサイクル管理 |

### codex_threads

| column | 説明 |
|---|---|
| thread_id | Codex SDK が発行する thread id (PK) |
| owner_client_id | 作成したclient_id (所有者境界) |
| repository | バインドされたリポジトリ名 |
| created_at / updated_at / archived / last_turn_id | |

### audit_logs

`id, timestamp, request_id, client_id, key_id, action, method, path, repository, thread_id, turn_id, status_code, duration_ms, remote_ip, user_agent, prompt_chars, result_status, error_code`

### schema_meta

`schema_version` を保持。外部マイグレーションフレームワークは使わず、起動時に `CREATE TABLE IF NOT EXISTS` 相当の安全な移行を実行します。

---

## API Key の設計

### フォーマット

- Raw key: `cax_<secrets.token_urlsafe(32)>` (256bit以上のランダム性)
- key_id: `cak_<8 hex chars>` (非秘密。監査ログにはこちらを記録)

### Hashing

```text
HMAC-SHA256(key=API_KEY_PEPPER, message=raw_api_key) の hex digest
```

を `key_hash` として DB へ保存します。**raw API key はDBに一切保存されません。** 照合は `key_hash` の indexed column lookup で行い、比較には `hmac.compare_digest()` を使用してタイミング攻撃を防いでいます。

### API_KEY_PEPPER の重要性

`API_KEY_PEPPER` を失うと、既存の API key を今後一切検証できなくなります(DBのhashを再現できないため)。**必ずバックアップしてください。**

逆に `DATABASE` と `API_KEY_PEPPER` の**両方**が漏洩した場合は、それらの組み合わせから既存 key の正当性を偽装される恐れはありませんが(hashは一方向関数のため raw key 自体は復元できません)、運用上は速やかに全 API key の credential rotation(全 revoke + 再発行)を行うことを推奨します。

### ライフサイクル

`create / list / revoke / disable / enable / rotate` をサポート。**raw keyが取得できるのは作成時・rotate時の1回だけ**です。DBからraw keyを復元する機能は実装していません(実装不可能: one-way hashのため)。

---

## Admin CLI

API key管理はHTTP APIではなく、Docker CLI経由で行います(管理APIをLANへ露出しないため)。

```bash
# User作成
docker compose exec codex-api python -m cli.users create --client-id alice --display-name "Alice"

# User一覧
docker compose exec codex-api python -m cli.users list

# User無効化・有効化
docker compose exec codex-api python -m cli.users disable alice
docker compose exec codex-api python -m cli.users enable alice

# API key作成 (raw keyはこの時だけ表示)
docker compose exec codex-api python -m cli.api_keys create alice
docker compose exec codex-api python -m cli.api_keys create alice --expires-in-days 90

# API key一覧 (raw keyは表示しない)
docker compose exec codex-api python -m cli.api_keys list alice

# API key revoke
docker compose exec codex-api python -m cli.api_keys revoke cak_ab12cd34

# API key rotation (新規発行 + 旧キーrevoke)
docker compose exec codex-api python -m cli.api_keys rotate alice --old-key-id cak_ab12cd34

# 監査ログ
docker compose exec codex-api python -m cli.audit list
docker compose exec codex-api python -m cli.audit list --client-id alice
docker compose exec codex-api python -m cli.audit list --repository project-a --limit 100
```

---

## Thread Ownership

複数ユーザー環境で最重要のセキュリティ境界です。

- 新規thread作成時、`owner_client_id` として作成者の `client_id` を SQLite (`codex_threads`) に保存します。
- 通常ユーザーは、他ユーザーが作成した thread に対する `resume / stream / archive / interrupt` を一切実行できません。
- アクセス拒否時は **HTTP 404** を返します(403にすると thread ID の存在自体が漏れるため)。
- `GET /v1/threads` は Codex SDK の `thread_list()` の結果をそのまま返さず、必ず SQLite の ownership table でフィルタしてから返します。
- Admin ロールは監査ログ閲覧・ユーザー管理CLI・thread metadata閲覧は可能ですが、**他ユーザーのCodex conversationへのprompt追加(resume/stream/interrupt)は禁止**しています。所有者境界はadminであっても越えられません。

---

## Repository Access / Path Safety

- `WORKSPACE_ROOT=/workspaces` を基点に、リクエストの `repository` フィールド(名前のみ、絶対パス禁止)を解決します。
- リポジトリ名は `^[A-Za-z0-9._-]+$` のみ許可。`../`, `../../etc`, `/etc`, `.`, `..`, `~` はすべて拒否します。
- 解決時は必ず `Path.resolve()` してから `WORKSPACE_ROOT` 配下に実際に収まっているかを再検証し、symlink による脱出 (`/workspaces/escape -> /etc` 等) を防いでいます。
- 現時点では全 enabled user が全 repository を利用可能です。認可ロジックは `app/dependencies.py` に集約しており、将来 repository ACL を追加する際もこの層のみ変更すれば済む構造にしています。

---

## Codex Sandbox / Approval Mode

- 必ず **`Sandbox.workspace_write`** を使用します。`Sandbox.full_access` は使用しません。
- Client から sandbox mode / approval mode を指定することはできません(APIスキーマに存在しない)。

### Approval Mode の選定理由

実際にインストールした `openai-codex==0.147.0` の `ApprovalMode` には `deny_all` と `auto_review` の2種類のみが存在します(仕様書が想定していたような複数段階のモードはSDKに存在しません)。

無人APIサーバーとして、**`ApprovalMode.auto_review`** を採用しました。

- `deny_all` はすべての承認が必要な操作を拒否するため、無人サーバーではファイル編集・shell実行がほぼ常に失敗し実用になりません。
- `auto_review` は Codex が自律的に判断して進める通常運用モードです。`Sandbox.workspace_write` と組み合わせることで、ファイル書き込み・shell実行は **workspace 配下に限定**され、ホスト全体への書き込みやネットワーク経由の任意コード実行を許すものではありません。

---

## Codex Authentication

> **重要:** このサーバーは、バックエンドの Codex が ChatGPT / OpenAI にログイン済みでないと、`/v1/threads` などの Codex を呼び出すエンドポイントが失敗します。**サーバーを本格的に使う前に、必ず一度 Codex ログインを済ませてください。** 具体的なログイン手順・確認方法・トラブルシュート(`{"detail":"Internal server error."}` が返る場合を含む)は **[SETUP.md](./SETUP.md)** にまとめています。

- デフォルトは `CODEX_AUTH_MODE=chatgpt`。既存の Codex 認証セッションがあれば再利用し、初回は Device Code login を使用します。
- fallback として `CODEX_AUTH_MODE=api_key` + `OPENAI_API_KEY` を使うと、起動時に `codex.login_api_key()` が実行されます。

### 認証の永続化

Codex runtime (codex-cli) は `CODEX_HOME` 環境変数が指すディレクトリ(デフォルト `~/.codex`)に認証情報を保存します。これは実際に `codex doctor` を実行して確認した挙動です。本サーバーでは Dockerfile 内で `CODEX_HOME=/home/codex/.codex` を明示的に設定し、`codex-auth` という named volume でこのディレクトリを永続化しています。

```yaml
volumes:
  - codex-auth:/home/codex/.codex
```

`codex-data` (SQLite) と `codex-auth` (Codex/ChatGPT認証) は明確に分離されています。

---

## Concurrency / Timeout

- `MAX_CONCURRENT_JOBS` (デフォルト 2) を上限とするグローバルな同時実行数制限を実装しています(`app/concurrency.py`)。上限超過時は待機させず即座に `429 too_many_requests` を返します。
- **この制限はグローバル**です。Alice と Bob が異なる thread を実行しても、同じ上限を共有します。バックエンドの Codex アカウントはユーザー間で共有されているため、ユーザーごとの無制限並列を許すと、そのアカウントの利用上限を無視した設計になってしまうためです。
- 将来 `MAX_CONCURRENT_JOBS_PER_CLIENT` を追加しやすいよう、`JobLimiter` はグローバル制限専用のシンプルなインターフェースとして分離しています。
- 同一 thread への同時リクエストは `asyncio.Lock` によってスレッドごとにシリアライズされます(異なる thread は並列実行可能)。
- `CODEX_REQUEST_TIMEOUT` (デフォルト 900秒) を超えると、通常リクエストは `504 timeout`、SSE では `event: error` (`code: timeout`) を返します。

---

## SSE Streaming

- 新規: `POST /v1/threads/stream`
- 既存: `POST /v1/threads/{thread_id}/stream`

SDK 内部の Notification (`AgentMessageDeltaNotification`, `ItemStartedNotification` 等) をそのまま外部にダンプせず、以下の小さな語彙へ正規化しています(`app/codex/service.py` の `_normalize_notification`):

```text
event: status     — {"status": "started" | "turn_started", ...}
event: delta      — {"text": "..."}
event: tool       — {"status": "started" | "completed", "item_type": "..."}
event: completed  — {"thread_id": "...", "turn_id": "...", "status": "completed"}
event: error      — {"code": "...", "message": "..."}
```

**reasoning / chain-of-thought 系の内部イベントは意図的に外部へ転送していません。** 外部に公開するのは assistant text・tool status・final response・usage metadata に相当する情報のみです。

---

## Interrupt

実行中の turn は `AsyncTurnHandle` としてスレッドごとに registry (`TurnRegistry`) 管理しており、

```http
POST /v1/threads/{thread_id}/interrupt
```

で `await turn_handle.interrupt()` を呼び出せます。所有者チェック必須です。

---

## Docker Security

- non-root user (`codex`) で実行します。
- `privileged: true` / `network_mode: host` は使用していません。
- `/var/run/docker.sock`、host の `/root` や `$HOME`、`~/.ssh` 等の host credential は一切マウントしません。
- 最小限のパッケージ (`git`, `curl`, `ca-certificates`, `bash`) のみインストールしています。**対象リポジトリの言語ランタイム(Node.js, Rust, Go等)が必要な場合は、別途 Dockerfile へ追加してください。**
- workspace の bind mount で UID/GID の不一致が起きる場合、host 側のファイル所有者と container 内 `codex` ユーザーの UID (通常1000) を揃えるか、`docker-compose.yml` に `user:` を明示してください。

---

## LAN公開 / Firewall / CORS

- `docker-compose.yml` で `0.0.0.0:8000:8000` を公開し、Uvicorn も `0.0.0.0:8000` で listen します。
- `/health` 以外は Bearer 認証必須です。**LAN内であっても "trusted network" とは仮定しません。**
- Linux Firewall例 (server LAN が `192.168.1.0/24` の場合、TCP 8000 を LAN subnet からのみ許可):

```bash
# ufw の例
sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp

# iptables の例
sudo iptables -A INPUT -p tcp --dport 8000 -s 192.168.1.0/24 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8000 -j DROP
```

- **router の port forwarding で 8000 を internet へ直接公開しないでください。** Internet越しにアクセスしたい場合は Tailscale / WireGuard / VPN / TLS reverse proxy 等を利用してください。
- CORS はデフォルト無効 (`CORS_ORIGINS=`)。ブラウザ frontend を使う場合のみ、オリジンを明示的に allowlist してください。`*` はデフォルトにしていません。
- `X-Forwarded-For` はデフォルトで信用しません。直接コネクションの remote IP のみを監査ログに使用します(reverse proxy 経由で正しい IP を記録したい場合は、信頼できるプロキシからのみこのヘッダーを受理するロジックを追加する必要がありますが、本実装ではデフォルトで無効です)。

---

## Security: このAPIはremote code executionを扱うサービスです

**このAPIは通常のチャットAPIではありません。** Codex は filesystem write / shell execution / git / tests を実行できるため、**remote code execution capability を持つサービス**として扱う必要があります。

最低限の推奨事項:

- LANのみで運用する(internet直接公開禁止)
- Bearer認証必須(`/health`以外)
- ユーザーごとに別のAPI keyを発行する
- API keyは定期的にrotationする
- 利用終了したユーザーは速やかにdisableする
- 不要になったAPI keyはrevokeする
- FirewallでLAN subnetにアクセスを限定する
- non-root containerで実行する
- Docker socketをマウントしない
- host credentials (`~/.ssh`, `~/.aws` 等) をマウントしない
- workspaceを意図したディレクトリ配下に制限する

### Prompt Injection

**untrusted な repository の `AGENTS.md` / README / ソースコードのコメント / スクリプト等には、agentへの悪意ある instruction が埋め込まれている可能性があります。** repository 自体を untrusted input として扱ってください。本サーバーはこれに対する自動防御機構を持たないため、社内・信頼できるリポジトリのみを `workspaces/` に配置することを推奨します。

### Git操作について

API Server自身は `git push` / `git reset --hard` / `git clean -fd` を自動的に実行しません。git remote の credential もデフォルトではマウントしません。

---

## セットアップ・起動手順

導入から起動、ユーザー作成、動作確認、Codex ログイン、トラブルシュートまでの手順は、別ファイル **[SETUP.md](./SETUP.md)** にまとめています。

概要:

```text
1. Setup        .env を用意して API_KEY_PEPPER を設定
2. Build        docker compose build
3. Codex login  ChatGPT / OpenAI にログイン（← 飛ばすと Codex 実行が失敗）
4. Start        docker compose up -d
5. Admin/User   管理者・利用者と API key を作成
6. 利用         LAN クライアントから curl で利用
```

詳細は [SETUP.md](./SETUP.md) を参照してください。

---

## Endpoints一覧

| Method | Path | 認証 | 説明 |
|---|---|---|---|
| GET | `/health` | 不要 | liveness/readiness |
| GET | `/v1/me` | 必須 | 自分のclient情報 |
| GET | `/v1/account` | 必須 | バックエンドCodexの認証状態 |
| POST | `/v1/threads` | 必須 | 新規thread作成 + 初回prompt実行 |
| POST | `/v1/threads/{thread_id}/messages` | 必須 (所有者) | thread継続 |
| GET | `/v1/threads` | 必須 | 自分のthread一覧 |
| DELETE | `/v1/threads/{thread_id}` | 必須 (所有者) | thread archive |
| POST | `/v1/threads/stream` | 必須 | 新規thread + SSE streaming |
| POST | `/v1/threads/{thread_id}/stream` | 必須 (所有者) | thread継続 + SSE streaming |
| POST | `/v1/threads/{thread_id}/interrupt` | 必須 (所有者) | 実行中turnの中断 |

---

## エラースキーマ

```json
{
  "error": {
    "code": "repository_not_found",
    "message": "Repository not found",
    "request_id": "..."
  }
}
```

API key関連のエラー(未認証・disabled・revoked・expired・disabled client)は、credential状態の詳細を外部に漏らさないため、**すべて `401 unauthorized` に統一**しています。

---

## テスト

```bash
python -m compileall app cli
pytest -q
```

テストは本物の OpenAI / Codex API へ一切接続しません。`app/codex/service.py` の `CodexServiceProtocol` を介して Fake 実装 (`tests/conftest.py::FakeCodexService`) を DI しています。

---

## 未対応事項 / SDKの制約

- **ApprovalMode の多段階制御**: 指示書が想定していたような複数段階の承認モードは、実際の `openai-codex==0.147.0` には存在しません(`deny_all` / `auto_review` の2種類のみ)。将来 SDK が拡張された場合は `app/codex/service.py` の `DEFAULT_APPROVAL_MODE` を見直してください。
- **Reverse proxy 経由の正しい remote_ip 記録**: `X-Forwarded-For` の trusted-proxy 対応は未実装です(仕様上デフォルト無効が要件のため)。将来必要になった場合は allowlist ベースで追加してください。
- **Repository ACL**: 現状は全 enabled user が全 repository にアクセス可能です。認可ロジックは `app/dependencies.py` に集約済みのため、ACL 追加は同ファイルの変更のみで対応可能な設計にしています。
- **実際の ChatGPT ログイン・本物の Codex への prompt 実行の動作確認**: 本サーバーを実装したサンドボックス環境はネットワーク的に ChatGPT の認証エンドポイントへ到達できないため、`cli.codex_auth login` によるログインおよびその後の実際の Codex 実行は動作確認できていません。SDKの型・シグネチャの整合性はすべて実際にインストールした `openai-codex==0.147.0` を対象に確認済みです。
