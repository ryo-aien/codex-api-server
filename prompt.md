# Codex API Server 実装指示

Docker Compose でそのまま起動できる、自分たち専用の「FastAPI + OpenAI Codex Python SDK API Server」を実装してください。

このシステムは複数ユーザーから利用することを前提とします。

APIクライアント認証は単一の環境変数APIキーではなく、

```text
SQLite
+
client_id
+
複数APIキー
+
監査ログ
```

で管理してください。

---

# 1. 目的

ローカルPCまたはLAN内のLinuxサーバー上で Codex を常駐させ、同一ネットワーク内の複数PCや自作アプリから REST API / SSE 経由でプロンプトを送信できるようにします。

主用途:

* コード調査
* バグ調査
* ファイル読み取り
* ファイル編集
* shell command 実行
* テスト実行
* git status / git diff
* 複数turnでの継続作業
* Codex threadのresume
* 複数ユーザーからの利用
* ユーザー単位の監査

想定構成:

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
| Codex runtime             |
|                           |
| repo / shell / git / test |
+------------+--------------+
             |
             v
     ChatGPT authentication
```

---

# 2. 重要な認証モデル

このシステムには、明確に異なる2種類の認証があります。

## A. Client → FastAPI

複数利用者を識別するための独自APIキー。

SQLiteで管理します。

```text
Alice
  ↓ Alice API Key

Bob
  ↓ Bob API Key

FastAPI
```

各利用者には、

```text
client_id
```

を割り当ててください。

例:

```text
alice
bob
ci-server
admin
```

---

## B. FastAPI / Codex → OpenAI

Codexそのものの認証。

デフォルト:

```text
ChatGPT account authentication
```

を使用します。

必要な場合のみ、

```text
OpenAI API key
```

をfallbackとして利用可能にしてください。

この2つを絶対に混同しないでください。

---

# 3. 重要: 複数ユーザーでもCodexアカウントは共有

このAPIサーバーでは、FastAPIの複数 `client_id` が、それぞれ別のChatGPTアカウントになるわけではありません。

構成は、

```text
alice ─┐
bob   ─┼─ FastAPI ─ Codex ─ 1つのCodex認証
ci    ─┘
```

です。

したがってCodexの使用量・利用制限は、バックエンドでログインしているCodex / ChatGPTアカウント側に集約されます。

READMEにこの点を明記してください。

複数ユーザー向け本番サービスや組織利用では、使用するChatGPT/OpenAI契約がその利用形態に適しているか、現在のOpenAI規約・プラン条件を確認する必要があることも明記してください。

---

# 4. Codex SDK

`codex` CLI をFastAPI側から直接subprocessでラップしないでください。

公式Python SDK:

```bash
pip install openai-codex
```

を利用してください。

基本:

```python
from openai_codex import (
    AsyncCodex,
    ApprovalMode,
    Sandbox,
)
```

現在のSDK公開APIを実際に確認してください。

最低限確認:

```text
AsyncCodex
CodexConfig

login_chatgpt
login_chatgpt_device_code
login_api_key
account
logout

thread_start
thread_resume
thread_list
thread_archive
thread_unarchive

Sandbox.read_only
Sandbox.workspace_write
Sandbox.full_access

AsyncThread.run
AsyncThread.turn

AsyncTurnHandle.stream
AsyncTurnHandle.interrupt

TurnResult
```

ドキュメントより、インストール済みSDKの公開APIを優先してください。

private APIには依存しないでください。

---

# 5. 技術スタック

以下を基本としてください。

```text
Python 3.12
FastAPI
Uvicorn
Pydantic v2
pydantic-settings

openai-codex

SQLite
Python sqlite3

pytest
pytest-asyncio
httpx

Docker
Docker Compose
```

SQLiteについては、

```text
SQLAlchemy
```

を必須にしないでください。

規模が小さいため、Python標準の、

```python
sqlite3
```

で十分です。

ただしコードの保守性が著しく改善する合理的理由があれば、軽量なDB layerを導入しても構いません。

以下は不要:

```text
PostgreSQL
Redis
Celery
RabbitMQ
Kubernetes
```

---

# 6. Project Name

Repository:

```text
codex-api-server
```

---

# 7. Directory structure

以下を基本にしてください。

```text
codex-api-server/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   │
│   ├── codex/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   └── auth.py
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── api_keys.py
│   │   └── principals.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── migrations.py
│   │   ├── clients.py
│   │   ├── api_keys.py
│   │   ├── threads.py
│   │   └── audit.py
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py
│   │   ├── account.py
│   │   ├── threads.py
│   │   └── me.py
│   │
│   ├── repository.py
│   ├── concurrency.py
│   ├── middleware.py
│   ├── schemas.py
│   └── errors.py
│
├── cli/
│   ├── __init__.py
│   ├── users.py
│   ├── api_keys.py
│   └── codex_auth.py
│
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_api_keys.py
│   ├── test_clients.py
│   ├── test_audit.py
│   ├── test_thread_ownership.py
│   ├── test_repository.py
│   ├── test_threads.py
│   ├── test_stream.py
│   ├── test_concurrency.py
│   └── test_health.py
│
├── data/
│   └── .gitkeep
│
├── workspaces/
│   └── .gitkeep
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .dockerignore
├── .gitignore
├── .env.example
└── README.md
```

合理的な変更は可能です。

巨大な `main.py` 一枚にはしないでください。

---

# 8. SQLite

DB path:

```env
DATABASE_PATH=/data/codex-api.db
```

Docker named volume:

```text
codex-data
```

を、

```text
/data
```

へmountしてください。

例:

```yaml
volumes:
  - codex-data:/data
