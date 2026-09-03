# codex-api-server — セットアップ・起動手順

このファイルは **導入から起動、ユーザー作成、動作確認まで** の手順をまとめたものです。
アーキテクチャ・セキュリティ・API仕様などの説明は [README.md](./README.md) を参照してください。

---

## 全体の流れ

```text
1. Setup        .env を用意して API_KEY_PEPPER を設定
2. Build        docker compose build
3. Codex login  ChatGPT / OpenAI にログイン（← 飛ばすと Codex 実行が失敗）
4. Start        docker compose up -d
5. Admin/User   管理者・利用者と API key を作成
6. 利用         LAN クライアントから curl で利用
```

---

## 1. Setup

```bash
git clone <this-repo>
cd codex-api-server

cp env.example .env
```

`API_KEY_PEPPER` を生成して設定してください:

```bash
openssl rand -hex 32
```

生成した値を `.env` の `API_KEY_PEPPER=` に設定します。

> `API_KEY_PEPPER` を失うと既存 API key を検証できなくなります。必ずバックアップしてください（詳細は [README.md](./README.md) の「API_KEY_PEPPER の重要性」を参照）。

---

## 2. Build

```bash
docker compose build
```

---

## 3. Codex login

**この手順を飛ばすと `/v1/threads` などの Codex 実行が失敗します。必ず一度実行してください。**

このサーバーは、バックエンドの Codex が ChatGPT / OpenAI にログイン済みでないと、Codex を呼び出すエンドポイントが失敗します。デフォルトは `CODEX_AUTH_MODE=chatgpt` で、既存の Codex 認証セッションがあれば再利用し、初回は Device Code login を使用します。

### ログイン手順 (ChatGPT / Device Code)

1. Codex ログインコマンドを実行します。`run --rm` を使うのは、ログインだけを一時コンテナで行い、認証情報を永続 volume (`codex-auth`) に書き込むためです。

   ```bash
   docker compose run --rm codex-api python -m cli.codex_auth login
   ```

2. すると以下のように **Verification URL** と **Code** が表示されます。

   ```text
   Verification URL:
   https://auth.openai.com/device

   Code:
   ABCD-1234

   Waiting for login to complete...
   ```

3. **PC やスマホのブラウザで Verification URL を開き、表示された Code を入力**して、ChatGPT アカウントでログインを承認します。

4. 承認が完了すると、コマンド側に `Login successful.` と表示されて終了します。認証情報は named volume `codex-auth` (`/home/codex/.codex`) に保存され、コンテナを再起動・再ビルドしても保持されます。

5. ログイン状態は次のコマンドで確認できます(token や email は表示しません)。

   ```bash
   docker compose run --rm codex-api python -m cli.codex_auth status
   # authenticated: True
   # auth_mode: chatgpt
   ```

### ログイン手順 (OpenAI API key / fallback)

ChatGPT アカウントではなく OpenAI API key を使う場合は、`.env` に以下を設定します。

```env
CODEX_AUTH_MODE=api_key
OPENAI_API_KEY=sk-...
```

この場合、サーバー起動時に `codex.login_api_key()` が自動で実行されるため、上記の device code ログインは不要です(明示的にログインしたい場合は `docker compose run --rm codex-api python -m cli.codex_auth login` でも実行できます)。

---

## 4. Start

```bash
docker compose up -d
```

起動後、`GET /health` の `"authenticated": true` で Codex 認証済みか確認できます。

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","codex":"ready","authenticated":true,"database":"ready"}
```

---

## 5. Admin / User と API key の作成

### Admin作成

```bash
docker compose exec codex-api python -m cli.users create \
  --client-id admin --display-name Administrator --role admin
```

### Admin API key

```bash
docker compose exec codex-api python -m cli.api_keys create admin
```

### User作成

```bash
docker compose exec codex-api python -m cli.users create \
  --client-id alice --display-name Alice
```

### User API key

```bash
docker compose exec codex-api python -m cli.api_keys create alice
```

> raw API key が表示されるのは作成時の1回だけです。安全に保管してください。

---

## 6. LAN利用例

Server IP を `192.168.1.100` とします。

### Health (認証不要)

```bash
curl http://192.168.1.100:8000/health
```

### /v1/me

```bash
curl -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  http://192.168.1.100:8000/v1/me
```

### 新規thread

```bash
curl -X POST http://192.168.1.100:8000/v1/threads \
  -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repository":"my-project",
    "prompt":"このリポジトリを調査してください"
  }'
```

### thread継続 (repositoryはthread metadataから自動解決)

```bash
curl -X POST http://192.168.1.100:8000/v1/threads/THREAD_ID/messages \
  -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt":"その問題を修正し、テストしてください"
  }'
```

### Streaming

```bash
curl -N -X POST http://192.168.1.100:8000/v1/threads/THREAD_ID/stream \
  -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt":"作業を続けてください"
  }'
```

### API key revoke

```bash
docker compose exec codex-api python -m cli.api_keys revoke KEY_ID
```

### 監査ログ

```bash
docker compose exec codex-api python -m cli.audit list --client-id alice --limit 100
```

---

## トラブルシュート

### `{"detail":"Internal server error."}` が返る

このメッセージは本サーバーの統一エラースキーマ(`{"error":{"code":...}}`)**ではなく**、アプリのリクエストハンドラに到達する前に返る Starlette / FastAPI のデフォルト応答です。典型的な原因は次のとおりです。

- **バックエンド Codex が起動に失敗している**: 最も多い原因です。`CODEX_HOME`(コンテナ内 `/home/codex/.codex`)ディレクトリが存在しない、あるいは Codex ランタイムがログインできず、FastAPI の起動処理(lifespan)自体が失敗している状態です。

  対処:

  1. ログを確認します。`TransportClosedError` や `CODEX_HOME ... does not exist` が出ていないか見てください。

     ```bash
     docker compose logs --tail=100 codex-api
     ```

  2. 上記「3. Codex login」に従って Codex ログインを完了させます。
  3. サーバーを再起動します。

     ```bash
     docker compose up -d --force-recreate
     ```

- **Codex はログイン済みだが、prompt 実行時に上流が失敗している**: この場合はアプリのハンドラに到達しているため、`{"detail":...}` ではなく `{"error":{"code":"codex_error",...}}` (HTTP 502) や `{"error":{"code":"codex_unavailable",...}}` (HTTP 503) が返ります。`codex_error` で `401 Unauthorized ... api.openai.com` のようなメッセージが出る場合は、Codex のログインが切れているので再ログインしてください。

補足: `docker` を使わずローカルで直接 `uvicorn` を起動して試す場合も、`CODEX_HOME` を実在するディレクトリに設定し、`python -m cli.codex_auth login` でログインを済ませてから起動してください。ディレクトリが無いと Codex ランタイムが起動に失敗します。

### 認証の永続化について

Codex runtime (codex-cli) は `CODEX_HOME` 環境変数が指すディレクトリ(デフォルト `~/.codex`)に認証情報を保存します。本サーバーでは Dockerfile 内で `CODEX_HOME=/home/codex/.codex` を設定し、named volume `codex-auth` でこのディレクトリを永続化しています。そのためコンテナを再起動・再ビルドしてもログインは保持されます。

```yaml
volumes:
  - codex-auth:/home/codex/.codex
```

`codex-data` (SQLite) と `codex-auth` (Codex/ChatGPT認証) は明確に分離されています。
