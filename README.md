# Shift Generator

6人用の月次シフト自動生成Webアプリです。

## 主な制約
- 1日2人、A=◎ / B=◯
- 店休日は勤務なし
- 勤務日数差は1以内
- 連勤禁止
- 勤務間で中5日以上空くのは禁止
- A/B回数差は1以内
- 同一曜日勤務は1人3回まで
- 同じポジション4回連続禁止
- 休み希望は1人5日まで
- 同じ順序付きペア(A担当,B担当)は月内1回
- 同じ2人組はポジションを無視して10日以上空ける
- 土日祝日の勤務数は全員差1以内
- 1条件でも満たせなければシフト非生成

## Render
Build Command:
pip install -r requirements.txt

Start Command:
gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT app:app