```

DBはcontainer再起動やimage rebuildでも失われないようにしてください。

---

# 9. SQLite schema

最低限以下のtableを作成してください。

## clients

```sql
clients
-------
id
client_id
display_name
role
enabled
created_at
updated_at
```

`client_id`:

```text
UNIQUE
NOT NULL
```

例:

```text
alice
bob
ci-server
admin
```

形式:

```regex
^[A-Za-z0-9._-]{1,64}$
```

`role`:

```text
user
admin
```

最低限この2種類。

---

# 10. api_keys table

```sql
api_keys
--------
id
client_id
key_id
key_hash
enabled
created_at
last_used_at
expires_at
revoked_at
```

必要ならforeign keyとして、

```text
clients.id
```

を使う設計でも構いません。

推奨は内部numeric client DB IDをforeign keyとして使い、外部には `client_id` を公開する方式です。

---

# 11. API Key format

ユーザーへ発行するraw API keyは十分なentropyを持たせてください。

例えば、

```text
cax_<random>
```

形式。

例:

```text
cax_Qz7....
```

`secrets.token_urlsafe(32)` 以上を使ってください。

最低でも256-bit相当のランダム性を確保してください。

---

# 12. key_id

各API keyには、

```text
key_id
```

も持たせてください。

例:

```text
cak_ab12cd34
```

これは秘密情報ではありません。

監査ログにはraw keyではなく、

```text
client_id
key_id
```

を記録できます。

---

# 13. APIキーをDBへ平文保存しない

絶対条件です。

SQLiteにはraw API keyを保存しないでください。

禁止:

```text
api_key = cax_abcdef...
```

---

# 14. API Key hashing

API keyは高entropy credentialなので、

```text
HMAC-SHA-256
```

を使用してください。

環境変数:

```env
API_KEY_PEPPER=
```

を用意。

生成例:

```bash
openssl rand -hex 32
```

サーバー側:

```python
HMAC-SHA256(
    key=API_KEY_PEPPER,
    message=raw_api_key
)
```

のdigestをDBへ保存してください。

Python標準:

```python
hmac
hashlib
```

を使用。

DB:

```text
key_hash
```

のみ保存。

API_KEY_PEPPER自体はDBへ保存しないでください。

---

# 15. Pepperの重要性

`API_KEY_PEPPER` を失うと既存API keyを検証できなくなるため、READMEにバックアップの重要性を記載してください。

一方、

```text
DATABASE
+
API_KEY_PEPPER
```

の両方が漏洩した場合はcredential rotationが必要であることも説明してください。

---

# 16. API Key verification

Request:

```http
Authorization: Bearer cax_....
```

Server:

```text
raw token
   ↓
HMAC-SHA256(API_KEY_PEPPER, token)
   ↓
DB hash lookup
   ↓
client
```

という流れにしてください。

可能であればdigestをindexed columnとしてlookupしてください。

raw keyを全レコードに対して順番に比較する設計にしないでください。

---

# 17. timing attack

hash値を照合する必要がある箇所では、

```python
hmac.compare_digest()
```

を使用してください。

---

# 18. API Key lifecycle

以下をサポートしてください。

```text
create
list
revoke
disable
enable
rotate
```

ただしraw keyを取得できるのは、

```text
作成時の1回だけ
```

にしてください。

DBからraw keyを復元する機能は禁止。

---

# 19. Admin CLI

API key管理はHTTP APIではなく、最初はDocker CLIから行ってください。

これにより管理APIをLANへ露出する必要をなくします。

例:

## User create

```bash
docker compose exec codex-api \
  python -m cli.users create \
  --client-id alice \
  --display-name "Alice"
```

---

## User list

```bash
docker compose exec codex-api \
  python -m cli.users list
```

---

## Disable user

```bash
docker compose exec codex-api \
  python -m cli.users disable alice
```

---

## Enable user

```bash
docker compose exec codex-api \
  python -m cli.users enable alice
```

---

# 20. API key create

```bash
docker compose exec codex-api \
  python -m cli.api_keys create alice
```

output:

```text
API key created

client_id: alice
key_id: cak_ab12cd34

API key:
cax_xxxxxxxxxxxxxxxxxxxxxxxxx

