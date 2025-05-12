import os, json, time, logging, boto3, hmac, hashlib

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 環境変数
SLACK_SECRET_ID   = os.environ['SLACK_SECRET_ID']
CHAT_HANDLER_NAME = os.environ['CHAT_HANDLER_NAME']
REGION            = os.environ.get('AWSREGION','ap-northeast-1')

# AWS クライアント
secrets_client = boto3.client('secretsmanager', region_name=REGION)
lambda_client  = boto3.client('lambda', region_name=REGION)

# 署名用シークレット取得
secret_str     = secrets_client.get_secret_value(SecretId=SLACK_SECRET_ID)['SecretString']
SIGNING_SECRET = json.loads(secret_str)['slack_signing_secret'].encode()

def verify_slack(event_body, headers):
    ts  = headers.get('x-slack-request-timestamp','')
    sig = headers.get('x-slack-signature','')
    if not ts or abs(time.time() - float(ts)) > 300:
        return False
    basestring = f"v0:{ts}:{event_body}".encode()
    my_sig = 'v0=' + hmac.new(SIGNING_SECRET, basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(my_sig, sig)

# ← ここからトップレベルで定義する
def lambda_handler(event, context):
    logger.info("EVENT RECEIVED: %s", json.dumps(event, ensure_ascii=False))
    # 1) Body／ヘッダー取得
    body    = event.get('body','')
    headers = {k.lower():v for k,v in event.get('headers',{}).items()}

    # 2) JSON parse（チャレンジ検証用）
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {'statusCode':400,'body':'invalid json'}

    # ── URL verification ──────────────────────
    if data.get('type') == 'url_verification':
        logger.info("Responding to URL verification")
        return {
            'statusCode': 200,
            'headers':    {'Content-Type':'text/plain'},
            'body':       data['challenge']
        }

    # ── 署名検証 ──────────────────────────────
    if not verify_slack(body, headers):
        logger.warning("Invalid signature")
        return {'statusCode':401,'body':'invalid signature'}

    # ── イベント処理 ──────────────────────────
    ev = data.get('event',{})
    # ボット自身のメッセージは無視
    if ev.get('bot_id'):
        return {'statusCode':200}

    # テキスト＆チャンネル＆ユーザー取得
    text    = ev.get('text','').strip()
    channel = ev.get('channel')
    user    = ev.get('user')

    # filmChatFlow を非同期呼び出し
    lambda_client.invoke(
        FunctionName   = CHAT_HANDLER_NAME,
        InvocationType = 'Event',
        Payload        = json.dumps({
            'prompt':     text,
            'channel_id': channel,
            'user_id':    user
        }).encode('utf-8')
    )
    return {'statusCode':200}
