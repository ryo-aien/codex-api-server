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

このサーバーは、バックエンドの Codex が ChatGPT / OpenAI にログイン済みでないと、Codex を呼び出すエンドポイントが失敗します。デフォルトは `CODEX_AUTH_MODE=chatgpt` です。

このプロジェクトでは、**ホストPCの `~/.codex/auth.json` という認証ファイル1つだけを、コンテナに read-only でバインドマウント**します。つまり **ホストPCで `codex login` を済ませておけば、その認証がそのままコンテナに反映されます。** コンテナ内でブラウザを開いたり device code を入力したりする必要はありません。

Codex ランタイムは起動時に sqlite やログを書き込みますが、それらは **コンテナ専用のボリューム (`codex-home`) に書かれ、ホストの `~/.codex` には一切書き込まれません。** ホストから渡すのは `auth.json` 1ファイル(読み取り専用)だけです。

### ログイン手順 (ChatGPT / ホストPCでログイン)

前提: ホストPCに codex CLI がインストールされていること。

1. ホストPCで通常どおりログインします。ホストのブラウザが自動で開くので、そのまま ChatGPT ログインを完了してください。

   ```bash
   codex login
   ```

   完了すると、ホストの `~/.codex/`(正確には `$CODEX_HOME`、デフォルト `~/.codex`)に `auth.json` が作成されます。ホスト側でログイン状態を確認するには:

   ```bash
   codex login status
   # または
   ls -l ~/.codex/auth.json
   ```

2. `.env` に、ホストの `~/.codex` **ディレクトリの絶対パス**を設定します。docker compose は `~` を展開しないため、必ず絶対パスで書いてください。

   ```env
   # macOS の例（ユーザー名が ryo の場合）
   CODEX_AUTH_HOST_DIR=/Users/ryo/.codex
   # Linux の例（ユーザー名が youruser の場合）
   # CODEX_AUTH_HOST_DIR=/home/youruser/.codex
   ```

   自分のパスは次で確認できます:

   ```bash
   echo "$HOME/.codex"
   ```

   > **注意:** ここに指定するのは**ディレクトリ**です。**末尾に `/auth.json` を付けないでください。**
   > compose 側で `${CODEX_AUTH_HOST_DIR}/auth.json` と付与しているため、`/auth.json` まで書くとパスが二重(`.../auth.json/auth.json`)になり、Docker が空ディレクトリを作って認証が読めなくなります(コンテナ内の `auth.json` がディレクトリ扱いになる場合はこれが原因です)。

3. コンテナ側からログイン状態を確認します(token や email は表示しません)。

   ```bash
   docker compose run --rm codex-api python -m cli.codex_auth status
   # authenticated: True
   # auth_mode: chatgpt
   ```

   ここが `authenticated: True` になっていれば、`docker compose up -d` した本体でも認証済みになります。

> 補足:
> - バインドするのは `auth.json` 1ファイルのみ・read-only です。コンテナはこのファイルを読み取るだけで書き換えません。Codex の作業用 sqlite/ログはコンテナ専用ボリューム (`codex-home`) に書かれ、ホストの `~/.codex` は汚れません。
> - `auth.json` はホスト側に**必ず存在**している必要があります(先に `codex login` を済ませること)。存在しないと、Docker がその場所をディレクトリとして作ってしまい、認証が読めません。
> - トークンの再取得が必要になった場合は、ホストPCで `codex login` をやり直せば、次回のコンテナ起動時に反映されます。
> - ホスト側の `~/.codex/auth.json` は秘密情報なので取り扱いに注意してください。

### ログイン手順 (OpenAI API key / fallback)

ChatGPT アカウントではなく OpenAI API key を使う場合は、`.env` に以下を設定します。

```env
CODEX_AUTH_MODE=api_key
OPENAI_API_KEY=sk-...
```

この場合、サーバー起動時に `codex.login_api_key()` が自動で実行されるため、上記のホストログイン／バインドは不要です。

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

### サーバーの LAN IP を確認する

以降の例では、サーバーの LAN IP を **`$SERVER_IP`** というシェル変数で表します。まず自分のサーバーの LAN IP を調べて、この変数に入れてください。

- macOS:

  ```bash
  SERVER_IP=$(ipconfig getifaddr en0)   # Wi-Fi。有線なら en1
  ```

- Linux:

  ```bash
  SERVER_IP=$(hostname -I | awk '{print $1}')
  ```

設定できたか確認します:

```bash
echo "$SERVER_IP"        # 例: 192.168.1.42 のように表示される
```

> `SERVER_IP` は今開いているターミナル内だけで有効な一時変数です(ファイルには保存されません)。ターミナルを開き直したら、もう一度上のコマンドで設定してください。