IMPORTANT:
This key will only be shown once.
Store it securely.
```

raw keyはこの時だけ表示してください。

---

# 21. API key list

```bash
docker compose exec codex-api \
  python -m cli.api_keys list alice
```

表示:

```text
key_id
enabled
created_at
last_used_at
expires_at
revoked_at
```

raw keyは表示しない。

---

# 22. API key revoke

```bash
docker compose exec codex-api \
  python -m cli.api_keys revoke cak_ab12cd34
```

revoke後は即座に認証不可にしてください。

---

# 23. Key rotation

以下のrotationを可能にしてください。

```text
1. 新しいキーを発行
2. client側を新しいキーへ切替
3. 旧キーをrevoke
```

同じclient_idに複数のactive API keyを持てるようにしてください。

---

# 24. Expiration

API key作成時にoptionalでexpiryを指定可能。

例:

```bash
python -m cli.api_keys create alice --expires-in-days 90
```

expirationなしも許可。

期限切れキーは401。

---

# 25. Authenticated principal

FastAPI dependencyは単なるbooleanではなく、

```python
@dataclass(frozen=True)
class AuthenticatedPrincipal:
    client_id: str
    display_name: str | None
    role: str
    key_id: str
```

のようなprincipalを返してください。

endpoint:

```python
principal: AuthenticatedPrincipal = Depends(require_auth)
```

と使える形にしてください。

---

# 26. GET /v1/me

実装:

```http
GET /v1/me
Authorization: Bearer ...
```

Response:

```json
{
  "client_id": "alice",
  "display_name": "Alice",
  "role": "user"
}
```

`key_id` は必要なら返して構いません。

API keyそのものは絶対に返さない。

---

# 27. Audit Log

SQLiteに、

```text
audit_logs
```

tableを作成してください。

最低限:

```sql
audit_logs
----------
id
timestamp
request_id
client_id
key_id
action
method
path
repository
thread_id
turn_id
status_code
duration_ms
remote_ip
user_agent
prompt_chars
result_status
error_code
```

---

# 28. Audit対象

最低限以下を記録してください。

```text
authentication success
authentication failure

thread create
thread resume
thread archive
thread list

prompt execution
stream execution

timeout
interrupt

repository access failure
authorization failure

server error
```

---

# 29. 絶対にaudit logへ記録しない情報

禁止:

```text
raw API key
Authorization header
API_KEY_PEPPER

OpenAI credential
ChatGPT token

full prompt
full response

file contents
tool output
shell stdout全文
```

promptは:

```text
prompt_chars
```

のみ。

---

# 30. Authentication failure log

API key不正時はclient_idが分からないため、

```text
client_id = null
key_id = null
```

で構いません。

ただし、

```text
request_id
remote_ip
path
timestamp
status
```

は記録してください。

raw tokenのhash等もログに残さないでください。

---

# 31. Remote IP

reverse proxyを前提にせず、デフォルトでは直接connectionのremote IPを使用してください。

`X-Forwarded-For` を無条件に信用しないでください。

将来trusted proxyを設定可能にしても構いませんが、デフォルトでは偽装可能なheaderを監査用IPとして採用しないでください。

---

# 32. Audit Log CLI

以下を作ってください。

```bash
docker compose exec codex-api \
  python -m cli.users audit alice
