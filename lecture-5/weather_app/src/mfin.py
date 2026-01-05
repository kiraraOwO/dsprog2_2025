# flet version need to be 0.28.3, search bar cannot work on >= 0.80.0
# fletバージョンは0.28.3が必要です。0.80.0以降ではSearchBarが動作しません。
# デモ動画 https://drive.google.com/file/d/1LVq1lc8wxFMiqcOD53cxg5abDCEE9ib7/view?usp=sharing
import flet as ft
import difflib
import requests
import datetime


class DataManager:
    def __init__(self):
        self.area_name_list = []
        self.name_to_id = {}
        self.weather_data = {}
        self._load_area_data()

    def _load_area_data(self):
        url = "https://www.jma.go.jp/bosai/common/const/area.json"
        print(f"Download region data from {url} ...")
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            full_data = response.json()
            offices = full_data.get("offices", {})

            self.area_master_data = offices
            self.area_name_list = []
            self.name_to_id = {}

            for code, info in offices.items():
                name = info["name"]
                self.area_name_list.append(name)
                self.name_to_id[name] = code

            print(f"Region data load succeed. {len(self.area_name_list)} areas loaded.")

        except Exception as e:
            print(f"Cannot load region data. E: {e}")
            fallback_offices = {
                "130000": {"name": "東京都"},
                "270000": {"name": "大阪府"}
            }

            self.area_master_data = fallback_offices
            self.area_name_list = []
            self.name_to_id = {}

            for code, info in fallback_offices.items():
                name = info["name"]
                self.area_name_list.append(name)
                self.name_to_id[name] = code

    def _get_jma_icon_and_color(self, code):
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

    def _get_jma_status_text(self, code):
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

    def _parse_jma_data(self, raw_json):
        try:
            report_short = raw_json[0]

            report_weekly = raw_json[1] if len(raw_json) > 1 else raw_json[0]
            is_weekly_mode = len(raw_json) > 1

            short_term_temps_map = []

            st_temp_series = None
            for series in report_short["timeSeries"]:
                if series.get("areas") and "temps" in series["areas"][0]:
                    st_temp_series = series
                    break

            if st_temp_series:
                for area in st_temp_series["areas"]:
                    short_term_temps_map.append(area["temps"])

            ts_weather = None
            ts_temp = None

            for series in report_weekly["timeSeries"]:
                if not series.get("areas"): continue
                keys = series["areas"][0].keys()
                if "weatherCodes" in keys:
                    ts_weather = series
                elif "temps" in keys or "tempsMin" in keys:
                    ts_temp = series

            if not ts_weather: return []

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
                        weekly_temp_data.append({"type": "daily", "temps": area["temps"]})

            time_defines = ts_weather["timeDefines"]
            formatted_dates = []
            for t in time_defines:
                dt = datetime.datetime.fromisoformat(t)
                formatted_dates.append(f"{dt.month}/{dt.day}")

            parsed_result = []

            for i_area, area_data in enumerate(ts_weather["areas"]):
                sub_area_name = area_data["area"]["name"]
                weather_codes = area_data["weatherCodes"]

                current_weekly_temps = weekly_temp_data[i_area] if i_area < len(weekly_temp_data) else None
                current_short_temps = short_term_temps_map[i_area] if i_area < len(short_term_temps_map) else []

                forecasts = []
                for i_time in range(len(time_defines)):
                    if i_time >= len(weather_codes): break

                    code = weather_codes[i_time]
                    icon, color = self._get_jma_icon_and_color(code)
                    status_text = self._get_jma_status_text(code)
                    display_temp = "--"

                    if current_weekly_temps:
                        if current_weekly_temps["type"] == "weekly":
                            min_v = current_weekly_temps["mins"][i_time]
                            max_v = current_weekly_temps["maxs"][i_time]

                            if (min_v == "" or max_v == "") and i_time == 0:
                                if current_short_temps:
                                    if len(current_short_temps) >= 2:
                                        t1 = current_short_temps[0]
                                        t2 = current_short_temps[1]
                                        display_temp = f"{t1}-{t2}°C"
                                    elif len(current_short_temps) == 1:
                                        display_temp = f"{current_short_temps[0]}°C"
                                else:
                                    display_temp = "--"  # こうになったらマジで死んだ
                            else:
                                if min_v and max_v:
                                    display_temp = f"{min_v}-{max_v}°C"
                                else:
                                    display_temp = f"{max_v if max_v else min_v}°C"

                        elif current_weekly_temps["type"] == "daily":
                            val = current_weekly_temps["temps"][i_time]
                            if val: display_temp = f"{val}°C"

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
            print(f"Parse failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def fetch_weather_data(self, region_id):
        url = f"https://www.jma.go.jp/bosai/forecast/data/forecast/{region_id}.json"

        print(f"Requesting: {url} ...")
        try:
            r = requests.get(url)
            r.raise_for_status()
            raw_json = r.json()
            print("Data:", raw_json)
            parsed_data = self._parse_jma_data(raw_json)

            region_name = next((name for name, code in self.name_to_id.items() if code == region_id), None)

            if region_name:
                self.weather_data[region_name] = parsed_data
                return True
            return False

        except Exception as e:
            print(f"Get data failed: {e}")
            return False

    def search_area(self, keyword):
        return difflib.get_close_matches(keyword, self.area_name_list, n=5, cutoff=0.2)

    def get_forecast_data(self, region_name):
        return self.weather_data.get(region_name, [])


def create_mini_weather_card(day, icon, status, temp, icon_color):
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


def create_sub_area_row(sub_area_name, forecasts):
    mini_cards = []
    for f in forecasts:
        mini_cards.append(create_mini_weather_card(f["day"], f["icon"], f["status"], f["temp"], f["color"]))

    return ft.Container(
        padding=ft.padding.symmetric(vertical=10, horizontal=10),
        border=ft.border.only(bottom=ft.border.BorderSide(1, ft.Colors.GREY_200)),
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Text(sub_area_name, size=16, weight=ft.FontWeight.W_500),
                    expand=True,
                ),
                ft.Row(
                    controls=mini_cards,
                    spacing=5
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )
    )


