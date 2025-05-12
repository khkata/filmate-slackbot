# filmate-slackbot

Slack の会話から映画を 3 本おすすめする Bot

## 目次

1. [概要](#概要)  
2. [前提条件](#前提条件)  
3. [Slack App の設定](#slack-app-の設定)  
4. [1-Click Deploy 手順](#1-click-deploy-手順)  
5. [環境変数について](#環境変数について)  
6. [コマンド仕様・使い方](#コマンド仕様使い方)  
7. [動作確認 (テスト)](#動作確認-テスト)  
8. [フォルダ構成](#フォルダ構成)  
9. [補足](#補足)  

---

## 概要

Slack 上で `/filmate` コマンドを打つと、TMDB から取得した映画のおすすめを 3 本返してくれる Bot です。

- セッション管理に DynamoDB を使用  
- Slack 認証情報や TMDB API キーは AWS Secrets Manager で管理  
- API Gateway (HttpApi) × Lambda（3 関数）で構成  

---

## 前提条件

1. AWS アカウント  
2. AWS CLI（`aws configure` が完了していること）  
3. AWS SAM CLI（`sam --version` でバージョン確認）  
4. Slack App 作成済み  
5. AWS Secrets Manager に以下のシークレットが登録済み  
   - `slack_bot_token`  
   - `slack_signing_secret`  
   - `tmdb_key`  

---

## Slack App の設定

### 1. Slash Command

- コマンド: `/filmate`  
- Request URL: https://<あなたのAPIドメイン>/prod/filmChatEntry
- Method: `POST`  

### 2. Event Subscriptions

- Enable Events: ✅  
- Request URL: https://<あなたのAPIドメイン>/prod/events

- Subscribe to bot events:
- `message.channels`  
- `message.im`  

### 3. OAuth & Permissions

- 権限スコープ:
- `commands`  
- `chat:write`  
- `incoming-webhook`  

---

## 1-Click Deploy 手順

```bash
# リポジトリをクローン
git clone https://github.com/<あなたのユーザ名>/filmate-slackbot.git
cd filmate-slackbot

# SAM ビルド
sam build

# 初回デプロイ（設定ガイド付き）
sam deploy --guided

# 再デプロイ（2 回目以降はオプション省略可）
sam deploy

デプロイが成功すると、以下のような出力が表示されます:
- Key                 HttpApiUrl
- Description         Bot の HTTP API ベース URL
- Value               https://xxxxxxx.execute-api.ap-northeast-1.amazonaws.com/prod
この Value の URL が <あなたのAPIドメイン> に該当します。

---

## 環境変数について

以下の環境変数は、`template.yaml` の `Environment.Variables` によって自動的に設定されます。

| 変数名               | 内容                                                        |
|----------------------|-------------------------------------------------------------|
| `SLACK_BOT_TOKEN`      | Secrets Manager から取得される Slack Bot のトークン        |
| `SLACK_SIGNING_SECRET` | Secrets Manager から取得される署名検証用のシークレット     |
| `TMDB_KEY`             | TMDB の API キー                                            |
| `SESSIONS_TABLE`       | 使用する DynamoDB テーブル名（例: `FileChatSessions`）     |
| `CHAT_HANDLER_NAME`    | 会話フロー実行用の Lambda 関数名                           |

---
