# filmate-slackbot

## 概要
Slack の会話から映画を 3 本おすすめする Bot。

## 前提
- AWS アカウント
- AWS CLI, SAM CLI がインストール済み
- Secret Manager に以下キーを登録済み  
  ARN: arn:aws:secretsmanager:…/prod/filmmate/slack-…  
  - `slack_bot_token`  
  - `slack_signing_secret`  
  - `tmdb_key`

## デプロイ手順 (1-click)
```bash
git clone https://github.com/＜あなたのユーザ＞/filmate-slackbot.git
cd filmate-slackbot
sam build
sam deploy --guided
# ── 以降は sam deploy だけで OK