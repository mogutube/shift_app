from __future__ import annotations

import calendar
from datetime import date
from flask import Flask, render_template, request, jsonify
from ortools.sat.python import cp_model

app = Flask(__name__)

JP_WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


def month_days(year: int, month: int):
    last = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, last + 1)]


def solve_shift(year: int, month: int, names: list[str], closed_days: set[int], requests: list[set[int]]):
    dates = month_days(year, month)
    n_days = len(dates)
    people = range(6)
    days = range(1, n_days + 1)
    open_days = [d for d in days if d not in closed_days]

    # ポジション込みの勤務ペアは「A担当者 → B担当者」の順序付きペアとして扱う。
    # 6人なら A を6通り、その人以外の B を5通り選べるため 6*5=30 通り。
    if len(open_days) > 30:
        return None, (
            f"営業日が{len(open_days)}日ありますが、6人で作れるポジション込みの勤務ペアは30通りしかありません。"
            "『同じ A担当者・B担当者 の組み合わせは月内で1回だけ』を守る場合、営業日は最大30日です。"
        )

    # 各人の休み希望は最大5日。
    for i, req in enumerate(requests):
        if len(req) > 5:
            return None, f"{names[i]}さんの休み希望が{len(req)}日あります。1人5日までです。"

    model = cp_model.CpModel()

    # work[p,d], A[p,d], B[p,d]
    work = {}
    pos_a = {}
    pos_b = {}
    for p in people:
        for d in days:
            work[p, d] = model.NewBoolVar(f"work_{p}_{d}")
            pos_a[p, d] = model.NewBoolVar(f"A_{p}_{d}")
            pos_b[p, d] = model.NewBoolVar(f"B_{p}_{d}")
            model.Add(work[p, d] == pos_a[p, d] + pos_b[p, d])

            if d in closed_days or d in requests[p]:
                model.Add(work[p, d] == 0)

    # 営業日は必ず2人、AとBが各1人。休業日は0人。
    for d in days:
        if d in closed_days:
            model.Add(sum(work[p, d] for p in people) == 0)
            model.Add(sum(pos_a[p, d] for p in people) == 0)
            model.Add(sum(pos_b[p, d] for p in people) == 0)
        else:
            model.Add(sum(work[p, d] for p in people) == 2)
            model.Add(sum(pos_a[p, d] for p in people) == 1)
            model.Add(sum(pos_b[p, d] for p in people) == 1)

    # 勤務日数の差を1以内にする。
    total_slots = 2 * len(open_days)
    min_work = total_slots // 6
    max_work = (total_slots + 5) // 6
    totals = []
    for p in people:
        t = model.NewIntVar(0, n_days, f"total_{p}")
        model.Add(t == sum(work[p, d] for d in days))
        model.Add(t >= min_work)
        model.Add(t <= max_work)
        totals.append(t)

    # 連勤禁止（カレンダー上で隣り合う日）。
    for p in people:
        for d in range(1, n_days):
            model.Add(work[p, d] + work[p, d + 1] <= 1)

    # 「中5日以上空く」を禁止。
    # 初回勤務前と最終勤務後は制限せず、勤務と次勤務の間だけ
    # 5日以上の完全な空白が生じないようにする。
    # 状態: 0=まだ勤務なし, 1=直前が勤務, 2..5=勤務後1..4日休み, 6=5日以上休み(以後勤務不可)
    gap_transitions = [
        (0, 0, 0), (0, 1, 1),
        (1, 1, 1), (1, 0, 2),
        (2, 1, 1), (2, 0, 3),
        (3, 1, 1), (3, 0, 4),
        (4, 1, 1), (4, 0, 5),
        (5, 1, 1), (5, 0, 6),
        (6, 0, 6),
    ]
    for p in people:
        model.AddAutomaton(
            [work[p, d] for d in days],
            0,
            [0, 1, 2, 3, 4, 5, 6],
            gap_transitions,
        )

    # 各曜日の勤務は1人3回まで。
    for p in people:
        for weekday in range(7):
            weekday_days = [d.day for d in dates if d.weekday() == weekday]
            model.Add(sum(work[p, d] for d in weekday_days) <= 3)

    # A/B回数の差は1以内。
    for p in people:
        a_total = sum(pos_a[p, d] for d in days)
        b_total = sum(pos_b[p, d] for d in days)
        model.Add(a_total - b_total <= 1)
        model.Add(b_total - a_total <= 1)

    # 同じポジションが「その人の勤務回ベース」で4回連続しない。
    # symbol: 0=休み, 1=A, 2=B。休みの日は連続回数をリセットしない。
    # states: 0=未勤務, 1=A1,2=A2,3=A3,4=B1,5=B2,6=B3
    pos_transitions = [
        (0, 0, 0), (0, 1, 1), (0, 2, 4),
        (1, 0, 1), (1, 1, 2), (1, 2, 4),
        (2, 0, 2), (2, 1, 3), (2, 2, 4),
        (3, 0, 3), (3, 2, 4),
        (4, 0, 4), (4, 2, 5), (4, 1, 1),
        (5, 0, 5), (5, 2, 6), (5, 1, 1),
        (6, 0, 6), (6, 1, 1),
    ]
    for p in people:
        symbols = []
        for d in days:
            s = model.NewIntVar(0, 2, f"symbol_{p}_{d}")
            model.Add(s == pos_a[p, d] + 2 * pos_b[p, d])
            symbols.append(s)
        model.AddAutomaton(symbols, 0, [0, 1, 2, 3, 4, 5, 6], pos_transitions)

    # ポジション込みで同じ勤務ペアは月内1回のみ。
    # 例: X=A, Y=B と X=B, Y=A は別ペア。
    # ordered_pair[p,q,d] = 1 <=> p が A、q が B。p != q。
    ordered_pairs = {}
    for p in people:
        for q in people:
            if p == q:
                continue
            pair_occurrences = []
            for d in open_days:
                ordered_pair = model.NewBoolVar(f"ordered_pair_A{p}_B{q}_{d}")
                model.Add(ordered_pair <= pos_a[p, d])
                model.Add(ordered_pair <= pos_b[q, d])
                model.Add(ordered_pair >= pos_a[p, d] + pos_b[q, d] - 1)
                ordered_pairs[p, q, d] = ordered_pair
                pair_occurrences.append(ordered_pair)
            model.Add(sum(pair_occurrences) <= 1)

    # 同じ2人の組み合わせ（ポジションは無視）は、再登場まで日付差を10日以上空ける。
    # 例: 1日に X=A,Y=B で勤務した場合、2〜10日には X/Y の組み合わせは不可。
    # 11日以降なら X=B,Y=A のようにポジションを入れ替えて再度組むことができる。
    # なお、同じ向き X=A,Y=B は上の制約により月内1回のみ。
    for p in people:
        for q in people:
            if p >= q:
                continue
            for i, d1 in enumerate(open_days):
                for d2 in open_days[i + 1:]:
                    if d2 - d1 < 10:
                        # unordered pair {p,q} が両日で同時に勤務することを禁止。
                        model.Add(
                            ordered_pairs[p, q, d1]
                            + ordered_pairs[q, p, d1]
                            + ordered_pairs[p, q, d2]
                            + ordered_pairs[q, p, d2]
                            <= 1
                        )

    # 土日の勤務数も全員差1以内。
    weekend_days = [d.day for d in dates if d.weekday() in (5, 6) and d.day not in closed_days]
    weekend_slots = 2 * len(weekend_days)
    min_weekend = weekend_slots // 6
    max_weekend = (weekend_slots + 5) // 6
    weekend_totals = []
    for p in people:
        wt = model.NewIntVar(0, len(weekend_days), f"weekend_{p}")
        model.Add(wt == sum(work[p, d] for d in weekend_days))
        model.Add(wt >= min_weekend)
        model.Add(wt <= max_weekend)
        weekend_totals.append(wt)

    # 完全な公平条件内で、勤務日の偏りを少しだけ抑える補助目的。
    # 早い日・遅い日の偏りが極端になりにくいよう、勤務日の重心差を最小化。
    day_sums = []
    for p in people:
        ds = model.NewIntVar(0, n_days * n_days, f"day_sum_{p}")
        model.Add(ds == sum(d * work[p, d] for d in days))
        day_sums.append(ds)
    max_ds = model.NewIntVar(0, n_days * n_days, "max_ds")
    min_ds = model.NewIntVar(0, n_days * n_days, "min_ds")
    model.AddMaxEquality(max_ds, day_sums)
    model.AddMinEquality(min_ds, day_sums)
    model.Minimize(max_ds - min_ds)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 42

    status = solver.Solve(model)
    if status == cp_model.INFEASIBLE:
        return None, (
            "可能な組み合わせがありませんでした。シフトは生成していません。"
            "指定された条件のうち1つでも破るシフトは表示しません。"
        )
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, (
            "条件をすべて満たす組み合わせを確認できなかったため、シフトは生成していません。"
            "指定された条件を破るシフトは表示しません。"
        )

    # 念のため、ソルバーが返した解をアプリ側でも再検証する。
    # 1つでも条件違反が見つかった場合は結果を返さない。
    violations = []

    # 営業日/店休日、A/B人数
    for d in days:
        wc = sum(solver.Value(work[p, d]) for p in people)
        ac = sum(solver.Value(pos_a[p, d]) for p in people)
        bc = sum(solver.Value(pos_b[p, d]) for p in people)
        expected = 0 if d in closed_days else 2
        if wc != expected or ac != (0 if d in closed_days else 1) or bc != (0 if d in closed_days else 1):
            violations.append(f"{d}日の勤務人数/ポジション人数")

    # 個人ごとの勤務日数、休み希望、連勤、勤務間隔、曜日、A/B、同一ポジション連続
    solved_totals = []
    solved_weekends = []
    for p in people:
        work_days = [d for d in days if solver.Value(work[p, d])]
        solved_totals.append(len(work_days))
        solved_weekends.append(sum(1 for d in weekend_days if solver.Value(work[p, d])))

        if any(d in requests[p] for d in work_days):
            violations.append(f"{names[p]}さんの休み希望")

        if any(b - a == 1 for a, b in zip(work_days, work_days[1:])):
            violations.append(f"{names[p]}さんの連勤")

        if any(b - a - 1 >= 5 for a, b in zip(work_days, work_days[1:])):
            violations.append(f"{names[p]}さんの勤務間隔")

        for weekday in range(7):
            count = sum(1 for d in work_days if dates[d - 1].weekday() == weekday)
            if count > 3:
                violations.append(f"{names[p]}さんの同一曜日勤務")

        a_count = sum(solver.Value(pos_a[p, d]) for d in days)
        b_count = sum(solver.Value(pos_b[p, d]) for d in days)
        if abs(a_count - b_count) > 1:
            violations.append(f"{names[p]}さんのA/B回数")

        position_sequence = []
        for d in work_days:
            position_sequence.append("A" if solver.Value(pos_a[p, d]) else "B")
        streak = 0
        prev = None
        for position in position_sequence:
            streak = streak + 1 if position == prev else 1
            prev = position
            if streak >= 4:
                violations.append(f"{names[p]}さんの同一ポジション4回連続")
                break

    if solved_totals and max(solved_totals) - min(solved_totals) > 1:
        violations.append("全員の勤務日数差")
    if solved_weekends and max(solved_weekends) - min(solved_weekends) > 1:
        violations.append("全員の土日勤務日数差")

    # 順序付きペア (A担当者, B担当者) の重複
    seen_pairs = set()
    # ポジションを無視した2人組について、前回から10日未満での再登場も禁止。
    last_unordered_pair_day = {}
    for d in open_days:
        a_person = next(p for p in people if solver.Value(pos_a[p, d]))
        b_person = next(p for p in people if solver.Value(pos_b[p, d]))
        pair = (a_person, b_person)
        if pair in seen_pairs:
            violations.append("ポジション込み勤務ペアの重複")
            break
        seen_pairs.add(pair)

        unordered_pair = tuple(sorted((a_person, b_person)))
        if unordered_pair in last_unordered_pair_day:
            if d - last_unordered_pair_day[unordered_pair] < 10:
                violations.append("同じ2人の組み合わせの勤務間隔が10日未満")
                break
        last_unordered_pair_day[unordered_pair] = d

    if violations:
        return None, (
            "条件チェックで違反が検出されたため、シフトは生成していません。"
            "指定された条件を1つでも満たさないシフトは表示しません。"
        )

    rows = []
    member_stats = []
    for dt in dates:
        d = dt.day
        assignments = []
        if d not in closed_days:
            for p in people:
                if solver.Value(pos_a[p, d]):
                    assignments.append({"name": names[p], "mark": "◎", "position": "A"})
                elif solver.Value(pos_b[p, d]):
                    assignments.append({"name": names[p], "mark": "◯", "position": "B"})
        rows.append({
            "day": d,
            "weekday": JP_WEEKDAYS[dt.weekday()],
            "closed": d in closed_days,
            "assignments": assignments,
        })

    for p in people:
        a_count = sum(solver.Value(pos_a[p, d]) for d in days)
        b_count = sum(solver.Value(pos_b[p, d]) for d in days)
        weekday_counts = {
            JP_WEEKDAYS[w]: sum(solver.Value(work[p, dt.day]) for dt in dates if dt.weekday() == w)
            for w in range(7)
        }
        member_stats.append({
            "name": names[p],
            "total": a_count + b_count,
            "A": a_count,
            "B": b_count,
            "weekend": sum(solver.Value(work[p, d]) for d in weekend_days),
            "weekday_counts": weekday_counts,
        })

    return {
        "year": year,
        "month": month,
        "rows": rows,
        "member_stats": member_stats,
        "open_days": len(open_days),
    }, None


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/generate")
def generate():
    data = request.get_json(force=True)
    try:
        year = int(data["year"])
        month = int(data["month"])
        names = [str(x).strip() for x in data["names"]]
        if len(names) != 6 or any(not n for n in names):
            return jsonify({"ok": False, "error": "6人全員の名前を入力してください。"}), 400
        if len(set(names)) != 6:
            return jsonify({"ok": False, "error": "メンバー名は6人すべて異なる名前にしてください。"}), 400

        n_days = calendar.monthrange(year, month)[1]
        closed_days = {int(d) for d in data.get("closed_days", [])}
        if any(d < 1 or d > n_days for d in closed_days):
            return jsonify({"ok": False, "error": "休業日に対象月以外の日付が含まれています。"}), 400

        raw_requests = data.get("requests", [])
        if len(raw_requests) != 6:
            raw_requests = [[] for _ in range(6)]
        requests = []
        for req in raw_requests:
            s = {int(d) for d in req}
            if any(d < 1 or d > n_days for d in s):
                return jsonify({"ok": False, "error": "休み希望に対象月以外の日付が含まれています。"}), 400
            requests.append(s)

        result, error = solve_shift(year, month, names, closed_days, requests)
        if error:
            return jsonify({"ok": False, "error": error}), 200
        return jsonify({"ok": True, "result": result})
    except (KeyError, ValueError, TypeError):
        return jsonify({"ok": False, "error": "入力内容を確認してください。"}), 400


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5050)