def create_list_item(text, on_click_func, on_delete_func):
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Text(text, size=16),
                    expand=True,
                    on_click=on_click_func,
                    padding=10,
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=ft.Colors.RED_300,
                    icon_size=20,
                    on_click=on_delete_func
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        width=float("inf"),
        border_radius=5,
        bgcolor=ft.Colors.TRANSPARENT,
        on_hover=lambda e: (
                setattr(e.control, 'bgcolor',
                        ft.Colors.WHITE if e.data == "true" else ft.Colors.TRANSPARENT) or e.control.update()
        ),
    )


class WeatherApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.data_manager = DataManager()
        self.current_saved_regions = ["東京都"]

        self._setup_page()
        self._init_controls()

        self.render_saved_list()
        self.update_weather_display("東京都")


    def _setup_page(self):
        self.page.title = "日本天気予報(Japan Weather Forecast)"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.window_width = 900
        self.page.window_height = 600
        self.page.padding = 0

    def _init_controls(self):
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

        self.saved_list_col = ft.Column(spacing=2)

        self.current_region_text = ft.Text(
            value="エリア選択(Choose area)", size=30, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER
        )

        self.weather_list_view = ft.ListView(
            expand=True,
            spacing=0,
            padding=20
        )

        self.sidebar = self._build_sidebar()
        self.content_area = self._build_content_area()

        self.page.add(ft.Row(controls=[self.sidebar, self.content_area], expand=True, spacing=0))

    def _build_sidebar(self):
        return ft.Container(
            width=250, bgcolor=ft.Colors.BLUE_GREY_50, padding=10,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        padding=ft.padding.only(bottom=10, top=10),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,

                            controls=[
                                ft.Icon(name=ft.Icons.WB_SUNNY, color=ft.Colors.ORANGE, size=24),
                                ft.Text(
                                    "日本天気",
                                    size=22,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.BLUE_900
                                ),
                                ft.Icon(name=ft.Icons.CLOUD, color=ft.Colors.BLUE_GREY, size=24),
                            ]
                        )
                    ),

                    self.search_bar,

                    ft.Divider(),
                    ft.Container(
                        alignment=ft.alignment.center_left,  # 收藏列表标题通常建议靠左，或者也 center
                        content=ft.Text("お気に入り(Stars)", size=12, color=ft.Colors.GREY)
                    ),
                    self.saved_list_col
                ],
                spacing=10
            )
        )

    def _build_content_area(self):
        return ft.Container(
            expand=True, padding=0, bgcolor=ft.Colors.WHITE,
            content=ft.Column(
                controls=[
                    ft.Container(height=30),
                    self.current_region_text,
                    ft.Divider(),
                    self.weather_list_view,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0
            )
        )

    def handle_search_change(self, e):
        keyword = e.data

        if not keyword:
            self._show_all_regions()
        else:
            matches = [
                name for name in self.data_manager.area_name_list
                if keyword in name
            ]

            new_controls = []
            for name in matches:
                new_controls.append(
                    ft.ListTile(
                        title=ft.Text(name),
                        leading=ft.Icon(ft.Icons.LOCATION_CITY),
                        on_click=lambda e, n=name: self.close_search_and_add(n)
                    )
                )
            self.search_bar.controls = new_controls
            self.search_bar.update()

            self.search_bar.open_view()

    def handle_search_tap(self, e):
        if not self.search_bar.value:
            self._show_all_regions()

        self.search_bar.open_view()

    def _show_all_regions(self):
        if not self.data_manager.area_name_list:
            self.search_bar.controls = [ft.ListTile(title=ft.Text("Loading area data..."))]
        else:
            all_items = []
            for name in self.data_manager.area_name_list:
                all_items.append(
                    ft.ListTile(
                        title=ft.Text(name),
                        leading=ft.Icon(ft.Icons.LOCATION_CITY),
                        on_click=lambda e, n=name: self.close_search_and_add(n)
                    )
                )
            self.search_bar.controls = all_items

        self.search_bar.update()

    def close_search_and_add(self, region_name):
        self.search_bar.close_view(region_name)
        self.add_region(region_name)

    def add_region(self, region_name):
        if not region_name:
            return

        if region_name in self.current_saved_regions:
            print(f"{region_name} already in saved list.")
            self.update_weather_display(region_name)
            return

        self.current_saved_regions.append(region_name)
        self.render_saved_list()

        self.update_weather_display(region_name)

    def remove_region(self, region_name):
        if region_name in self.current_saved_regions:
            self.current_saved_regions.remove(region_name)
            self.render_saved_list()
            if self.current_region_text.value == region_name:
                self.current_region_text.value = "Choose one area"
                self.weather_list_view.controls.clear()
                self.page.update()

    def render_saved_list(self):
        self.saved_list_col.controls.clear()
        for region in self.current_saved_regions:
            self.saved_list_col.controls.append(
                create_list_item(
                    text=region,
                    on_click_func=lambda e, r=region: self.update_weather_display(r),
                    on_delete_func=lambda e, r=region: self.remove_region(r)
                )
            )
        self.page.update()

    def update_weather_display(self, region_name):
        self.current_region_text.value = region_name

        if region_name not in self.data_manager.weather_data:
            region_id = self.data_manager.name_to_id.get(region_name)
            if region_id:
                success = self.data_manager.fetch_weather_data(region_id)

                if not success:
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
                                    ft.Text("Network connect failed.", size=20, weight=ft.FontWeight.BOLD,
                                            color=ft.Colors.GREY_700),
                                    ft.Text("Please check your network.", size=14, color=ft.Colors.GREY_500),
                                    ft.ElevatedButton(
                                        "Retry",
                                        on_click=lambda e: self.update_weather_display(region_name)
                                    )
                                ],
                                spacing=10
                            )
                        )
                    )
                    self.page.update()
                    return

        sub_areas_data = self.data_manager.get_forecast_data(region_name)

        self.weather_list_view.controls.clear()

        for sub_area in sub_areas_data:
            row = create_sub_area_row(sub_area["area_name"], sub_area["forecasts"])
            self.weather_list_view.controls.append(row)

        self.page.update()


def main(page: ft.Page):
    WeatherApp(page)


if __name__ == "__main__":
    ft.app(target=main)