```

または、

```bash
python -m cli.audit list --client-id alice
```

のようなCLI。

推奨:

```bash
python -m cli.audit list
python -m cli.audit list --client-id alice
python -m cli.audit list --repository project-a
python -m cli.audit list --limit 100
```

raw secretは表示しない。

---

# 33. Thread ownership

複数ユーザー環境で非常に重要です。

SQLiteに、

```text
codex_threads
```

tableを作成してください。

例:

```sql
codex_threads
-------------
thread_id
client_id
repository
created_at
updated_at
archived
```

必要なら:

```text
last_turn_id
```

等を追加。

---

# 34. Thread owner

新規threadを作成したユーザーを、

```text
owner_client_id
```

として保存してください。

例えばAlice:

```text
thread_id = thr_xxx
client_id = alice
repository = project-a
```

---

# 35. 他ユーザーthreadアクセス禁止

通常ユーザー:

```text
alice
```

はBobが作ったthreadを、

```text
resume
stream
archive
interrupt
```

できないようにしてください。

この場合:

```text
HTTP 404
```

を推奨します。

403にするとthread IDの存在が漏れるため、通常ユーザーには404を返してください。

---

# 36. Admin

role:

```text
admin
```

のユーザーについては、必要なら全threadを確認可能にして構いません。

ただしデフォルトでは、

```text
adminも他ユーザーthreadを実行操作できない
```

設計でも構いません。

推奨:

Admin:

```text
audit閲覧
ユーザー管理CLI
thread metadata閲覧
```

は可能。

他人のCodex conversationへのprompt追加は原則禁止。

セキュリティ上、所有者境界を保ってください。

---

# 37. Thread list

```http
GET /v1/threads
```

通常ユーザーには、

```text
自分が作成したthreadのみ
```

返してください。

Codex SDKの `thread_list()` が全threadを返す場合でも、その結果をSQLite ownership tableでfilterしてください。

---

# 38. Repository Access

環境:

```env
WORKSPACE_ROOT=/workspaces
```

host:

```text
./workspaces
```

container:

```text
/workspaces
```

API Request:

```json
{
  "repository": "project-a"
}
```

absolute pathは禁止。

---

# 39. Repository name validation

```regex
^[A-Za-z0-9._-]+$
```

程度。

拒否:

```text
../
../../etc
/etc
~
.
..
```

---

# 40. Symlink escape

必ず、

```python
Path.resolve()
```

してください。

最終pathが、

```text
WORKSPACE_ROOT
```

内部に存在することを確認。

例:

```text
/workspaces/escape -> /etc
```

は拒否。

---

# 41. Repository permissions

現時点では全enabled userが全repositoryを利用可能で構いません。

ただし後からrepository ACLを追加しやすい構造にしてください。

authorization logicをrouteに直接散らさず、service/dependency layerへまとめてください。

---

# 42. Codex sandbox

必ず:

```python
Sandbox.workspace_write
```

を使用。

禁止:

```python
Sandbox.full_access
```

Clientからsandbox modeを指定できないようにしてください。

---

# 43. Approval Mode

現在のCodex SDKの、

```text
ApprovalMode
```

仕様を確認してください。

無人API Serverとして安全かつ実用的なmodeを選択してください。

Clientから自由にapproval modeを変更できない設計にしてください。

選んだ理由をREADMEに説明してください。

---

# 44. Codex lifecycle

FastAPI lifespanで `AsyncCodex` を管理してください。

概念:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncCodex(...) as codex:
        app.state.codex = codex
        yield
```

現行SDKに沿った正しい方法を使用。

---

# 45. Codex authentication

デフォルト:

```env
CODEX_AUTH_MODE=chatgpt
```

optional:

```env
CODEX_AUTH_MODE=api_key
OPENAI_API_KEY=
```

---

# 46. ChatGPT authentication

既存Codex auth sessionが存在すれば再利用。

初回はDevice Code loginを優先してください。

管理CLI:

```bash
docker compose run --rm codex-api \
  python -m cli.codex_auth login
```

SDK:

```python
await codex.login_chatgpt_device_code()
```

を利用可能なら使用。

表示:

```text
Verification URL:
...

Code:
....
```

---

# 47. Codex auth persistence

Codex runtimeが実際に利用するauthentication directoryを確認してください。

named volume:

```text
codex-auth
```

へ永続化。

推測でpathを決めず、現行仕様を確認してください。

例として `~/.codex` なら:

```yaml
volumes:
  - codex-auth:/home/codex/.codex
```

---

# 48. Codex account status

CLI:

```bash
python -m cli.codex_auth status
```

を実装。

必要最低限:

```text
authenticated
auth mode
```

だけ表示。

token/email等は不要。

---

# 49. GET /health

LANからアクセス可能。

認証不要。

```http
GET /health
```

Response:

```json
{
  "status": "ok",
  "codex": "ready",
  "authenticated": true,
  "database": "ready"
}
```

機密情報は返さない。

---

# 50. GET /v1/account

Bearer必須。

バックエンドCodexの状態だけ返してください。

```json
{
  "authenticated": true,
  "auth_mode": "chatgpt"
}
```

ChatGPTのemailやcredentialは返さない。

---

# 51. POST /v1/threads

Bearer必須。

Request:

```json
{
  "repository": "project-a",
  "prompt": "このリポジトリの問題を調査してください"
}
```

実装:

```python
thread = await codex.thread_start(
    cwd=resolved_repo_path,
    sandbox=Sandbox.workspace_write,
)

result = await thread.run(prompt)
```

現行SDKに合わせる。

成功後:

```text
thread_id
client_id
repository
```

をSQLiteに保存。

Response:

```json
{
  "thread_id": "thr_xxx",
  "turn_id": "...",
  "repository": "project-a",
  "status": "completed",
  "response": "..."
}
```

---

# 52. POST /v1/threads/{thread_id}/messages

Bearer必須。

まずSQLiteで、

```text
thread owner == current principal
```

を検証。

さらにrepository一致を確認。

Request:

```json
{
  "repository": "project-a",
  "prompt": "では修正してテストしてください"
}
```

その後:

```python
thread = await codex.thread_resume(
    thread_id,
    cwd=resolved_repo_path,
    sandbox=Sandbox.workspace_write,
)

result = await thread.run(prompt)
```

---

# 53. Thread repository binding

thread作成時のrepositoryから、後続requestでrepositoryを変更できないようにしてください。

より良い設計として、

```http
POST /v1/threads/{thread_id}/messages
```