まず**サーバー自身**から、その IP で疎通するか確認します:

```bash
curl "http://$SERVER_IP:8000/health"
# {"status":"ok",...} が返れば LAN 公開 OK。以降は他PCからも http://<このIP>:8000 でアクセスできます
```

> `127.0.0.1` は「同じPC内からのみ」アクセスできるアドレスです。他のPCから使うには、上で調べた `192.168.x.x` の LAN IP を使ってください。
>
> 繋がらない場合は、下記「[トラブルシュート](#トラブルシュート)」の LAN 疎通の項を参照してください。

以降の例はこの `$SERVER_IP` をそのまま使っています。**同じターミナルで**続けて実行してください(他PCから叩くときは、`$SERVER_IP` を実際の IP に置き換えてください)。

### Health (認証不要)

```bash
curl "http://$SERVER_IP:8000/health"
```

### /v1/me

```bash
curl -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  "http://$SERVER_IP:8000/v1/me"
```

### 新規thread

```bash
curl -X POST "http://$SERVER_IP:8000/v1/threads" \
  -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repository":"test",
    "prompt":"このリポジトリを調査してください"
  }'
```

### thread継続 (repositoryはthread metadataから自動解決)

```bash
curl -X POST "http://$SERVER_IP:8000/v1/threads/THREAD_ID/messages" \
  -H "Authorization: Bearer $CODEX_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt":"その問題を修正し、テストしてください"
  }'
```

### Streaming

```bash
curl -N -X POST "http://$SERVER_IP:8000/v1/threads/THREAD_ID/stream" \
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


### LAN の他PCから繋がらない / `192.168.x.x` で接続できない

まず切り分けます。

1. **サーバー自身**で `127.0.0.1` は繋がるか。

   ```bash
   curl http://127.0.0.1:8000/health
   ```

   これが返らないなら、そもそもサーバーが起動できていません(上のトラブルシュート参照)。

2. **サーバー自身**で、自分の LAN IP では繋がるか。

   ```bash
   SERVER_IP=$(ipconfig getifaddr en0)   # macOS。Linux は hostname -I の先頭
   echo "$SERVER_IP"
   curl "http://$SERVER_IP:8000/health"
   ```

   - 繋がる → サーバーは LAN 公開できています。他PCからは `http://<この $SERVER_IP の値>:8000` を使ってください。
   - 繋がらない → 3 へ。

3. **ポートが全インターフェースで公開されているか**確認します。

   ```bash
   docker compose port codex-api 8000
   # 0.0.0.0:8000 と出れば OK。127.0.0.1:8000 だとローカル限定
   ```

4. **ホストのファイアウォール**を確認します。

   - macOS: システム設定 → ネットワーク → ファイアウォール。オンだと外部からの 8000 番接続がブロックされることがあります。LAN テスト中は一時的にオフにするか、接続を許可してください。
   - Linux: `ufw` や `firewalld` で TCP 8000 を LAN サブネットから許可してください(README「LAN公開 / Firewall / CORS」参照)。

5. 他PCと**同じLAN/サブネットにいるか**、Wi-Fi のゲストネットワーク分離(AP アイソレーション)が有効になっていないかも確認してください。

> なお、繋がらないときに `docker compose up -d` を繰り返しても状況は変わりません。接続失敗(curl の timeout)はネットワーク/ファイアウォール側の問題で、サーバー自体は起動したままです。

### 認証の永続化について

Codex runtime (codex-cli) は `CODEX_HOME`(コンテナ内 `/home/codex/.codex`)に、認証だけでなく起動時に作業用の sqlite/ログも書き込みます。そのため本サーバーでは次のように分離しています。

```yaml
volumes:
  # Codex の作業用 sqlite/ログはコンテナ専用ボリュームへ（ホストには書かない）
  - codex-home:/home/codex/.codex
  # ホストの auth.json 1ファイルだけを read-only でバインド
  - ${CODEX_AUTH_HOST_DIR}/auth.json:/home/codex/.codex/auth.json:ro
```

- 認証は**ホストの `auth.json` 1ファイル**(read-only)から。ホストで `codex login` し直せば次回起動時に反映されます。
- Codex の作業状態はコンテナ専用ボリューム `codex-home` に入り、ホストの `~/.codex` を汚しません。
- 本アプリの SQLite (クライアント/APIキー/監査ログ) は別ボリューム `codex-data` (`/data`) に保存され、Codex 認証/状態とは明確に分離されています。

> `.env` の `CODEX_AUTH_HOST_DIR` には**ディレクトリ**(例 `/Users/youruser/.codex`)を指定してください。末尾に `/auth.json` を付けないこと(compose 側で付与しています)。付けると存在しないパスになり、Docker が空ディレクトリを作って認証が読めなくなります。
