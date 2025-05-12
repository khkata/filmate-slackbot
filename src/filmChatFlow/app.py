import os
import json
import time
import logging
import urllib.request
import urllib.parse
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 環境変数
SLACK_SECRET_ID = os.environ['SLACK_SECRET_ID']
SESSIONS_TABLE  = os.environ['SESSIONS_TABLE']

# AWS クライアント
secrets_client = boto3.client('secretsmanager', region_name='ap-northeast-1')
dynamodb       = boto3.client('dynamodb')
bedrock        = boto3.client('bedrock-runtime', region_name='ap-northeast-1')

# Secrets のロード
secret_str   = secrets_client.get_secret_value(SecretId=SLACK_SECRET_ID)['SecretString']
secrets      = json.loads(secret_str)
SLACK_TOKEN  = secrets['slack_bot_token']
TMDB_KEY     = secrets['tmdb_key']

TMDB_BASE  = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

def init_session(session_id):
    """
    session_id で新規セッションを作成。
    preferences=[]、round=0、ttl=今から1時間後
    """
    now = int(time.time())
    ttl = now + 3600  # Unixエポック秒で1時間後
    dynamodb.put_item(
        TableName=SESSIONS_TABLE,
        Item={
            'sessionId':   {'S': session_id},
            'preferences': {'S': json.dumps([])},
            'round':       {'N': '0'},
            'updatedAt':   {'N': str(now)},
            'ttl':         {'N': str(ttl)}
        }
    )

def get_session(session_id):
    """
    DynamoDB からセッションを取得。なければ init_session を呼ぶ。
    """
    resp = dynamodb.get_item(
        TableName=SESSIONS_TABLE,
        Key={'sessionId': {'S': session_id}}
    )
    if 'Item' not in resp:
        # テーブルになければ新規登録して返す
        init_session(session_id)
        return {'sessionId': session_id, 'round': 0, 'preferences': []}

    item = resp['Item']
    return {
        'sessionId':   session_id,
        'round':       int(item.get('round', {'N': '0'})['N']),
        'preferences': json.loads(item.get('preferences', {'S': '[]'})['S'])
    }

def update_session(session):
    now = int(time.time())
    dynamodb.put_item(
        TableName=SESSIONS_TABLE,
        Item={
            'sessionId':   {'S': session['sessionId']},
            'preferences': {'S': json.dumps(session['preferences'])},
            'round':       {'N': str(session['round'])},
            'updatedAt':   {'N': str(now)}
        }
    )

def delete_session(session_id):
    """
    セッション終了後に削除（オプション）。
    """
    dynamodb.delete_item(
        TableName=SESSIONS_TABLE,
        Key={'sessionId': {'S': session_id}}
    )

_genre_cache = None

def fetch_keyword_ids(query):
    url = f"{TMDB_BASE}/search/keyword?api_key={TMDB_KEY}&query={urllib.parse.quote_plus(query)}"
    data = json.loads(urllib.request.urlopen(url).read())
    return [kw['id'] for kw in data.get('results', [])]

def tmdb_discover_with_keywords(keyword_ids, n=3):
    params = {
        'api_key':       TMDB_KEY,
        'language':      'ja-JP',
        'sort_by':       'popularity.desc',
        'vote_count.gte':'100',
        'with_keywords': ",".join(map(str, keyword_ids))
    }
    data = json.loads(urllib.request.urlopen(
        f"{TMDB_BASE}/discover/movie?{urllib.parse.urlencode(params)}"
    ).read())
    return data.get('results', [])[:n]

def recommend_movies(query, n=3):
    # 1) キーワード絞り込み
    kw_ids = fetch_keyword_ids(query)
    if kw_ids:
        return tmdb_discover_with_keywords(kw_ids, n)

    # 2) ジャンル絞り込み
    gids = extract_genre_ids(query)
    if gids:
        return tmdb_discover(query, n)

    # 3) タイトル検索
    results = tmdb_search(query, n)
    if results:
        return results

    # 最終フォールバック: 空リスト
    return []

