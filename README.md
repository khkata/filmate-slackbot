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
- Request URL:  
