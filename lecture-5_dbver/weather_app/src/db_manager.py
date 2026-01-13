import sqlite3
import json
import datetime


class WeatherDB:
    """天気データベース管理クラス"""

    def __init__(self, db_name="weather_data1.db"):
        self.db_name = db_name
        self._create_tables()

    def _get_conn(self):
        """データベース接続を取得"""
        return sqlite3.connect(self.db_name, check_same_thread=False)

    def _create_tables(self):
        """テーブルを作成"""
        conn = self._get_conn()
        cursor = conn.cursor()

        # テーブル1: お気に入り地域
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS saved_areas
                       (
                           area_name
                           TEXT
                           PRIMARY
                           KEY,
                           area_code
                           TEXT,
                           created_at
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP
                       )
                       ''')

        # テーブル2: 天気履歴データ（履歴を保持）
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS weather_history
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           area_name
                           TEXT
                           NOT
                           NULL,
                           json_data
                           TEXT
                           NOT
                           NULL,
                           fetched_at
                           TIMESTAMP
                           NOT
                           NULL,
                           created_at
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP,
                           FOREIGN
                           KEY
                       (
                           area_name
                       ) REFERENCES saved_areas
                       (
                           area_name
                       )
                           )
                       ''')

        # インデックスを作成（検索を高速化）
        cursor.execute('''
                       CREATE INDEX IF NOT EXISTS idx_weather_area_time
                           ON weather_history(area_name, fetched_at DESC)
                       ''')

        conn.commit()
        conn.close()

    # --- お気に入り地域関連 ---

    def get_saved_areas(self):
        """保存されたすべての地域名を取得"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT area_name FROM saved_areas ORDER BY created_at ASC")
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]

    def add_saved_area(self, name, code=""):
        """お気に入りに追加"""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO saved_areas (area_name, area_code) VALUES (?, ?)",
                (name, code)
            )
            conn.commit()
        finally:
            conn.close()

    def remove_saved_area(self, name):
        """お気に入りから削除"""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # 関連する履歴データも削除するか選択可能
            # cursor.execute("DELETE FROM weather_history WHERE area_name = ?", (name,))
            cursor.execute("DELETE FROM saved_areas WHERE area_name = ?", (name,))
            conn.commit()
        finally:
            conn.close()

    # --- 天気データ履歴関連 ---

    def save_weather_data(self, area_name, parsed_data, fetched_at=None):
        """
        天気データを履歴として保存（上書きしない）

        Args:
            area_name: 地域名
            parsed_data: パース済みの天気データ
            fetched_at: 取得日時（Noneの場合は現在時刻）
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        if fetched_at is None:
            fetched_at = datetime.datetime.now().isoformat()

        json_str = json.dumps(parsed_data, ensure_ascii=False)

        cursor.execute('''
                       INSERT INTO weather_history (area_name, json_data, fetched_at)
                       VALUES (?, ?, ?)
                       ''', (area_name, json_str, fetched_at))

        conn.commit()
        conn.close()

    def get_latest_weather_data(self, area_name):
        """
        最新の天気データを取得

        Returns:
            (data, fetched_at) または (None, None)
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
                       SELECT json_data, fetched_at
                       FROM weather_history
                       WHERE area_name = ?
                       ORDER BY fetched_at DESC LIMIT 1
                       ''', (area_name,))
        row = cursor.fetchone()
        conn.close()

        if row:
            data = json.loads(row[0])
            timestamp = row[1]
            return data, timestamp
        return None, None

    def get_weather_history(self, area_name, limit=10):
        """
        地域の天気履歴を取得

        Args:
            area_name: 地域名
            limit: 取得する件数（デフォルト10件）

        Returns:
            [(data, fetched_at, created_at), ...] のリスト
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
                       SELECT json_data, fetched_at, created_at
                       FROM weather_history
                       WHERE area_name = ?
                       ORDER BY fetched_at DESC LIMIT ?
                       ''', (area_name, limit))
        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            data = json.loads(row[0])
            result.append((data, row[1], row[2]))
        return result

    def delete_old_weather_data(self, days=30):
        """
        古い天気データを削除

        Args:
            days: 保持する日数（デフォルト30日）
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()

        cursor.execute('''
                       DELETE
                       FROM weather_history
                       WHERE fetched_at < ?
                       ''', (cutoff_date,))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted_count

    def get_weather_data_count(self, area_name=None):
        """
        保存されている天気データの件数を取得

        Args:
            area_name: 地域名（Noneの場合は全体）

        Returns:
            件数
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        if area_name:
            cursor.execute('''
                           SELECT COUNT(*)
                           FROM weather_history
                           WHERE area_name = ?
                           ''', (area_name,))
        else:
            cursor.execute('SELECT COUNT(*) FROM weather_history')

        count = cursor.fetchone()[0]
        conn.close()
        return count

    # --- 互換性メソッド（旧コードとの互換性のため） ---

    def save_weather_cache(self, area_name, parsed_data):
        """
        旧APIとの互換性のため
        内部的にはsave_weather_dataを呼び出す
        """
        self.save_weather_data(area_name, parsed_data)

    def get_weather_cache(self, area_name):
        """
        旧APIとの互換性のため
        内部的にはget_latest_weather_dataを呼び出す
        """
        return self.get_latest_weather_data(area_name)

    # --- データベースメンテナンス ---

    def vacuum_database(self):
        """データベースを最適化"""
        conn = self._get_conn()
        conn.execute("VACUUM")
        conn.close()

    def get_database_stats(self):
        """データベースの統計情報を取得"""
        conn = self._get_conn()
        cursor = conn.cursor()

        stats = {}

        # お気に入り地域数
        cursor.execute("SELECT COUNT(*) FROM saved_areas")
        stats['saved_areas_count'] = cursor.fetchone()[0]

        # 履歴データ総数
        cursor.execute("SELECT COUNT(*) FROM weather_history")
        stats['weather_history_count'] = cursor.fetchone()[0]

        # 地域ごとのデータ数
        cursor.execute('''
                       SELECT area_name, COUNT(*) as count
                       FROM weather_history
                       GROUP BY area_name
                       ''')
        stats['data_per_area'] = dict(cursor.fetchall())

        # 最古と最新のデータ日時
        cursor.execute('''
                       SELECT MIN(fetched_at), MAX(fetched_at)
                       FROM weather_history
                       ''')
        min_date, max_date = cursor.fetchone()
        stats['oldest_data'] = min_date
        stats['newest_data'] = max_date

        conn.close()
        return stats


def generate_test_weather_data(area_name, start_date, days=7):
    """
    テスト用の天気データを生成

    Args:
        area_name: 地域名
        start_date: 開始日（datetime.date または 'YYYY-MM-DD' 形式の文字列）
        days: 生成する日数（デフォルト7日）

    Returns:
        パース済み天気データ形式のdict
    """
    import random

    # 文字列の場合はdatetime.dateに変換
    if isinstance(start_date, str):
        start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()

    # 天気コードと説明のマッピング
    weather_codes = {
        100: ("晴れ", "WB_SUNNY", "ORANGE"),
        101: ("晴れ時々曇り", "WB_SUNNY", "ORANGE"),
        200: ("曇り", "CLOUD", "GREY"),
        201: ("曇り時々晴れ", "CLOUD", "GREY"),
        300: ("雨", "WATER_DROP", "BLUE"),
        301: ("雨時々曇り", "WATER_DROP", "BLUE"),
        400: ("雪", "AC_UNIT", "CYAN"),
    }

    # サブエリア（東京の例）
    sub_areas = {
        "東京都": ["東京地方", "伊豆諸島北部", "伊豆諸島南部"],
        "大阪府": ["大阪市", "北大阪", "東部大阪"],
        "北海道": ["札幌", "函館", "旭川"],
        "沖縄県": ["那覇", "名護", "石垣島"],
    }

    # デフォルトのサブエリア
    areas = sub_areas.get(area_name, [f"{area_name}北部", f"{area_name}南部"])

    parsed_result = []

    for sub_area_name in areas:
        forecasts = []

        for day_offset in range(days):
            current_date = start_date + datetime.timedelta(days=day_offset)

            # ランダムに天気コードを選択
            code = random.choice(list(weather_codes.keys()))
            status, icon, color = weather_codes[code]

            # ランダムに気温を生成（季節を考慮）
            month = current_date.month
            if month in [12, 1, 2]:  # 冬
                min_temp = random.randint(-5, 5)
                max_temp = random.randint(min_temp + 5, min_temp + 15)
            elif month in [3, 4, 5]:  # 春
                min_temp = random.randint(5, 15)
                max_temp = random.randint(min_temp + 5, min_temp + 15)
            elif month in [6, 7, 8]:  # 夏
                min_temp = random.randint(20, 28)
                max_temp = random.randint(min_temp + 5, min_temp + 12)
            else:  # 秋
                min_temp = random.randint(10, 20)
                max_temp = random.randint(min_temp + 5, min_temp + 15)

            forecasts.append({
                "day": f"{current_date.month}/{current_date.day}",
                "icon": icon,
                "status": status,
                "temp": f"{min_temp}-{max_temp}°C",
                "color": color
            })

        parsed_result.append({
            "area_name": sub_area_name,
            "forecasts": forecasts
        })

    return parsed_result


def test_weather_db():
    """データベースのテスト"""
    print("=" * 60)
    print("天気データベーステスト開始")
    print("=" * 60)

    # テスト用DBを作成
    db = WeatherDB("test_weather.db")

    # テスト1: 地域の追加
    print("\n[テスト1] 地域の追加")
    test_areas = [
        ("東京都", "130000"),
        ("大阪府", "270000"),
        ("北海道", "016000"),
    ]

    for name, code in test_areas:
        db.add_saved_area(name, code)
        print(f"✓ {name} を追加")

    saved = db.get_saved_areas()
    print(f"保存された地域: {saved}")

    # テスト2: 複数日付で天気データを生成・保存
    print("\n[テスト2] 天気データの生成と保存")

    base_date = datetime.date(2025, 1, 1)

    for name, _ in test_areas:
        # 異なる日付で3回保存
        for day_offset in [0, 7, 14]:
            fetch_date = base_date + datetime.timedelta(days=day_offset)
            weather_data = generate_test_weather_data(name, fetch_date, days=7)

            db.save_weather_data(
                name,
                weather_data,
                fetched_at=fetch_date.isoformat()
            )
            print(f"✓ {name} の天気データを保存 (取得日: {fetch_date})")

    # テスト3: 最新データの取得
    print("\n[テスト3] 最新データの取得")
    for name, _ in test_areas:
        data, timestamp = db.get_latest_weather_data(name)
        if data:
            print(f"\n{name} の最新データ:")
            print(f"  取得日時: {timestamp}")
            print(f"  サブエリア数: {len(data)}")
            if data:
                first_forecast = data[0]['forecasts'][0]
                print(f"  最初の予報: {first_forecast['day']} - {first_forecast['status']} ({first_forecast['temp']})")

    # テスト4: 履歴データの取得
    print("\n[テスト4] 履歴データの取得")
    for name, _ in test_areas:
        history = db.get_weather_history(name, limit=5)
        print(f"\n{name} の履歴 ({len(history)}件):")
        for i, (data, fetched_at, created_at) in enumerate(history, 1):
            print(f"  {i}. 取得日: {fetched_at}, 保存日時: {created_at}")

    # テスト5: データ件数の確認
    print("\n[テスト5] データ件数")
    for name, _ in test_areas:
        count = db.get_weather_data_count(name)
        print(f"{name}: {count}件")

    total_count = db.get_weather_data_count()
    print(f"全体: {total_count}件")

    # テスト6: 統計情報
    print("\n[テスト6] データベース統計")
    stats = db.get_database_stats()
    print(f"お気に入り地域数: {stats['saved_areas_count']}")
    print(f"履歴データ総数: {stats['weather_history_count']}")
    print(f"最古のデータ: {stats['oldest_data']}")
    print(f"最新のデータ: {stats['newest_data']}")
    print(f"地域ごとのデータ数: {stats['data_per_area']}")

    # テスト7: 古いデータの削除
    print("\n[テスト7] 古いデータの削除テスト")
    print("(このテストはスキップ - 実際のデータが少ないため)")
    # deleted = db.delete_old_weather_data(days=10)
    # print(f"削除されたレコード数: {deleted}")

    print("\n" + "=" * 60)
    print("テスト完了!")
    print("=" * 60)
    print(f"\nテストデータベース: test_weather.db")
    print("確認後、test_weather.db を削除できます")


if __name__ == "__main__":
    # テスト実行
    test_weather_db()

    print("\n\n[カスタムテストの例]")
    print("-" * 60)

    # カスタム: 特定の日付と地域でテストデータを生成
    custom_area = "福岡県"
    custom_date = "2025-02-15"
    custom_days = 10

    print(f"地域: {custom_area}")
    print(f"開始日: {custom_date}")
    print(f"日数: {custom_days}日間")
    print()

    weather_data = generate_test_weather_data(custom_area, custom_date, custom_days)

    for sub_area in weather_data:
        print(f"\n[{sub_area['area_name']}]")
        for forecast in sub_area['forecasts']:
            print(f"  {forecast['day']}: {forecast['status']:10s} {forecast['temp']:12s}")

    # カスタムデータをDBに保存する例
    print("\n\nカスタムデータをDBに保存:")
    db = WeatherDB("test_weather.db")
    db.add_saved_area(custom_area, "999999")  # ダミーコード
    db.save_weather_data(custom_area, weather_data, fetched_at=custom_date)
    print(f"✓ {custom_area} のデータを保存しました")