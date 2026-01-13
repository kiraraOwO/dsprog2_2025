# flet version need to be 0.28.3, search bar cannot work on >= 0.80.0
# fletバージョンは0.28.3が必要です。0.80.0以降ではSearchBarが動作しません。
import flet as ft
import requests
import datetime
import json
import os
from db_manager import WeatherDB


class DataManager:
    """データ管理クラス: 地域データと天気データの取得・管理"""

    def __init__(self):
        self.db = WeatherDB()
        self.area_name_list = []
        self.name_to_id = {}
        self.weather_data = {}
        self._load_area_data()

    def _load_area_data(self):
        """地域データの読み込み: ローカルキャッシュ → ネットワーク → フォールバック"""
        cache_file = "area.json"
        url = "https://www.jma.go.jp/bosai/common/const/area.json"
        full_data = None

        # ローカルキャッシュを試す
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    full_data = json.load(f)
                print("ローカルキャッシュ読み込み成功")
            except Exception as e:
                print(f"ローカルキャッシュ読み込み失敗: {e}")

        # ネットワークから取得
        if full_data is None:
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                full_data = response.json()

                # ローカルに保存
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(full_data, f, ensure_ascii=False, indent=2)
                print("地域データダウンロード成功")
            except Exception as e:
                print(f"ネットワーク取得失敗: {e}")

        # フォールバックデータ
        if full_data is None:
            print("フォールバックデータ使用")
            full_data = {
                "offices": {
                    "130000": {"name": "東京都"},
                    "270000": {"name": "大阪府"},
                    "016000": {"name": "札幌"},
                    "471000": {"name": "沖縄"}
                }
            }

        # データ処理
        try:
            offices = full_data.get("offices", {})
            self.area_name_list = []
            self.name_to_id = {}

            for code, info in offices.items():
                name = info["name"]
                self.area_name_list.append(name)
                self.name_to_id[name] = code

            print(f"地域データ準備完了: {len(self.area_name_list)}件")
        except Exception as e:
            print(f"データ処理エラー: {e}")
            self.area_name_list = ["東京都"]
            self.name_to_id = {"東京都": "130000"}

    def fetch_weather_data(self, region_id, region_name):
        """天気データの取得: ネットワーク → キャッシュ"""
        url = f"https://www.jma.go.jp/bosai/forecast/data/forecast/{region_id}.json"

        try:
            # ネットワークから取得
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            raw_json = r.json()
            parsed_data = self._parse_jma_data(raw_json)

            if parsed_data:
                self.weather_data[region_name] = parsed_data
                self.db.save_weather_cache(region_name, parsed_data)
                return True, "online"
        except Exception as e:
            print(f"ネットワーク失敗 ({e}), キャッシュ確認中...")

            # キャッシュから取得
            cached_data, timestamp = self.db.get_weather_cache(region_name)
            if cached_data:
                print(f"{region_name}のキャッシュ使用: {timestamp}")
                self.weather_data[region_name] = cached_data
                return True, timestamp

            return False, None

        return False, None

    def _parse_jma_data(self, raw_json):
        """気象庁JSONデータのパース"""
        try:
            report_short = raw_json[0]
            report_weekly = raw_json[1] if len(raw_json) > 1 else raw_json[0]

            # 短期気温データの抽出
            short_term_temps_map = []
            for series in report_short["timeSeries"]:
                if series.get("areas") and "temps" in series["areas"][0]:
                    for area in series["areas"]:
                        short_term_temps_map.append(area["temps"])
                    break

            # 週間天気・気温データの抽出
            ts_weather = None
            ts_temp = None
            for series in report_weekly["timeSeries"]:
                if not series.get("areas"):
                    continue
                keys = series["areas"][0].keys()
                if "weatherCodes" in keys:
                    ts_weather = series
                elif "temps" in keys or "tempsMin" in keys:
                    ts_temp = series

            if not ts_weather:
                return []

            # 気温データの整理
            weekly_temp_data = []
            if ts_temp:
                for area in ts_temp["areas"]:
                    if "tempsMin" in area:
                        weekly_temp_data.append({
                            "type": "weekly",
                            "mins": area["tempsMin"],
                            "maxs": area["tempsMax"]
                        })
                    else:
                        weekly_temp_data.append({
                            "type": "daily",
                            "temps": area["temps"]
                        })

            # 日付のフォーマット
            time_defines = ts_weather["timeDefines"]
            formatted_dates = []
            for t in time_defines:
                dt = datetime.datetime.fromisoformat(t)
                formatted_dates.append(f"{dt.month}/{dt.day}")

            # 結果の構築
            parsed_result = []
            for i_area, area_data in enumerate(ts_weather["areas"]):
                sub_area_name = area_data["area"]["name"]
                weather_codes = area_data["weatherCodes"]

                current_weekly_temps = weekly_temp_data[i_area] if i_area < len(weekly_temp_data) else None
                current_short_temps = short_term_temps_map[i_area] if i_area < len(short_term_temps_map) else []

                forecasts = []
                for i_time in range(len(time_defines)):
                    if i_time >= len(weather_codes):
                        break

                    code = weather_codes[i_time]
                    icon, color = self._get_weather_icon_and_color(code)
                    status_text = self._get_weather_status_text(code)
                    display_temp = self._format_temperature(
                        current_weekly_temps, current_short_temps, i_time
                    )

                    forecasts.append({
                        "day": formatted_dates[i_time],
                        "icon": icon,
                        "status": status_text,
                        "temp": display_temp,
                        "color": color
                    })

                parsed_result.append({
                    "area_name": sub_area_name,
                    "forecasts": forecasts
                })

            return parsed_result

        except Exception as e:
            print(f"パース失敗: {e}")
            return []

    def _get_weather_icon_and_color(self, code):
        """天気コードからアイコンと色を取得"""
        c = int(code)
        if 100 <= c < 200:
            return ft.Icons.WB_SUNNY, ft.Colors.ORANGE
        elif 200 <= c < 300:
            return ft.Icons.CLOUD, ft.Colors.GREY
        elif 300 <= c < 400:
            return ft.Icons.WATER_DROP, ft.Colors.BLUE
        elif 400 <= c < 500:
            return ft.Icons.AC_UNIT, ft.Colors.CYAN
        else:
            return ft.Icons.HELP_OUTLINE, ft.Colors.GREY

    def _get_weather_status_text(self, code):
        """天気コードからステータステキストを取得"""
        try:
            c = int(code)
            if 100 <= c < 200:
                return "晴れ"
            elif 200 <= c < 300:
                return "くもり"
            elif 300 <= c < 400:
                return "雨"
            elif 400 <= c < 500:
                return "雪"
            else:
                return "-"
        except:
            return "-"

    def _format_temperature(self, weekly_temps, short_temps, time_index):
        """気温データのフォーマット"""
        display_temp = "--"

        if weekly_temps:
            if weekly_temps["type"] == "weekly":
                min_v = weekly_temps["mins"][time_index]
                max_v = weekly_temps["maxs"][time_index]

                if (min_v == "" or max_v == "") and time_index == 0:
                    # 当日の気温は短期データから
                    if short_temps:
                        if len(short_temps) >= 2:
                            display_temp = f"{short_temps[0]}-{short_temps[1]}°C"
                        elif len(short_temps) == 1:
                            display_temp = f"{short_temps[0]}°C"
                else:
                    if min_v and max_v:
                        display_temp = f"{min_v}-{max_v}°C"
                    elif max_v or min_v:
                        display_temp = f"{max_v if max_v else min_v}°C"

            elif weekly_temps["type"] == "daily":
                val = weekly_temps["temps"][time_index]
                if val:
                    display_temp = f"{val}°C"

        return display_temp

    def get_forecast_data(self, region_name):
        """予報データの取得"""
        return self.weather_data.get(region_name, [])


