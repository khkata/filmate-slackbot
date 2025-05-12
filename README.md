filmate-slackbot

Slack の会話から映画を 3 本おすすめする Bot

⸻

目次
	1.	概要
	2.	前提条件
	3.	Slack App の設定
	4.	1-Click Deploy 手順
	5.	環境変数について
	6.	コマンド仕様・使い方
	7.	動作確認 (テスト)
	8.	フォルダ構成
	9.	補足

⸻

概要

Slack 上で /filmate コマンドを打つと、TMDB から取得した映画のおすすめを 3 本返してくれる Bot です。
	•	セッション管理に DynamoDB を使用
	•	Slack 認証情報や TMDB API キーは AWS Secrets Manager で管理
	•	API Gateway (HttpApi) × Lambda（3 関数）で構成

⸻

前提条件
	1.	AWS アカウント
	2.	AWS CLI (aws configure が完了していること)
	3.	AWS SAM CLI (sam --version で SAM CLI, version ... が表示されること)
	4.	Slack App 作成済み
	5.	AWS Secrets Manager に以下のシークレットが登録済み
	•	slack_bot_token
	•	slack_signing_secret
	•	tmdb_key

⸻

Slack App の設定
	1.	Slash Command
	•	コマンド: /filmate
	•	Request URL:

https://<あなたのAPIドメイン>/prod/filmChatEntry


	•	Method: POST

	2.	Event Subscriptions
	•	Enable Events: ✅
	•	Request URL:

https://<あなたのAPIドメイン>/prod/events


	•	Subscribe to bot events:
	•	message.channels
	•	message.im
	•	必要に応じて追加してください

	3.	OAuth & Permissions
	•	権限スコープ:
	•	commands
	•	chat:write
	•	incoming-webhook
	•	（必要に応じて他を追加）
	4.	App Home
	•	（任意）Home タブに Bot の説明などを設定できます

⸻

1-Click Deploy 手順

# リポジトリをクローン
git clone https://github.com/<あなたのユーザ名>/filmate-slackbot.git
cd filmate-slackbot

# SAM ビルド
sam build

# 初回デプロイ（設定ガイド付き）
sam deploy --guided

# 再デプロイ（2 回目以降はオプション省略可）
sam deploy

デプロイが成功すると、SAM が次のような出力を表示します:

Key                 HttpApiUrl
Description         Bot の HTTP API ベース URL
Value               https://xxxxxxx.execute-api.ap-northeast-1.amazonaws.com/prod

この Value の URL が <あなたのAPIドメイン> に該当します。

⸻

環境変数について

変数名	内容
SLACK_BOT_TOKEN	Secrets Manager から取得される Bot トークン
SLACK_SIGNING_SECRET	Secrets Manager から取得される署名検証用シークレット
TMDB_KEY	TMDB API キー
SESSIONS_TABLE	DynamoDB テーブル名 (FileChatSessions)
CHAT_HANDLER_NAME	会話フロー実行 Lambda 関数名

これらは template.yaml の Environment.Variables で自動的に設定されます。

⸻

コマンド仕様・使い方

/filmate (filmChatEntry)
	•	説明: 映画のおすすめをはじめる
	•	例:

/filmate おすすめのアクション映画


	•	挙動:
	1.	Slack から受け取ったテキストを元に TMDB API を呼び出す
	2.	DynamoDB にセッションを作成/更新
	3.	会話フロー Lambda (filmChatFlow) を非同期呼び出し
	4.	最終的に Slack におすすめ結果を投稿

Events API (events)
	•	説明: インタラクティブイベント（ボタンクリックなど）やその他イベントを受信
	•	ルート: /events
	•	利用例: 会話中の「もっと見る」ボタン押下など

⸻

動作確認 (テスト)

curl での確認

Slash Command テスト:

curl -X POST \
  https://<あなたのAPIドメイン>/prod/filmChatEntry \
  -H 'Content-Type: application/json' \
  -d '{"text":"おすすめのコメディ映画"}'

Events ハンドラ テスト:

curl -X POST \
  https://<あなたのAPIドメイン>/prod/events \
  -H 'Content-Type: application/json' \
  -d '{"type":"block_actions","user":{"id":"U12345"},"actions":[...]}'


⸻

フォルダ構成

/ (リポジトリルート)
├── template.yaml
├── README.md
└── src
    ├── filmChatEntry
    │   └── app.py
    ├── filmChatFlow
    │   └── app.py
    └── eventsHandler
        └── app.py


⸻

補足
	•	リージョン: ap-northeast-1（東京）を想定しています。
	•	その他質問やカスタマイズについては Issue を立ててください。
