# 6人用 月次シフト自動生成サイト

Flask + Google OR-Tools CP-SAT で、指定条件を**すべてハード制約**として扱うシフト生成サイトです。
1つでも満たせない場合は、条件を緩めたシフトを出さず「可能な組み合わせがありません」と返します。

## 条件

- メンバーは6人固定（名前入力）
- 年月を入力し、曜日を自動表示
- 店休日は勤務者0人
- 営業日は1日2人
- A担当を `◎`、B担当を `◯` で表示
- 6人の総勤務日数差は1以内
- 連勤禁止
- 2回の勤務の間に5日以上の完全な休みが入ることを禁止
- 各人のA/B勤務回数差は1以内
- 同じ曜日の勤務は1人3回まで
- 同じポジション4勤務連続は禁止
- 休み希望は1人5日まで、その日は勤務不可
- ポジション込みの同一ペア `A担当者 → B担当者` は月内1回まで
  - `X=A, Y=B` と `X=B, Y=A` は別扱い
- **ポジションを無視した同じ2人の組み合わせは、再登場まで日付差10日以上**
  - 例：1日にX/Yが勤務した場合、2〜10日はX/Yの再ペア禁止
  - 11日以降は再度組める（ただし同じA/Bの向きは月内1回制約に従う）
- 土日勤務数の全員差は1以内
- 1つでも条件違反があればシフトを表示しない

## ローカル起動

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

ローカルでは `http://127.0.0.1:5050/` を開きます。

## Renderに公開する手順

### 1. GitHubにアップロード

このフォルダの中身をGitHubリポジトリに置きます。

```bash
git init
git add .
git commit -m "Initial shift generator"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
git push -u origin main
```

GitHubのWeb画面からファイルをアップロードしても構いません。

### 2. RenderでWeb Serviceを作る

1. Renderにログイン
2. `New` → `Web Service`
3. GitHubリポジトリを接続
4. `render.yaml` を使う場合は Blueprint として作成してもよい
5. 手動設定する場合は以下

- Runtime: Python
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT app:app`

デプロイ完了後、Renderから `https://...onrender.com` の公開URLが発行されます。

## Render用ファイル

- `render.yaml`: Render Blueprint設定
- `.python-version`: Python 3.12系を指定
- `requirements.txt`: Flask / OR-Tools / Gunicorn

## 注意

無料Web Serviceは一定時間アクセスがないと停止し、次回アクセス時に再起動することがあります。
また、OR-Toolsの探索は最大30秒に設定されています。すべての条件を満たす解を確認できない場合、シフトは表示しません。