class WeatherApp:
    """メインアプリケーションクラス"""

    def __init__(self, page: ft.Page):
        self.page = page
        self.data_manager = DataManager()

        # 保存された地域リストの読み込み
        saved_from_db = self.data_manager.db.get_saved_areas()
        if saved_from_db:
            self.current_saved_regions = saved_from_db
        else:
            self.current_saved_regions = ["東京都"]
            self.data_manager.db.add_saved_area("東京都", "130000")

        self._setup_page()
        self._init_controls()
        self.render_saved_list()

        # 最初の地域を表示
        first_city = self.current_saved_regions[0] if self.current_saved_regions else "東京都"
        self.update_weather_display(first_city)

    def _setup_page(self):
        """ページ設定"""
        self.page.title = "日本天気予報(Japan Weather Forecast)"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.window_width = 900
        self.page.window_height = 600
        self.page.padding = 0

    def _init_controls(self):
        """UIコントロールの初期化"""
        # 検索バー
        self.search_bar = ft.SearchBar(
            view_hint_text="エリアを入れてください(Type area name)",
            bar_hint_text="検索(Search)...",
            bar_bgcolor=ft.Colors.WHITE,
            view_bgcolor=ft.Colors.WHITE,
            bar_leading=ft.Icon(ft.Icons.SEARCH, color=ft.Colors.GREY),
            on_tap=self.handle_search_tap,
            on_change=self.handle_search_change,
            controls=[]
        )

        # 保存リスト
        self.saved_list_col = ft.Column(spacing=2)

        # 地域名表示
        self.current_region_text = ft.Text(
            value="Area Name",
            size=30,
            weight=ft.FontWeight.BOLD
        )

        # 日付フィルタードロップダウン
        self.date_filter_dd = ft.Dropdown(
            width=120,
            options=[],
            hint_text="Date",
            text_size=14,
            content_padding=10,
            on_change=self.handle_date_filter_change,
            disabled=True
        )

        # 天気リスト表示エリア
        self.weather_list_view = ft.ListView(
            expand=True,
            spacing=0,
            padding=20
        )

        # レイアウト構築
        self.sidebar = self._build_sidebar()
        self.content_area = self._build_content_area()
        self.page.add(ft.Row(controls=[self.sidebar, self.content_area], expand=True, spacing=0))

    def _build_sidebar(self):
        """サイドバーの構築"""
        return ft.Container(
            width=250,
            bgcolor=ft.Colors.BLUE_GREY_50,
            padding=10,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    # ヘッダー
                    ft.Container(
                        padding=ft.padding.only(bottom=10, top=10),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Icon(name=ft.Icons.WB_SUNNY, color=ft.Colors.ORANGE, size=24),
                                ft.Text("日本天気", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                                ft.Icon(name=ft.Icons.CLOUD, color=ft.Colors.BLUE_GREY, size=24),
                            ]
                        )
                    ),
                    self.search_bar,
                    ft.Divider(),
                    ft.Container(
                        alignment=ft.alignment.center_left,
                        content=ft.Text("お気に入り(Stars)", size=12, color=ft.Colors.GREY)
                    ),
                    self.saved_list_col
                ],
                spacing=10
            )
        )

    def _build_content_area(self):
        """コンテンツエリアの構築"""
        return ft.Container(
            expand=True,
            padding=0,
            bgcolor=ft.Colors.WHITE,
            content=ft.Column(
                controls=[
                    ft.Container(height=30),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self.current_region_text,
                            ft.Container(width=10),
                            self.date_filter_dd
                        ]
                    ),
                    ft.Divider(),
                    self.weather_list_view,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0
            )
        )

    def handle_search_change(self, e):
        """検索バー変更イベント"""
        keyword = e.data

        if not keyword:
            self._show_all_regions()
        else:
            matches = [name for name in self.data_manager.area_name_list if keyword in name]
            new_controls = [
                ft.ListTile(
                    title=ft.Text(name),
                    leading=ft.Icon(ft.Icons.LOCATION_CITY),
                    on_click=lambda e, n=name: self.close_search_and_add(n)
                )
                for name in matches
            ]
            self.search_bar.controls = new_controls
            self.search_bar.update()
            self.search_bar.open_view()

    def handle_search_tap(self, e):
        """検索バータップイベント"""
        if not self.search_bar.value:
            self._show_all_regions()
        self.search_bar.open_view()

    def _show_all_regions(self):
        """全地域を表示"""
        if not self.data_manager.area_name_list:
            self.search_bar.controls = [ft.ListTile(title=ft.Text("Loading area data..."))]
        else:
            self.search_bar.controls = [
                ft.ListTile(
                    title=ft.Text(name),
                    leading=ft.Icon(ft.Icons.LOCATION_CITY),
                    on_click=lambda e, n=name: self.close_search_and_add(n)
                )
                for name in self.data_manager.area_name_list
            ]
        self.search_bar.update()

    def close_search_and_add(self, region_name):
        """検索を閉じて地域を追加"""
        self.search_bar.close_view(region_name)
        self.add_region(region_name)

    def add_region(self, region_name):
        """地域を追加"""
        if not region_name or region_name in self.current_saved_regions:
            if region_name:
                self.update_weather_display(region_name)
            return

        code = self.data_manager.name_to_id.get(region_name, "")
        self.data_manager.db.add_saved_area(region_name, code)
        self.current_saved_regions.append(region_name)
        self.render_saved_list()
        self.update_weather_display(region_name)

    def remove_region(self, region_name):
        """地域を削除"""
        if region_name in self.current_saved_regions:
            self.data_manager.db.remove_saved_area(region_name)
            self.current_saved_regions.remove(region_name)
            self.render_saved_list()

            if self.current_region_text.value == region_name:
                self.current_region_text.value = "Choose one area"
                self.weather_list_view.controls.clear()
                self.page.update()

    def render_saved_list(self):
        """保存リストのレンダリング"""
        self.saved_list_col.controls.clear()
        for region in self.current_saved_regions:
            self.saved_list_col.controls.append(
                self._create_list_item(region)
            )
        self.page.update()

    def _create_list_item(self, text):
        """リストアイテムの作成"""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Text(text, size=16),
                        expand=True,
                        on_click=lambda e, r=text: self.update_weather_display(r),
                        padding=10,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=ft.Colors.RED_300,
                        icon_size=20,
                        on_click=lambda e, r=text: self.remove_region(r)
                    )
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            width=float("inf"),
            border_radius=5,
            bgcolor=ft.Colors.TRANSPARENT,
            on_hover=lambda e: (
                    setattr(e.control, 'bgcolor', ft.Colors.WHITE if e.data == "true" else ft.Colors.TRANSPARENT)
                    or e.control.update()
            ),
        )

    def handle_date_filter_change(self, e):
        """日付フィルター変更イベント"""
        region_name = self.current_region_text.value
        self.render_weather_view(region_name)

    def update_weather_display(self, region_name):
        """天気表示の更新"""
        self.current_region_text.value = region_name

        # データ取得
        if region_name not in self.data_manager.weather_data:
            region_id = self.data_manager.name_to_id.get(region_name)
            if region_id:
                success, _ = self.data_manager.fetch_weather_data(region_id, region_name)
                if not success:
                    self._show_error_screen(region_name)
                    self.date_filter_dd.disabled = True
                    self.date_filter_dd.update()
                    return

        sub_areas_data = self.data_manager.get_forecast_data(region_name)
        if not sub_areas_data:
            self.date_filter_dd.disabled = True
            self.date_filter_dd.update()
            return

        # ドロップダウンの更新
        self._update_date_dropdown(sub_areas_data)

        # ビューのレンダリング
        self.render_weather_view(region_name)

    def _update_date_dropdown(self, sub_areas_data):
        """日付ドロップダウンの更新"""
        try:
            first_area_forecasts = sub_areas_data[0]["forecasts"]
            unique_dates = []
            seen = set()
            for f in first_area_forecasts:
                if f["day"] not in seen:
                    unique_dates.append(f["day"])
                    seen.add(f["day"])

            dd_options = [ft.dropdown.Option("All", "全て(All)")]
            dd_options.extend([ft.dropdown.Option(d) for d in unique_dates])

            self.date_filter_dd.options = dd_options

            if self.date_filter_dd.value not in unique_dates and self.date_filter_dd.value != "All":
                self.date_filter_dd.value = "All"

            if not self.date_filter_dd.value:
                self.date_filter_dd.value = "All"

            self.date_filter_dd.disabled = False
            self.date_filter_dd.update()
        except Exception as e:
            print(f"ドロップダウン更新エラー: {e}")

    def render_weather_view(self, region_name):
        """天気ビューのレンダリング"""
        sub_areas_data = self.data_manager.get_forecast_data(region_name)
        if not sub_areas_data:
            return

        selected_date = self.date_filter_dd.value
        self.weather_list_view.controls.clear()

        for sub_area in sub_areas_data:
            original_forecasts = sub_area["forecasts"]

            # 日付フィルター
            if selected_date and selected_date != "All":
                filtered_forecasts = [f for f in original_forecasts if f["day"] == selected_date]
            else:
                filtered_forecasts = original_forecasts

            if not filtered_forecasts:
                continue

            row = self._create_sub_area_row(sub_area["area_name"], filtered_forecasts)
            self.weather_list_view.controls.append(row)

        self.page.update()

    def _create_sub_area_row(self, sub_area_name, forecasts):
        """サブエリア行の作成"""
        mini_cards = [
            self._create_mini_weather_card(f["day"], f["icon"], f["status"], f["temp"], f["color"])
            for f in forecasts
        ]

        return ft.Container(
            padding=ft.padding.symmetric(vertical=10, horizontal=10),
            border=ft.border.only(bottom=ft.border.BorderSide(1, ft.Colors.GREY_200)),
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Text(sub_area_name, size=16, weight=ft.FontWeight.W_500),
                        expand=True,
                    ),
                    ft.Row(controls=mini_cards, spacing=5)
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            )
        )

    def _create_mini_weather_card(self, day, icon, status, temp, icon_color):
        """ミニ天気カードの作成"""
        return ft.Container(
            width=70,
            height=90,
            bgcolor=ft.Colors.BLUE_GREY_50,
            border_radius=8,
            padding=5,
            content=ft.Column(
                controls=[
                    ft.Text(day, size=10, color=ft.Colors.GREY_700),
                    ft.Icon(icon, size=24, color=icon_color),
                    ft.Text(status, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_700),
                    ft.Text(temp, size=12, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2
            )
        )

    def _show_error_screen(self, region_name):
        """エラー画面の表示"""
        self.weather_list_view.controls.clear()
        self.weather_list_view.controls.append(
            ft.Container(
                expand=True,
                alignment=ft.alignment.center,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.WIFI_OFF, size=64, color=ft.Colors.RED_400),
                        ft.Text("No Data Available.", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
                        ft.Text("Connect to internet to fetch new data.", size=14, color=ft.Colors.GREY_500),
                        ft.ElevatedButton("Retry", on_click=lambda e: self.update_weather_display(region_name))
                    ],
                    spacing=10
                )
            )
        )
        self.page.update()


def main(page: ft.Page):
    WeatherApp(page)


if __name__ == "__main__":
    ft.app(target=main)