def ask_claude_for_titles(preferences):
    keywords = "、".join(preferences)
    prompt = f"""
以下の条件を満たす映画を日本語タイトルで 3 本、JSON 形式で教えてください。
・キーワード: {keywords}
・返却例:
[
  {{ "title": "チャーリーとチョコレート工場", "reason": "チョコレート工場を描いた物語で…"}}, 
  …
]
・必ず JSON 配列だけを返してください（余計なテキスト禁止）
"""
    body = {
        'anthropic_version': 'bedrock-2023-05-31',
        'max_tokens': 512,
        'messages': [{'role':'user', 'content': prompt}]
    }
    res = bedrock.invoke_model(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json"
    )
    text = json.loads(res['body'].read())['content'][0]['text']
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error("Claude JSON parse error: %s", text)
        return []

def get_movie_details_from_tmdb(title):
    safe_query = urllib.parse.quote_plus(title)
    url = (
        f"{TMDB_BASE}/search/movie?"
        f"api_key={TMDB_KEY}&"
        f"query={safe_query}&"
        f"language=ja-JP&"
        f"include_adult=false"
    )
    try:
        with urllib.request.urlopen(url) as res:
            data = json.loads(res.read())
    except Exception as e:
        logger.error(f"TMDB search error for title={title}: {e}")
        return None

    results = data.get('results', [])
    if not results:
        logger.warning(f"TMDB search returned no results for title={title}")
        return None

    m = results[0]
    return {
        'title':        m.get('title'),
        'release_date': (m.get('release_date','')[:4] or ''),
        'overview':     m.get('overview','（概要なし）'),
        'poster_path':  m.get('poster_path')
    }

def fetch_genre_list():
    global _genre_cache
    if _genre_cache is None:
        url = f"{TMDB_BASE}/genre/movie/list?api_key={TMDB_KEY}&language=ja-JP"
        data = json.loads(urllib.request.urlopen(url).read())
        _genre_cache = {g['name'].lower(): g['id'] for g in data.get('genres', [])}
    return _genre_cache

def extract_genre_ids(query):
    genres = fetch_genre_list()
    return [gid for name, gid in genres.items() if name in query.lower()]

def tmdb_discover(query, n=3):
    params = {
        'api_key':       TMDB_KEY,
        'language':      'ja-JP',
        'sort_by':       'popularity.desc',
        'vote_count.gte':'100'
    }
    gids = extract_genre_ids(query)
    if gids:
        params['with_genres'] = ",".join(map(str, gids))
    data = json.loads(urllib.request.urlopen(
        f"{TMDB_BASE}/discover/movie?{urllib.parse.urlencode(params)}"
    ).read())
    return data.get('results', [])[:n]

import urllib.error

def tmdb_search(query, n=3):
    # 改行をスペースに置き換え、長すぎる場合は切り詰め
    safe_query = " ".join(query.split())
    safe_query = safe_query[:100]  # 最大100文字までに制限

    # URL 組み立て
    url = (
        f"{TMDB_BASE}/search/movie?"
        f"api_key={TMDB_KEY}&"
        f"query={urllib.parse.quote_plus(safe_query)}&"
        f"language=ja-JP&"
        f"include_adult=false"
    )
    logger.info(f"[tmdb_search] URL: {url}")
    try:
        resp = urllib.request.urlopen(url)
        data = json.loads(resp.read())
        return data.get('results', [])[:n]
    except urllib.error.HTTPError as e:
        # 本文を読んでログ出力
        body = e.read().decode('utf-8', errors='ignore') if hasattr(e, 'read') else ''
        logger.error(f"[tmdb_search] HTTPError {e.code} {e.reason} body={body}")
        return []
    except Exception as e:
        logger.error(f"[tmdb_search] Unexpected error: {e}", exc_info=True)
        return []

def summarize_batch(movies, max_retries=3):
    contents = "\n\n".join(
        f"タイトル: {m['title']}\nあらすじ: {m.get('overview','（概要なし）')}"
        for m in movies
    )
    prompt = "次の映画それぞれのあらすじを80文字以内の日本語で要約してください。\n\n" + contents
    body = {
        'anthropic_version':'bedrock-2023-05-31',
        'max_tokens':512,
        'messages':[{'role':'user','content':prompt}]
    }
    for i in range(max_retries):
        try:
            res = bedrock.invoke_model(
                modelId="anthropic.claude-3-haiku-20240307-v1:0",
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json"
            )
            text = json.loads(res['body'].read())['content'][0]['text']
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            summaries = [ln.split(":",1)[1].strip() for ln in lines if ln.startswith("あらすじ:")]
            if len(summaries) == len(movies):
                return summaries
        except Exception:
            time.sleep(2**i)
    # フォールバック
    return [
        (m.get("overview","")[:80] + "...") if len(m.get("overview",""))>80 else m.get("overview","")
        for m in movies
    ]

