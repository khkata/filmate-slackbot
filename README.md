# filmate-slackbot

Slack の会話から映画を 3本おすすめする Bot

## 前提条件

1. AWS アカウント・CLI（`aws configure`）  
2. AWS SAM CLI（`sam --version` で確認）  
3. Slack App 作成済み  
   - Slash Command `/filmate`  
   - Event Subscriptions に以下の URL を設定  
     - `https://<あなたのAPIドメイン>/filmChatEntry`  
     - `https://<あなたのAPIドメイン>/events`  
   - OAuth スコープ: `commands`, `chat:write`, `incoming-webhook`  
4. SecretsManager に登録済みシークレット  
   - `slack_bot_token`, `slack_signing_secret`, `tmdb_key`

## デプロイ手順 (1-Click)

```bash
# 1. リポジトリをクローン
git clone https://github.com/<あなたのユーザ名>/filmate-slackbot.git
cd filmate-slackbot

# 2. ビルド
sam build

# 3. デプロイ (初回は --guided)
sam deploy --guided