ではrepositoryをrequestから受け取らず、

```text
SQLite thread metadata
```

からrepositoryを取得してください。

こちらを推奨します。

つまりRequest:

```json
{
  "prompt": "続きを実行してください"
}
```

だけでよいです。

同様にstream endpointでもrepositoryを再指定させないでください。

---

# 54. GET /v1/threads

Bearer必須。

通常ユーザー:

```text
自分のthreadsのみ
```

返す。

query:

```text
limit
cursor
archived
```

SDKとDBを組み合わせて実装。

---

# 55. DELETE /v1/threads/{thread_id}

Bearer必須。

所有者確認。

Codex:

```python
await codex.thread_archive(thread_id)
```

SQLite:

```text
archived=true
```

---

# 56. SSE Streaming

新規:

```http
POST /v1/threads/stream
```

既存:

```http
POST /v1/threads/{thread_id}/stream
```

Bearer必須。

既存threadではowner check必須。

SDK:

```python
turn = await thread.turn(prompt)

async for event in turn.stream():
    ...
```

を使用。

---

# 57. SSE normalization

SDK eventをraw dumpしない。

外部向け:

```text
event: status
data: {"status":"started"}

event: delta
data: {"text":"..."}

event: tool
data: {...}

event: completed
data: {
  "thread_id":"thr_xxx",
  "status":"completed"
}

event: error
data: {...}
```

内部protocolの詳細にClientを依存させない。

---

# 58. Reasoning

内部chain-of-thought / reasoning event等をそのまま外部公開しないでください。

外部には:

```text
assistant text
tool status
final response
usage metadata
```

等、必要な情報だけ。

---

# 59. Interrupt

SDKで公式にサポートされる、

```python
await turn_handle.interrupt()
```

等を使用。

Endpoint:

```http
POST /v1/threads/{thread_id}/interrupt
```

owner check必須。

実行中turn registryを管理してください。

---

# 60. Concurrency

環境:

```env
MAX_CONCURRENT_JOBS=2
```

`asyncio.Semaphore` 等でCodex turn数を制限。

---

# 61. Per-thread lock

同一threadへの同時requestは禁止。

```python
dict[str, asyncio.Lock]
```

等。

```text
thread A request 1
thread A request 2
```

はserialize。

異なるthreadはparallel可能。

---

# 62. Cross-user concurrency

AliceとBobが異なるthreadを実行しても、

```text
MAX_CONCURRENT_JOBS
```

のglobal limitを共有してください。

backend Codex accountの利用上限を無視してユーザーごとの無制限並列にはしない。

---

# 63. Optional per-client limit

将来、

```text
MAX_CONCURRENT_JOBS_PER_CLIENT
```

を追加しやすい設計にしてください。

初期実装ではglobal semaphoreだけでも構いません。

---

# 64. Timeout

```env
CODEX_REQUEST_TIMEOUT=900
```

通常request timeout:

```text
HTTP 504
```

SSE:

```text
event: error
code: timeout
```

---

# 65. Prompt limit

```env
MAX_PROMPT_CHARS=100000
```

validation:

```text
empty禁止
whitespace-only禁止
最大長
```

---

# 66. Request ID

Middleware:

```http
X-Request-ID
```

Clientの妥当な値は利用可能。

なければUUID生成。

Responseにも返す。

audit logにも保存。

---

# 67. Application logging

Python logging。

最低限:

```text
request_id
client_id
key_id
endpoint
repository
thread_id
turn_id
status
duration_ms
prompt_chars
```

---

# 68. Secretsをログに出さない

禁止:

```text
Bearer token
raw API key
API_KEY_PEPPER
OPENAI_API_KEY
ChatGPT token
prompt全文
response全文
```

---

# 69. Error schema

統一:

```json
{
  "error": {
    "code": "repository_not_found",
    "message": "Repository not found",
    "request_id": "..."
  }
}
```

最低限:

```text
400 invalid_request

401 unauthorized
401 api_key_expired
401 api_key_revoked

404 repository_not_found
404 thread_not_found

409 thread_busy

422 validation_error

429 too_many_requests

500 internal_error

502 codex_error
503 codex_unavailable
504 timeout
```

セキュリティ上必要ならAPI key関係はすべて単純な、

```text
401 unauthorized
```

に統一しても構いません。

外部へcredential状態の詳細を出さない方を優先してください。

---

# 70. SQLite concurrency

FastAPI async applicationでSQLiteを扱うため、event loopをblockingしないよう配慮してください。

以下のいずれか:

```text
短時間transaction
thread executor
asyncio.to_thread
```

等を使用。

DB lockを長時間保持しない。

Codex実行中にSQLite transactionをopenしたままにしない。

---

# 71. SQLite settings

適切なら、

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

等を使用してください。

現在のユースケースに合うか確認して採用。

---

# 72. DB migrations

外部migration frameworkは必須ではありません。

簡易schema version:

```text
schema_version
```

を持たせてください。

起動時に、

```text
DB存在
↓
schema確認
↓
必要migration
```

を安全に実行。

---

# 73. Initial Admin

初回DBにはuserが存在しません。

管理CLIで:

```bash
docker compose exec codex-api \
  python -m cli.users create \
  --client-id admin \
  --display-name Administrator \
  --role admin
```

その後:

```bash
docker compose exec codex-api \
  python -m cli.api_keys create admin
```

としてください。

initial admin passwordのような固定credentialをimage内に埋め込まない。

---

# 74. Docker

Dockerfile:

```text
Python 3.12
non-root
```

user:

```text
codex
```

container:

```text
/app
/workspaces
/data
```

---

# 75. Docker volumes

```yaml
volumes:
  - ./workspaces:/workspaces
  - codex-data:/data
  - codex-auth:<actual-auth-path>
```

`codex-data`:

```text
SQLite
```

`codex-auth`:

```text
ChatGPT/Codex auth
```

明確に分離。

---

# 76. LAN公開

今回は同一ネットワーク内の別PCから利用することが要件です。

Docker Compose:

```yaml
ports:
  - "0.0.0.0:8000:8000"
```

FastAPI/Uvicorn:

```text
0.0.0.0:8000
```

でlisten。

---

# 77. LAN client example

Server:

```text
192.168.1.100
```

Client:

```text
http://192.168.1.100:8000
```

でアクセス可能にしてください。

---

# 78. LANだから無認証にしない

`/health` 以外はBearer必須。

LAN内でも、

```text
trusted network
```

とは仮定しない。

---

# 79. Firewall README

READMEにLinux firewall例を記載。

例えばserver LANが:

```text
192.168.1.0/24
```

の場合、

```text
TCP 8000
```

へのアクセスをLAN subnetからのみ許可することを推奨。

特定のfirewall製品を必須にはしない。

---

# 80. Internet公開禁止

READMEに、

```text
router port forwardingで8000をinternetへ直接公開しない
```

と明記。

Internet越しなら:

```text
Tailscale
WireGuard
VPN
TLS reverse proxy
```

等を利用。

---

# 81. CORS

LAN公開とCORSは別。

デフォルト:

```env
CORS_ORIGINS=
```

無効。

Browser frontendを使う場合のみallowlist。

`*` をdefaultにしない。

---

# 82. Docker security

禁止:

```yaml
privileged: true
network_mode: host
```

禁止mount:

```text
/var/run/docker.sock
host /root
host $HOME
~/.ssh
~/.aws
~/.config/gcloud
```

等。

---

# 83. Non-root

containerはrootで実行しない。

`codex` user。

workspace bind mountのUID/GID問題をREADMEで説明。

---

# 84. Minimum packages

最低限:

```text
git
curl
ca-certificates
bash
```

対象repositoryの言語runtimeは別途imageへ追加する必要があることをREADMEへ記載。

例:

```text
Node.js project → node/npm必要
Rust → cargo必要
Go → go必要
```

---

# 85. Environment

`.env.example`:

```env
# ------------------------------------------------
# FastAPI / LAN
# ------------------------------------------------

HOST=0.0.0.0
PORT=8000

# ------------------------------------------------
# SQLite
# ------------------------------------------------

DATABASE_PATH=/data/codex-api.db

# Used to HMAC API keys before storing them in SQLite.
# Generate with:
# openssl rand -hex 32
API_KEY_PEPPER=replace-with-a-random-secret

# ------------------------------------------------
# Codex authentication
# ------------------------------------------------

CODEX_AUTH_MODE=chatgpt

# Used only when CODEX_AUTH_MODE=api_key
OPENAI_API_KEY=

# ------------------------------------------------
# Workspace
# ------------------------------------------------

WORKSPACE_ROOT=/workspaces

# ------------------------------------------------
# Limits
# ------------------------------------------------

MAX_CONCURRENT_JOBS=2
CODEX_REQUEST_TIMEOUT=900
MAX_PROMPT_CHARS=100000

# ------------------------------------------------
# Browser access
# ------------------------------------------------

CORS_ORIGINS=

# ------------------------------------------------
# Logging
# ------------------------------------------------

LOG_LEVEL=INFO
```

`SERVER_API_KEY` / `SERVER_API_KEYS` は使用しないでください。

API keyはSQLite管理です。

---

# 86. .gitignore

最低限:

```text
.env
*.db
*.db-shm
*.db-wal
__pycache__/
.pytest_cache/
```

---

# 87. Healthcheck

Docker Compose:

```text
GET http://127.0.0.1:8000/health
```

でhealthcheck。

---

# 88. Tests

本物のOpenAI/Codex APIへ接続せず実行可能にしてください。

Codex serviceはDI可能にする。

---

# 89. API key tests

必須:

```text
valid key
invalid key
missing header
malformed Bearer

disabled key
revoked key
expired key

disabled client

multiple keys same client

key rotation

raw key not stored in DB
```

