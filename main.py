import os
import re
import time
import random
import threading
import socket
import traceback
from urllib.parse import urlparse, parse_qs

# Kivy 核心组件
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock, mainthread
from kivy.utils import platform
from kivy.uix.popup import Popup

# 引入并注册全局中文字体
from kivy.core.text import LabelBase, DEFAULT_FONT
LabelBase.register(DEFAULT_FONT, 'font.ttf')

# 引入解析引擎
import yt_dlp
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
socket.setdefaulttimeout(15)

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
        self.title = "视频打捞大师 终极防死锁版"
        
        self.base_url = ""
        self.params = {}
        self.save_dir = ""
        self.is_downloading = False
        
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])

        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        layout.add_widget(Label(text="请粘贴视频播放网页网址 或 抓包获得的 Request URL:", size_hint_y=None, height=40))
        self.url_input = TextInput(
            multiline=True, 
            hint_text="任意支持的视频网页链接，或者包含 CLS-xxx.jpg 的切片请求地址...", 
            size_hint_y=None, 
            height=200
        )
        layout.add_widget(self.url_input)
        
        self.info_label = Label(
            text="[引擎就绪：等待输入指令]", 
            size_hint_y=None, 
            height=120,
            halign="left", 
            valign="top"
        )
        self.info_label.bind(size=self.info_label.setter('text_size'))
        layout.add_widget(self.info_label)
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10)
        
        self.main_btn = Button(text="开始智能打捞", background_color=(0.1, 0.6, 0.9, 1))
        self.main_btn.bind(on_press=self.start_smart_process)
        btn_layout.add_widget(self.main_btn)
        
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

    # ==========================================
    # 【核心修复】工业级线程安全日志刷新器
    # 彻底解决 Kivy 底层渲染拥堵导致的丢弃日志问题
    # ==========================================
    @mainthread
    def log(self, message):
        self.log_label.text += str(message) + "\n"

    @mainthread
    def update_info(self, message):
        self.info_label.text = str(message)

    def start_smart_process(self, instance):
        raw_url = self.url_input.text.strip()
        if not raw_url:
            self.log("[错误] 输入框内容为空，请先粘贴有效网址。")
            return
            
        if self.is_downloading:
            self.log("[提示] 引擎轰鸣中，请勿重复点击。")
            return
            
        self.log("\n" + "="*30)
        self.log("[*] 智能分析链路已启动...")
        
        if re.search(r'CLS-\d+\.jpg', raw_url):
            self.log("[+] 检测到直接切片请求，并轨至固化下载流...")
            self.start_download_flow(raw_url)
        else:
            self.log("[+] 检测到普通网址，唤醒抓包嗅探引擎...")
            self.loading_popup = LoadingPopup()
            self.loading_popup.open()
            threading.Thread(target=self.async_web_parse, args=(raw_url,), daemon=True).start()

    def async_web_parse(self, page_url):
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True, 
            'format': 'best',
            'nocheckcertificate': True,
            'socket_timeout': 15
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(page_url, download=False)
                real_video_url = info_dict.get('url', None)
                
                if real_video_url:
                    Clock.schedule_once(lambda dt: self.on_parse_success(real_video_url))
                else:
                    Clock.schedule_once(lambda dt: self.on_parse_error("[错误] 未能提取到视频主链。"))
        except Exception as e:
            err = str(e)
            Clock.schedule_once(lambda dt: self.on_parse_error(f"[解析异常中断] {err}"))

    def on_parse_success(self, real_url):
        if hasattr(self, 'loading_popup'):
            self.loading_popup.close_animation()
        self.url_input.text = real_url
        self.log("[✔] 网页嗅探成功！已将底层真实主链提取回输入框。")
        self.start_download_flow(real_url)

    def on_parse_error(self, error_msg):
        if hasattr(self, 'loading_popup'):
            self.loading_popup.close_animation()
        self.log(error_msg)

    def start_download_flow(self, url):
        if not self.parse_url_parameters(url):
            self.log("[❌ 打捞中止] 目标特征校验失败。")
            return
            
        self.is_downloading = True
        self.main_btn.disabled = True
        threading.Thread(target=self.download_logic, daemon=True).start()

    def parse_url_parameters(self, raw_url):
        try:
            parsed_url = urlparse(raw_url)
            queries = parse_qs(parsed_url.query)
            self.params = {k: v[0] for k, v in queries.items()}
            
            path = parsed_url.path
            if not re.search(r'CLS-\d+\.jpg', path):
                self.log("[错误] 链路 Path 无法定位 CLS-xxx.jpg 切片特征。")
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
            
            self.update_info(f"【打捞环境就绪】\n域名: {parsed_url.netloc}\n视频ID: {video_id}\n保存至: {self.save_dir}")
            self.log("[+] 目标特征识别成功，保存路径建立完毕。")
            return True
        except Exception as e:
            self.log(f"[❌ 特征提取奔溃] {str(e)}")
            return False

    def create_session(self):
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.mount('http://', HTTPAdapter(max_retries=retries))
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
            "Referer": "https://rou.video/",
            "Connection": "keep-alive"
        })
        return session

    # ==========================================
    # 【核心修复】上帝视角的全局异常包裹
    # 如果线程死锁，彻底打印死因
    # ==========================================
    def download_worker(self, index):
        try:
            target_path = os.path.join(self.save_dir, f"CLS-{index:03d}.bin")
            if os.path.exists(target_path) and os.path.getsize(target_path) > 100000:
                return "EXISTS"
                
            url = self.base_url.format(index)
            # 初始化网络组件被移入了 try 保护块内，防止开局暴毙
            session = self.create_session()
            time.sleep(random.uniform(0.1, 0.3))
            
            response = session.get(url, params=self.params, timeout=12, verify=False)
            if response.status_code in [400, 404]:
                return "EOF"
            elif response.status_code == 200:
                with open(target_path, "wb") as f:
                    f.write(response.content)
                return "SUCCESS"
            else:
                self.log(f"[异常] CLS-{index:03d} 状态码异常: {response.status_code}")
                return "ERROR"
        except Exception as e:
            self.log(f"[网络异常] CLS-{index:03d} 报错: {str(e)}")
            return "ERROR"
        finally:
            if 'session' in locals():
                session.close()

    def download_logic(self):
        try:
            self.log("[*] 高并发打捞引擎正式启动...")
            for idx in range(1, 600):
                if not self.is_downloading:
                    break
                res = self.download_worker(idx)
                if res == "EOF":
                    if self.download_worker(idx + 1) == "EOF":
                        self.log(f"\n[✔] 成功捕获流尾部信号，切片链下载完毕！")
                        break
                elif res == "SUCCESS":
                    self.log(f"[+] 固化: CLS-{idx:03d}.bin")
                elif res == "EXISTS":
                    self.log(f"[-] 跳过重复: CLS-{idx:03d}.bin")
            self.log("\n[✔] 所有缓存固化完成，请点击【合并视频】。")
        except Exception as e:
            # 如果依然出现神秘死锁，这里会将全部 Traceback 调用栈直接打印在手机上
            err_msg = traceback.format_exc()
            self.log(f"\n[致命崩溃] 引擎遭遇未知的线程断裂:\n{err_msg}")
        finally:
            self.is_downloading = False
            # 确保无论如何解开按钮锁定
            Clock.schedule_once(lambda dt: setattr(self.main_btn, 'disabled', False))

    def merge_slices(self, instance):
        if not self.save_dir or not os.path.exists(self.save_dir):
            self.log("[错误] 下载路径为空或不存在。")
            return
            
        files = [f for f in os.listdir(self.save_dir) if f.endswith(".bin")]
        files.sort()
        
        if not files:
            self.log("[错误] 未侦测到可拼装的 .bin 数据块。")
            return
            
        parent_dir = os.path.dirname(self.save_dir)
        video_name = os.path.basename(self.save_dir).replace("slices_", "video_")
        output_mp4 = os.path.join(parent_dir, f"{video_name}.mp4")
        
        self.log(f"[*] 正在将 {len(files)} 个数据流进行物理二进制拼接...")
        try:
            with open(output_mp4, "wb") as out_f:
                for f in files:
                    with open(os.path.join(self.save_dir, f), "rb") as in_f:
                        out_f.write(in_f.read())
            self.log(f"\n[✔] 视频拼装成功！无损 MP4 已归档至系统下载目录:\n{output_mp4}")
        except Exception as e:
            self.log(f"[合并崩溃] {str(e)}")

    def open_directory(self, instance):
        if platform == 'android':
            self.log("\n[提示] 视频保存在手机系统的【文件管理】 -> 【内部存储】 -> 【Download】 中。")
        else:
            if self.save_dir and os.path.exists(self.save_dir):
                os.startfile(self.save_dir)

if __name__ == "__main__":
    VideoDownloaderAndroid().run()
