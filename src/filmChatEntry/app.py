import os
import json
import time
import logging
import urllib.parse
import base64
import boto3
import hmac
import hashlib

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 環境変数
SLACK_SECRET_ID   = os.environ['SLACK_SECRET_ID']
SESSIONS_TABLE    = os.environ['SESSIONS_TABLE']
CHAT_HANDLER_NAME = os.environ['CHAT_HANDLER_NAME']

# AWS クライアント
secrets_client = boto3.client('secretsmanager', region_name='ap-northeast-1')
dynamodb        = boto3.client('dynamodb')
lambda_client   = boto3.client('lambda')
bedrock         = boto3.client('bedrock-runtime', region_name='ap-northeast-1')

# Secrets のロード
secret_str     = secrets_client.get_secret_value(SecretId=SLACK_SECRET_ID)['SecretString']
secrets        = json.loads(secret_str)
SIGNING_SECRET = secrets['slack_signing_secret'].encode()

def verify(event, raw_body):
    headers = {k.lower(): v for k, v in event.get('headers', {}).items()}
    ts  = headers.get('x-slack-request-timestamp','')
    sig = headers.get('x-slack-signature','')
    if not ts or not sig or abs(time.time() - float(ts)) > 300:
        return False
    basestring = f"v0:{ts}:{raw_body}".encode()
    my_sig = 'v0=' + hmac.new(SIGNING_SECRET, basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(my_sig, sig)

def ask_initial_question():
    """
    Bedrock（Claude）に「最初のアイスブレイク質問」を作らせる例。
    現在時刻・天気情報なども含めた柔軟なプロンプトにすると◎。
    """
    prompt = (
        "あなたは、ユーザーと一緒に映画を観る友人です。"
        "あなたは女の子です。"
        "フレンドリーに話してください。"
        "敬語ではなく、タメ口で話してください。"
        "ユーザーは映画を探しています。"
        "これから映画をおすすめするためにユーザーの好みを分析してください。"
        "ユーザーの好みを自然に掘り下げ、親しい友達のように接してください。"
        "時刻や天気を考慮して、親しみやすい一言＋最初の質問を日本語で返してください。"
        "余計な説明は不要で、質問だけを一文で。"
        "例1：「やっほー！今なにしてるの？暇なら一緒に映画でも観ない？」"
        "例2：「お仕事お疲れ！息抜きに一緒に映画でも観ない？」"
        "例3：「今日は暑いね！休憩に一緒に映画でも観ない？」"
    )
    body = {
        'anthropic_version':'bedrock-2023-05-31',
        'max_tokens': 128,
        'messages': [{'role':'user','content': prompt}]
    }
    res = bedrock.invoke_model(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json"
    )
    text = json.loads(res['body'].read())['content'][0]['text'].strip()
    return text

def lambda_handler(event, context):
    # 署名検証
    raw_body = event.get('body','') or ''
    if event.get('isBase64Encoded', False):
        raw_body = base64.b64decode(raw_body).decode('utf-8')
    if not verify(event, raw_body):
        return {"statusCode": 401, "body": "Invalid signature"}

    # パラメータ解析
    data       = urllib.parse.parse_qs(raw_body)
    user_input = data.get('text', [''])[0].strip()
    channel_id = data.get('channel_id', [''])[0]
    user_id    = data.get('user_id', [''])[0]

    session_id = f"{user_id}#{channel_id}"
    # セッション初期化（必要であれば FilmChatFlow 側でも行う）
    dynamo_resp = dynamodb.get_item(TableName=SESSIONS_TABLE, Key={'sessionId':{'S':session_id}})
    if 'Item' not in dynamo_resp:
        dynamodb.put_item(
            TableName=SESSIONS_TABLE,
            Item={
                'sessionId':   {'S': session_id},
                'preferences': {'S': json.dumps([])},
                'round':       {'N': '0'},
                'updatedAt':   {'N': str(int(time.time()))},
                'ttl':         {'N': str(int(time.time()) + 3600)}
            }
        )

    # 「/filmate」だけで呼ばれた → 最初の質問を即返却
    if user_input == "":
        first_q = ask_initial_question()
        return {
            'statusCode': 200,
            'headers':    {'Content-Type': 'application/json; charset=utf-8'},
            'body': json.dumps({
                "response_type": "ephemeral",
                "text":          first_q
            })
        }

    # user_input がある場合（例：/filmate ジャンル） or フォールバック
    # FilmChatFlow を非同期で呼び出して会話を継続させる
    lambda_client.invoke(
        FunctionName   = CHAT_HANDLER_NAME,
        InvocationType = 'Event',
        Payload        = json.dumps({
            'prompt':     user_input,
            'channel_id': channel_id,
            'user_id':    user_id
        }).encode('utf-8')
    )

    # 簡易レスポンス
    return {
        'statusCode': 200,
        'headers':    {'Content-Type': 'application/json; charset=utf-8'},
        'body': json.dumps({
            "response_type": "ephemeral",
            "text":          "💬 了解！"
        })
    }