DBを直接確認し、raw API key文字列が存在しないことをテスト。

---

# 90. API pepper tests

同じraw key:

```text
same pepper → same digest
different pepper → different digest
```

を確認。

---

# 91. Client tests

```text
create
duplicate client_id
disable
enable
admin/user role
```

---

# 92. Audit tests

request後に、

```text
client_id
key_id
request_id
repository
thread_id
status
```

が記録されること。

さらに、

```text
raw API key
full prompt
Authorization header
```

がaudit DBに存在しないことを確認。

---

# 93. Thread ownership tests

非常に重要。

```text
Alice creates thread A
Bob creates thread B
```

確認:

```text
Alice → A resume = success
Bob → B resume = success

Alice → B resume = 404
Bob → A resume = 404

Alice → B archive = 404
Bob → A stream = 404
```

---

# 94. Thread list tests

Alice:

```text
Aだけ見える
```

Bob:

```text
Bだけ見える
```

こと。

---

# 95. Repository tests

必須:

```text
project-a
../etc
../../etc
/etc
.
..
~
```

symlink:

```text
/workspaces/escape -> /etc
```

拒否。

---

# 96. Concurrency tests

```text
global semaphore
same-thread lock
different thread concurrency
different client concurrency
```

---

# 97. Timeout tests

fake Codexをsleep。

通常:

```text
504
```

Streaming:

```text
error event
```

---

# 98. SQLite persistence test

可能な範囲で、

```text
DB reopen
↓
client/API key/thread metadata残存
```

を確認。

---

# 99. CLI tests

API key create CLIが、

```text
raw keyを1回だけ表示
```

すること。

list CLIでraw keyが表示されないこと。

---

# 100. README

READMEには以下を順番に記載してください。

## Architecture

```text
Client
→ Bearer API Key
→ FastAPI
→ SQLite auth/audit
→ Codex SDK
→ ChatGPT
```

---

# 101. Setup

```bash
git clone ...
cd codex-api-server

cp .env.example .env
```

生成:

```bash
openssl rand -hex 32
```

を、

```env
API_KEY_PEPPER=
```

へ設定。

---

# 102. Build

```bash
docker compose build
```

---

# 103. Codex login

```bash
docker compose run --rm codex-api \
  python -m cli.codex_auth login
```

表示されたverification URL/codeでChatGPTログイン。

---

# 104. Start

```bash
docker compose up -d
```

---

# 105. Admin creation

```bash
docker compose exec codex-api \
  python -m cli.users create \
  --client-id admin \
  --display-name Administrator \
  --role admin
```

---

# 106. Admin API key

```bash
docker compose exec codex-api \
  python -m cli.api_keys create admin
```

---

# 107. User creation

```bash
docker compose exec codex-api \
  python -m cli.users create \
  --client-id alice \
  --display-name Alice
```

---

# 108. User API key

```bash
docker compose exec codex-api \
  python -m cli.api_keys create alice
```

---

# 109. LAN usage

Server IP:

```text
192.168.1.100
```

Health:

```bash
curl http://192.168.1.100:8000/health
```

---

# 110. /me

```bash
curl \
  -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  http://192.168.1.100:8000/v1/me
```

---

# 111. New thread

```bash
curl -X POST \
  http://192.168.1.100:8000/v1/threads \
  -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repository":"my-project",
    "prompt":"このリポジトリを調査してください"
  }'
```

---

# 112. Continue thread

repositoryはthread metadataから自動解決。

```bash
curl -X POST \
  http://192.168.1.100:8000/v1/threads/THREAD_ID/messages \
  -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt":"その問題を修正し、テストしてください"
  }'
```

---

# 113. Streaming

```bash
curl -N -X POST \
  http://192.168.1.100:8000/v1/threads/THREAD_ID/stream \
  -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt":"作業を続けてください"
  }'
```

---

# 114. API key revoke

```bash
docker compose exec codex-api \
  python -m cli.api_keys revoke KEY_ID
```

---

# 115. Audit

```bash
docker compose exec codex-api \
  python -m cli.audit list --client-id alice --limit 100
```

---

# 116. Security README

READMEに明記:

このAPIは通常のチャットAPIではありません。

Codexは、

```text
filesystem write
shell execution
git
tests
```

を行えるため、

```text
remote code execution capability
```

を持つサービスとして扱う必要があります。

---

# 117. Security recommendations

最低限:

```text
LANのみ
Bearer認証必須
ユーザーごとに別API key
API keyは定期rotation
利用終了ユーザーはdisable
API key revoke
FirewallでLAN subnetに限定
Internet port forwarding禁止
non-root container
Docker socket禁止
host credentials禁止
workspace制限
```

---

# 118. API key storage security

READMEに説明:

SQLiteには、

```text
raw API key
```

を保存せず、

```text
HMAC-SHA-256 digest
```

のみ保存。

