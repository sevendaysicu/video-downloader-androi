import os
import re
import time
import random
import threading
from urllib.parse import urlparse, parse_qs

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.utils import platform
from kivy.uix.popup import Popup

from kivy.core.text import LabelBase, DEFAULT_FONT
LabelBase.register(DEFAULT_FONT, 'font.ttf')

import yt_dlp
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class LoadingPopup(Popup):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "请稍候"
        self.size_hint = (0.7, 0.4)
        self.auto_dismiss = False 
        
        self.spinner_chars = ['-', '\\', '|', '/']
        self.char_index = 0
        
        self.loading_label = Label(text="正在全速解析底层切片...", font_size=16)
        self.add_widget(self.loading_label)
        self.update_event = Clock.schedule_interval(self.update_spinner, 0.1)

    def update_spinner(self, dt):
        self.char_index = (self.char_index + 1) % len(self.spinner_chars)
        self.loading_label.text = f"正在伪装浏览器抓包...\n\n           {self.spinner_chars[self.char_index]}"

    def close_animation(self):
        self.update_event.cancel()
        self.dismiss()

class VideoDownloaderAndroid(App):
    def build(self):
        self.title = "视频打捞大师 Android版"
        
        self.base_url = ""
        self.params = {}
        self.save_dir = ""
        self.is_downloading = False
        
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])

        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        layout.add_widget(Label(text="请粘贴视频播放网页的网址 (或底层Request URL):", size_hint_y=None, height=40))
        self.url_input = TextInput(
            multiline=True, 
            hint_text="例如: https://v.douyin.com/... 或 https://v.rn...", 
            size_hint_y=None, 
            height=120
        )
        layout.add_widget(self.url_input)
        
        self.info_label = Label(
            text="[等待解析参数...]", 
            size_hint_y=None, 
            height=160,
            halign="left", 
            valign="top"
        )
        self.info_label.bind(size=self.info_label.setter('text_size'))
        layout.add_widget(self.info_label)
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10)
        
        # 移除了会导致豆腐块的 Emoji
        self.parse_btn = Button(text="智能解析", background_color=(0.8, 0.4, 0.1, 1))
        self.parse_btn.bind(on_press=self.on_btn_click_parse)
        btn_layout.add_widget(self.parse_btn)
        
        self.download_btn = Button(text="下载切片", background_color=(0.1, 0.6, 0.9, 1))
        self.download_btn.bind(on_press=self.start_download_thread)
        btn_layout.add_widget(self.download_btn)
        
        self.merge_btn = Button(text="合并视频", background_color=(0.1, 0.8, 0.3, 1))
        self.merge_btn.bind(on_press=self.merge_slices)
        btn_layout.add_widget(self.merge_btn)
        
        self.open_dir_btn = Button(text="查看文件", background_color=(0.7, 0.7, 0.7, 1))
        self.open_dir_btn.bind(on_press=self.open_directory)
        btn_layout.add_widget(self.open_dir_btn)
        
        layout.add_widget(btn_layout)
        
        scroll = ScrollView()
        self.log_label = Label(
            text="运行日志:\n", 
            size_hint_y=None, 
            halign="left", 
            valign="top"
        )
        self.log_label.bind(size=self.log_label.setter('text_size'))
        self.log_label.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1]))
        scroll.add_widget(self.log_label)
        layout.add_widget(scroll)
        
        return layout

    def on_btn_click_parse(self, instance):
        user_pasted_page_url = self.url_input.text.strip()
        if not user_pasted_page_url:
            self.log("[提示] 请先粘贴网页链接！")
            return
            
        self.loading_popup = LoadingPopup()
        self.loading_popup.open()
        
        threading.Thread(target=self.auto_parse_video_url, args=(user_pasted_page_url,), daemon=True).start()

    def auto_parse_video_url(self, page_url):
        ydl_opts = {'quiet': True, 'no_warnings': True, 'format': 'best'}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(page_url, download=False)
                real_video_url = info_dict.get('url', None)
                
                if real_video_url:
                    Clock.schedule_once(lambda dt: self.on_parse_success(real_video_url))
                else:
                    Clock.schedule_once(lambda dt: self.show_error("[错误] 未能提取到底层切片链接。"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.show_error(f"[解析失败] {str(e)}"))

    def on_parse_success(self, real_url):
        if hasattr(self, 'loading_popup'):
            self.loading_popup.close_animation()
            
        self.url_input.text = real_url
        self.log(f"\n[成功] 网页解析完成！已自动填入底层真实链接。\n提取到的链接前缀: {real_url[:60]}...\n请点击【下载切片】启动引擎！")

    def show_error(self, message):
        if hasattr(self, 'loading_popup'):
            self.loading_popup.close_animation()
        self.log(message)

    def log(self, message):
        Clock.schedule_once(lambda dt: setattr(self.log_label, 'text', self.log_label.text + message + "\n"))

    def update_info(self, message):
        Clock.schedule_once(lambda dt: setattr(self.info_label, 'text', message))

    def parse_url(self):
        raw_url = self.url_input.text.strip()
        if not raw_url:
            self.update_info("[错误] 网址不能为空")
            return False
            
        try:
            parsed_url = urlparse(raw_url)
            queries = parse_qs(parsed_url.query)
            self.params = {k: v[0] for k, v in queries.items()}
            
            path = parsed_url.path
            if not re.search(r'CLS-\d+\.jpg', path):
                self.update_info("[错误] 无法定位 CLS-xxx.jpg 序列，请确保这是有效的切片地址。")
                return False
                
            standard_path = re.sub(r'CLS-\d+\.jpg', 'CLS-{:03d}.jpg', path)
            self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{standard_path}"
            
            video_id_match = re.search(r'/hls/([^/]+)/', path)
            video_id = video_id_match.group(1) if video_id_match else "default_video"
            
            if platform == 'android':
                from android.storage import primary_external_storage_path
                downloads_path = os.path.join(primary_external_storage_path(), "Download")
                self.save_dir = os.path.join(downloads_path, f"slices_{video_id}")
            else:
                self.save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"slices_{video_id}")
                
            os.makedirs(self.save_dir, exist_ok=True)
            
            self.update_info(
                f"【环境就绪】\n域名: {parsed_url.netloc}\n视频ID: {video_id}\n保存至: {self.save_dir}"
            )
            return True
        except Exception as e:
            self.update_info(f"[验证异常] {str(e)}")
            return False

    def create_session(self):
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.mount('http://', HTTPAdapter(max_retries=retries))
        
        # ⚠️ 这里已经为你移除了导致安卓断网死锁的 127.0.0.1 代理代码！
        # 手机开启 VPN 时，系统会自动代理流量，Python 代码必须保持纯净。
        
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            "Referer": "https://rou.video/",
            "Connection": "keep-alive"
        })
        return session

    def download_worker(self, index):
        target_path = os.path.join(self.save_dir, f"CLS-{index:03d}.bin")
        if os.path.exists(target_path) and os.path.getsize(target_path) > 100000:
            return "EXISTS"
            
        url = self.base_url.format(index)
        session = self.create_session()
        time.sleep(random.uniform(0.2, 0.4))
        
        try:
            response = session.get(url, params=self.params, timeout=15, verify=False)
            if response.status_code in [400, 404]:
                return "EOF"
            elif response.status_code == 200:
                with open(target_path, "wb") as f:
                    f.write(response.content)
                return "SUCCESS"
            else:
                return "ERROR"
        except:
            return "ERROR"
        finally:
            session.close()

    def start_download_thread(self, instance):
        if self.is_downloading or not self.parse_url():
            return
        self.is_downloading = True
        self.download_btn.disabled = True
        threading.Thread(target=self.download_logic, daemon=True).start()

    def download_logic(self):
        self.log("[*] 安卓异步打捞引擎启动...")
        for idx in range(1, 600):
            res = self.download_worker(idx)
            if res == "EOF":
                if self.download_worker(idx + 1) == "EOF":
                    self.log(f"\n[成功] 捕获尾部信号，切片下载完成！")
                    break
            elif res == "SUCCESS":
                self.log(f"[+] 固化切片: CLS-{idx:03d}.bin")
            elif res == "EXISTS":
                self.log(f"[-] 跳过已存在切片: CLS-{idx:03d}.bin")
            else:
                self.log(f"[异常] 切片 CLS-{idx:03d} 异常，重试中...")
                
        self.log("\n[完成] 缓存全部固化。请点击【合并视频】。")
        self.is_downloading = False
        self.download_btn.disabled = False

    def merge_slices(self, instance):
        if not self.save_dir or not os.path.exists(self.save_dir):
            self.log("[错误] 未找到下载路径")
            return
            
        files = [f for f in os.listdir(self.save_dir) if f.endswith(".bin")]
        files.sort()
        
        if not files:
            self.log("[错误] 没有检测到可合并的切片")
            return
            
        parent_dir = os.path.dirname(self.save_dir)
        video_name = os.path.basename(self.save_dir).replace("slices_", "video_")
        output_mp4 = os.path.join(parent_dir, f"{video_name}.mp4")
        
        self.log(f"[*] 正在物理拼装 {len(files)} 个数据流...")
        try:
            with open(output_mp4, "wb") as out_f:
                for f in files:
                    with open(os.path.join(self.save_dir, f), "rb") as in_f:
                        out_f.write(in_f.read())
            self.log(f"\n[成功] 视频拼装成功！\n保存在手机系统下载目录:\n{output_mp4}")
        except Exception as e:
            self.log(f"[合并失败] {str(e)}")

    def open_directory(self, instance):
        if platform == 'android':
            self.log("\n[提示] 视频和缓存均保存在手机系统的【文件管理】 -> 【内部存储】 -> 【Download】 中。")
        else:
            if self.save_dir and os.path.exists(self.save_dir):
                os.startfile(self.save_dir)

if __name__ == "__main__":
    VideoDownloaderAndroid().run()
