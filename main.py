import os
import re
import time
import random
import threading
from urllib.parse import urlparse, parse_qs

# Kivy UI 组件
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock, mainthread
from kivy.utils import platform

# 全局中文字体支持
from kivy.core.text import LabelBase, DEFAULT_FONT
LabelBase.register(DEFAULT_FONT, 'font.ttf')

# 网络通信组件
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class VideoDownloaderAndroid(App):
    def build(self):
        self.title = "视频打捞大师 高能进度条版"
        self.base_url = ""
        self.params = {}
        self.save_dir = ""
        self.is_downloading = False
        
        # 预设估计最大切片数（用于计算进度百分比，捕获到 EOF 后会自动更新精确值）
        self.estimated_total = 100 
        
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])

        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        layout.add_widget(Label(text="请粘贴通过黄鸟抓包获得的完整 Request URL (必须带 https://):", size_hint_y=None, height=40))
        self.url_input = TextInput(
            multiline=True, 
            hint_text="示例: https://v.rn212.xyz/hls/abc-720/CLS-001.jpg?v=6&auth=...", 
            size_hint_y=None, 
            height=400  
        )
        layout.add_widget(self.url_input)
        
        self.info_label = Label(text="[状态：等待捕捞指令]", size_hint_y=None, height=120, halign="left", valign="top")
        self.info_label.bind(size=self.info_label.setter('text_size'))
        layout.add_widget(self.info_label)
        
        # 按钮排版
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10)
        
        self.main_btn = Button(text="开始下载切片", background_color=(0.1, 0.6, 0.9, 1))
        self.main_btn.bind(on_press=self.start_download_flow)
        btn_layout.add_widget(self.main_btn)
        
        self.merge_btn = Button(text="合并视频", background_color=(0.1, 0.8, 0.3, 1))
        self.merge_btn.bind(on_press=self.merge_slices)
        btn_layout.add_widget(self.merge_btn)
        
        self.open_dir_btn = Button(text="查看文件", background_color=(0.7, 0.7, 0.7, 1))
        self.open_dir_btn.bind(on_press=self.open_directory)
        btn_layout.add_widget(self.open_dir_btn)
        
        layout.add_widget(btn_layout)
        
        # 日志大屏幕
        scroll = ScrollView()
        self.log_label = Label(text="运行日志:\n", size_hint_y=None, halign="left", valign="top")
        self.log_label.bind(size=self.log_label.setter('text_size'))
        self.log_label.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1]))
        scroll.add_widget(self.log_label)
        layout.add_widget(scroll)
        
        return layout

    # 【防爆显存安全日志机制】永远只保留屏幕最新的 35 行，确保丝滑滚动不隐身
    @mainthread
    def log(self, message):
        lines = self.log_label.text.split('\n')
        lines.append(str(message))
        if len(lines) > 35:
            lines = lines[-35:]
        self.log_label.text = '\n'.join(lines)

    @mainthread
    def update_info(self, message):
        self.info_label.text = str(message)

    def start_download_flow(self, instance):
        raw_url = self.url_input.text.strip()
        if not raw_url:
            self.log("[错误] 输入框内容为空，请粘贴网址。")
            return
        if self.is_downloading:
            return
            
        self.log("\n" + "="*30)
        self.log("[*] 正在分析 Request URL 特征...")
        
        if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
            self.log("[❌ 错误] 链接不合法！必须包含 https:// 开头。")
            return
            
        parsed = urlparse(raw_url)
        if not parsed.netloc or '.' not in parsed.netloc:
            self.log("[❌ 错误] 网址缺失核心服务器域名！")
            return

        if not re.search(r'CLS-\d+\.jpg', raw_url):
            self.log("[❌ 错误] 该链接不包含 CLS-xxx.jpg 切片序列特征！")
            return

        if not self.parse_url_parameters(raw_url):
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
            self.update_info(f"【打捞环境就绪】\n服务器: {parsed_url.netloc}\n缓存目录: {self.save_dir}")
            self.log("[+] 目标链识别成功，准备进入高频拉取阶段...")
            return True
        except Exception as e:
            self.log(f"[❌ 静态解析崩溃] {str(e)}")
            return False

    def create_session(self):
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.mount('http://', HTTPAdapter(max_retries=retries))
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://rou.video/",
            "Connection": "keep-alive"
        })
        return session

    def download_worker(self, index):
        try:
            target_path = os.path.join(self.save_dir, f"CLS-{index:03d}.bin")
            if os.path.exists(target_path) and os.path.getsize(target_path) > 100000:
                return "EXISTS"
                
            url = self.base_url.format(index)
            session = self.create_session()
            time.sleep(random.uniform(0.05, 0.15)) # 略微加快下载频率
            
            response = session.get(url, params=self.params, timeout=10, verify=False)
            if response.status_code in [400, 404]:
                return "EOF"
            elif response.status_code == 200:
                with open(target_path, "wb") as f:
                    f.write(response.content)
                return "SUCCESS"
            elif response.status_code in [401, 403]:
                return f"AUTH_ERR_{response.status_code}"
            else:
                return f"SERVER_ERR_{response.status_code}"
        except Exception as e:
            # 截取前 30 个字符作为精简错误输出，防止撑爆屏幕
            return f"NET_ERR_{str(e)[:30]}"
        finally:
            if 'session' in locals():
                session.close()

    def download_logic(self):
        try:
            self.log("[*] 高并发进度监听打捞引擎启动...")
            continuous_errors = 0
            
            for idx in range(1, 600):
                if not self.is_downloading:
                    break
                
                res = self.download_worker(idx)
                
                # 计算并输出当前进度的数字百分比
                progress_percent = min(int((idx / self.estimated_total) * 100), 99)
                progress_text = f" -> 进度: {progress_percent}% ({idx}/{self.estimated_total})"
                
                if res == "EOF":
                    # 再次校验确认真实尾部
                    if self.download_worker(idx + 1) == "EOF":
                        self.estimated_total = idx - 1
                        self.log(f"\n[✔] 进度: 100% ({self.estimated_total}/{self.estimated_total})")
                        self.log(f"[✔] 成功捕获流尾部信号，切片拉取完毕！")
                        break
                elif res == "SUCCESS":
                    self.log(f"[+] 成功固化: CLS-{idx:03d}.bin" + progress_text)
                    continuous_errors = 0
                elif res == "EXISTS":
                    self.log(f"[-] 跳过重复: CLS-{idx:03d}.bin" + progress_text)
                    continuous_errors = 0
                elif res.startswith("AUTH_ERR_"):
                    code = res.split('_')[-1]
                    self.log(f"[❌ 权限遭拒] CLS-{idx:03d} 状态码 {code}！这意味着您抓包复制的鉴权 auth/exp 参数已过期，或复制不全。")
                    continuous_errors += 1
                elif res.startswith("SERVER_ERR_"):
                    code = res.split('_')[-1]
                    self.log(f"[⚠️ 服务器响应异常] CLS-{idx:03d} 状态码: {code}")
                    continuous_errors += 1
                elif res.startswith("NET_ERR_"):
                    err_info = res.replace("NET_ERR_", "")
                    self.log(f"[⚠️ 网络波动] CLS-{idx:03d} 失败: {err_info}")
                    continuous_errors += 1
                
                # 连续失败 10 次才进行硬拉闸，给网络波动留够容错空间
                if continuous_errors >= 10:
                    self.log("\n[🚫 智能熔断阻断] 连续10个切片全部请求失败。请务必检查黄鸟粘贴链接中 ? 后面的鉴权加密参数是否完整！")
                    break
                    
            self.log("\n[✔] 打捞结束。请点击【合并视频】。")
        except Exception as e:
            self.log(f"\n[线程崩溃]: {str(e)}")
        finally:
            self.is_downloading = False
            Clock.schedule_once(lambda dt: setattr(self.main_btn, 'disabled', False))

    def merge_slices(self, instance):
        if not self.save_dir or not os.path.exists(self.save_dir):
            self.log("[错误] 下载路径为空或不存在。")
            return
        files = [f for f in os.listdir(self.save_dir) if f.endswith(".bin")]
        files.sort()
        if not files:
            self.log("[错误] 未侦测到可拼装的数据块。")
            return
            
        parent_dir = os.path.dirname(self.save_dir)
        video_name = os.path.basename(self.save_dir).replace("slices_", "video_")
        output_mp4 = os.path.join(parent_dir, f"{video_name}.mp4")
        
        self.log(f"[*] 正在将这 {len(files)} 个数据流进行物理二进制拼接...")
        try:
            with open(output_mp4, "wb") as out_f:
                for f in files:
                    with open(os.path.join(self.save_dir, f), "rb") as in_f:
                        out_f.write(in_f.read())
            self.log(f"\n[✔] 物理合流成功！无损 MP4 已归档至手机 Download 目录:\n{output_mp4}")
        except Exception as e:
            self.log(f"[合并失败] {str(e)}")

    def open_directory(self, instance):
        if platform == 'android':
            self.log("\n[提示] 视频文件和缓存均保存在手机系统的【文件管理】 -> 【内部存储】 -> 【Download】 中。")
        else:
            if self.save_dir and os.path.exists(self.save_dir):
                os.startfile(self.save_dir)

if __name__ == "__main__":
    VideoDownloaderAndroid().run()