`API_KEY_PEPPER` は `.env` に存在するため、

```text
.env
```

も秘密情報として管理。

---

# 119. Prompt injection

untrusted repositoryの、

```text
AGENTS.md
README
source code
comments
scripts
```

等にはagentへの悪意あるinstructionが含まれる可能性があります。

repository自体をuntrusted inputとして扱うことをREADMEに記載。

---

# 120. Git

API Server自身は自動的に、

```text
git push
git reset --hard
git clean -fd
```

しない。

remote credentialもdefaultでmountしない。

---

# 121. Requirements

実装時点の安定versionを確認。

最低限:

```text
fastapi
uvicorn
pydantic
pydantic-settings
openai-codex
httpx
pytest
pytest-asyncio
```

versionを合理的にpin。

---

# 122. SDK確認

コードを書く前に実行:

```bash
python - <<'PY'
import openai_codex

from openai_codex import (
    AsyncCodex,
    ApprovalMode,
    Sandbox,
)

print(openai_codex.__version__)
print(AsyncCodex)
print(ApprovalMode)
print(Sandbox)
PY
```

さらに必要に応じ:

```bash
python -m pydoc openai_codex
```

---

# 123. Error classes

現行 `openai_codex` の公開exceptionも確認してください。

例えば存在する場合:

```text
CodexError
TransportClosedError
InvalidRequestError
ServerBusyError
RetryLimitExceededError
is_retryable_error
```

等。

これらを適切にHTTP errorへmapしてください。

架空のexceptionを作らない。

---

# 124. Validation

完成後:

```bash
python -m compileall app cli

pytest -q

docker compose config

docker compose build
```

Docker利用可能なら:

```bash
docker compose up -d

curl -f http://127.0.0.1:8000/health

docker compose ps

docker compose logs --tail=100 codex-api
```

---

# 125. SQLite確認

さらに、

```bash
docker compose exec codex-api \
  python -m cli.users list
```

と、

```bash
docker compose exec codex-api \
  python -m cli.api_keys list admin
```

等を実際に確認。

---

# 126. LAN確認

可能な環境なら、

```text
0.0.0.0:8000
```

でlistenしていることを確認。

Docker:

```bash
docker compose port codex-api 8000
```

等でも確認。

---

# 127. 完成条件

以下すべてを満たしてください。

```text
[ ] Docker Composeで起動可能

[ ] LANから接続可能
[ ] 0.0.0.0:8000

[ ] SQLite永続化

[ ] 複数client対応
[ ] client_id
[ ] user/admin role

[ ] 複数API key/client
[ ] API key rotation
[ ] revoke
[ ] expire
[ ] disable

[ ] raw API keyをDB保存しない
[ ] HMAC-SHA-256
[ ] API_KEY_PEPPER

[ ] client_id audit
[ ] key_id audit
[ ] request_id audit

[ ] full promptをauditしない
[ ] Authorizationをauditしない

[ ] thread ownership
[ ] 他ユーザーthreadアクセス禁止

[ ] ChatGPT authentication
[ ] Codex auth永続化

[ ] arbitrary cwd禁止
[ ] path traversal防止
[ ] symlink escape防止

[ ] Sandbox.workspace_write
[ ] Sandbox.full_access禁止

[ ] thread create
[ ] thread resume
[ ] thread list
[ ] thread archive

[ ] SSE

[ ] interrupt

[ ] concurrency limit
[ ] thread lock
[ ] timeout

[ ] non-root

[ ] Docker socket禁止

[ ] tests

[ ] README
```

---

# 128. 実装品質

以下を優先:

```text
security
correctness
predictability
testability
simplicity
```

過剰なframework化はしない。

しかし、

```text
authentication
authorization
Codex
database
repository resolution
audit
HTTP routes
```

は適切に責務分離してください。

---

# 129. TODO禁止

完成時に、

```text
TODO
pass
NotImplementedError
dummy implementation
pseudo code
```

を残さないでください。

現在のSDKで実装不能な機能があれば、架空実装をするのではなく、

```text
未対応
理由
SDKの制約
```

をREADMEと最終回答に明記してください。

---

# 130. 最終回答

実装完了後、以下を報告してください。

1. 作成・変更したファイル
2. 使用した `openai-codex` version
3. Codex runtime version
4. Codex認証方式
5. Codex auth永続化path
6. SQLite schema
7. API key hashing方式
8. API_KEY_PEPPERの扱い
9. client / API key管理方法
10. thread ownership方式
11. audit log仕様
12. 実装endpoint一覧
13. Sandbox / Approval設定
14. Docker security設定
15. 実行したpytest
16. pytest結果
17. docker compose config結果
18. docker build結果
19. 起動確認結果
20. 未検証事項
21. 初回Codex login手順
22. admin作成手順
23. user/API key発行手順
24. LANからのcurl例

説明だけで終わらず、実際にファイルを作り、利用可能な範囲ですべて検証してください。