def make_blocks(movies, summaries):
    blocks = [
        {'type':'section','text':{'type':'mrkdwn','text':'🎬 *おすすめ映画一覧*'}},
        {'type':'divider'}
    ]
    for m, s in zip(movies, summaries):
        if m.get("poster_path"):
            blocks.append({'type':'image','image_url':IMAGE_BASE+m['poster_path'],'alt_text':m['title']})
        blocks.append({
            'type':'section',
            'text':{'type':'mrkdwn','text':f"*{m['title']}* ({m.get('release_date','')[:4]})\n{s}"}
        })
        blocks.append({'type':'divider'})
    if blocks and blocks[-1]['type']=='divider':
        blocks.pop()
    return blocks

def post_ephemeral(channel, user, text=None, blocks=None):
    url = "https://slack.com/api/chat.postEphemeral"
    payload = {"channel":channel, "user":user}
    if text:
        payload["text"] = text
    if blocks:
        payload["blocks"] = blocks
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f"Bearer {SLACK_TOKEN}",
            'Content-Type':  'application/json; charset=utf-8'
        }
    )
    with urllib.request.urlopen(req) as res:
        logger.info("postEphemeral response: %s", res.read().decode('utf-8'))

SYSTEM_MSG = (
    "あなたは、ユーザーと一緒に映画を観る友人です。"
    "あなたは女の子です。"
    "フレンドリーに話してください。"
    "敬語ではなく、タメ口で話してください。"
    "ユーザーは映画を探しています。"
    "これから映画をおすすめするためにユーザーの好みを分析してください。"
    "ユーザーの好みを自然に掘り下げ、親しい友達のように接してください。"
)

def build_messages(session, user_input):
    prefix = SYSTEM_MSG
    if session['preferences']:
        prefix += "\nこれまでの好み: " + "、".join(session['preferences'])
    return [{'role':'user','content':prefix + "\nユーザー: " + user_input}]

def lambda_handler(event, context):
    prompt     = event.get('prompt','')
    channel_id = event.get('channel_id','')
    user_id    = event.get('user_id','')
    #session_id = f"{user_id}#{channel_id}"
    session_id = f"{event['user_id']}#{event['channel_id']}"
    session = get_session(session_id)

    logger.info(f"Session start: {session}")

    # Bedrock 呼び出し
    messages = build_messages(session, prompt)
    res = bedrock.invoke_model(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        body=json.dumps({'anthropic_version':'bedrock-2023-05-31','max_tokens':512,'messages':messages}),
        contentType="application/json",
        accept="application/json"
    )
    reply = json.loads(res['body'].read())['content'][0]['text'].strip()

    if len(session['preferences']) < 2:
        # 質問フェーズ：エフェメラルで質問を返す
        post_ephemeral(channel_id, user_id, text=reply)
        if session['round'] >= 1:
            session['preferences'].append(event['prompt'])
        session['round'] += 1
        update_session(session)
    else:
        # ── 推薦フェーズ (LLM＋TMDB ハイブリッド) ────────────────────
        # 1) Claude にタイトル３本＋理由を JSON で生成してもらう
        claude_list = ask_claude_for_titles(session['preferences'])

        # 2) TMDB で詳細を補完しながらブロック生成用リストを作成
        movies = []
        for item in claude_list:
            details = get_movie_details_from_tmdb(item['title'])
            if details:
                details['reason'] = item.get('reason','')  # Claude の理由をマージ
                movies.append(details)

        # 3) Slack 用の blocks を組み立て
        blocks = [
            {'type':'section','text':{'type':'mrkdwn','text':'🎬 *おすすめ映画一覧*'}},
            {'type':'divider'}
        ]
        for m in movies:
            if m.get('poster_path'):
                blocks.append({
                    'type':'image',
                    'image_url': IMAGE_BASE + m['poster_path'],
                    'alt_text': m['title']
                })
            text = f"*{m['title']}* ({m['release_date']})\n{m['reason']}"
            blocks.append({'type':'section','text':{'type':'mrkdwn','text': text}})
            blocks.append({'type':'divider'})
        if blocks and blocks[-1]['type']=='divider':
            blocks.pop()

        post_ephemeral(channel_id, user_id, blocks=blocks)
        delete_session(session_id)

    return {'statusCode': 200}
