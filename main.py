import os
import re
import time
import random
import threading
from urllib.parse import urlparse, parse_qs

# Kivy 核心 UI 组件
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock, mainthread
from kivy.utils import platform

# 强行注入全局中文字体支持
from kivy.core.text import LabelBase, DEFAULT_FONT
LabelBase.register(DEFAULT_FONT, 'font.ttf')

# 极简高能网络库
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class VideoDownloaderAndroid(App):
    def build(self):
        self.title = "视频打捞大师 RequestURL专用版"
        self.base_url = ""
        self.params = {}
        self.save_dir = ""
        self.is_downloading = False
        
        # 运行时向安卓系统申请底层公共读写权限
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])

        # 主界面垂直布局
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        layout.add_widget(Label(text="请粘贴通过黄鸟抓包获得的完整 Request URL (必须带 https://):", size_hint_y=None, height=40))
        self.url_input = TextInput(
            multiline=True, 
            hint_text="示例: https://v.rn212.xyz/hls/abc-720/CLS-001.jpg?v=6&auth=...", 
            size_hint_y=None, 
            height=300  # 维持宽大舒适的粘贴视野
        )
        layout.add_widget(self.url_input)
        
        self.info_label = Label(text="[状态：等待捕捞指令]", size_hint_y=None, height=120, halign="left", valign="top")
        self.info_label.bind(size=self.info_label.setter('text_size'))
        layout.add_widget(self.info_label)
        
        # 极简功能按钮连排
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
        
        # 滚动运行日志大屏幕
        scroll = ScrollView()
        self.log_label = Label(text="运行日志:\n", size_hint_y=None, halign="left", valign="top")
        self.log_label.bind(size=self.log_label.setter('text_size'))
        self.log_label.bind(texture_size=lambda instance, value: setattr(instance, 'height', value[1]))
        scroll.add_widget(self.log_label)
        layout.add_widget(scroll)
        
        return layout

    # 线程安全的流式滚动日志 (防图片高度超限隐身)
    @mainthread
    def log(self, message):
        lines = self.log_label.text.split('\n')
        lines.append(str(message))
        if len(lines) > 40:
            lines = lines[-40:]
        self.log_label.text = '\n'.join(lines)

    @mainthread
    def update_info(self, message):
        self.info_label.text = str(message)

    # ==========================================
    # 核心控制流：直接校验并执行多线程打捞
    # ==========================================
    def start_download_flow(self, instance):
        raw_url = self.url_input.text.strip()
        if not raw_url:
            self.log("[错误] 输入框内容太空，请先粘贴黄鸟抓到的长网址。")
            return
        if self.is_downloading:
            self.log("[提示] 打捞引擎正在轰鸣下载中，请勿连点。")
            return
            
        self.log("\n" + "="*30)
        self.log("[*] 正在执行 Request URL 深度合法性校验...")
        
        # 1. 严格拦截没有 http 协议头的残缺链接
        if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
            self.log("[❌ 致命错误] 链接不完整！")
            self.log("请确保你在黄鸟里长按复制的是【完整URL】，必须包含 https:// 开头。")
            return
            
        # 2. 严格拦截缺失域名的残缺路径
        parsed = urlparse(raw_url)
        if not parsed.netloc or '.' not in parsed.netloc:
            self.log("[❌ 致命错误] 网址缺失核心服务器域名！")
            self.log("您当前粘贴的缺少了域名部分，请重新前往抓包历史复制完整请求。")
            return

        # 3. 拦截不包含序列切片特征的普通链接
        if not re.search(r'CLS-\d+\.jpg', raw_url):
            self.log("[❌ 致命错误] 该长链接不包含 CLS-xxx.jpg 切片序列特征！")
            self.log("请在黄鸟里使用搜索功能，输入关键词“CLS-”，找到带数字后缀的链接再行复制。")
            return

        # 4. 验证通过，解析参数并开辟文件夹
        if not self.parse_url_parameters(raw_url):
            self.log("[❌ 失败] 提取 URL 参数时发生异常崩溃。")
            return
            
        # 进入真实异步线程下载
        self.is_downloading = True
        self.main_btn.disabled = True
        threading.Thread(target=self.download_logic, daemon=True).start()

    def parse_url_parameters(self, raw_url):
        try:
            parsed_url = urlparse(raw_url)
            queries = parse_qs(parsed_url.query)
            # 全量提取加密鉴权 token 参数 (v, exp, auth 等)
            self.params = {k: v[0] for k, v in queries.items()}
            
            path = parsed_url.path
            # 将具体的 CLS-004.jpg 动态格式化为 CLS-{:03d}.jpg 通配模板
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
            self.update_info(f"【打捞环境就绪】\n服务器: {parsed_url.netloc}\n临时目录: {self.save_dir}")
            self.log("[+] 目标链咬合成功，手机本地缓存通道已打通。")
            return True
        except Exception as e:
            self.log(f"[❌ 静态解析崩溃] {str(e)}")
            return False

    # ==========================================
    # 底层二进制流高频固化下载机
    # ==========================================
    def create_session(self):
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
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
            # 如果本地已经有了完整大块，自动秒跳过，实现无断点续传
            if os.path.exists(target_path) and os.path.getsize(target_path) > 100000:
                return "EXISTS"
                
            url = self.base_url.format(index)
            session = self.create_session()
            time.sleep(random.uniform(0.1, 0.25))
            
            response = session.get(url, params=self.params, timeout=12, verify=False)
            if response.status_code in [400, 404]:
                return "EOF"
            elif response.status_code == 200:
                with open(target_path, "wb") as f:
                    f.write(response.content)
                return "SUCCESS"
            else:
                return "ERROR"
        except Exception:
            return "ERROR"
        finally:
            if 'session' in locals():
                session.close()

    def download_logic(self):
        try:
            self.log("[*] 全自动离散切片拉取进程启动...")
            error_count = 0
            
            for idx in range(1, 600):
                if not self.is_downloading:
                    break
                res = self.download_worker(idx)
                
                if res == "EOF":
                    # 双重校验防假尾部
                    if self.download_worker(idx + 1) == "EOF":
                        self.log(f"\n[✔] 成功截获流尾部截止信号，全量切片拉取完毕！")
                        break
                elif res == "SUCCESS":
                    self.log(f"[+] 成功固化切片: CLS-{idx:03d}.bin")
                    error_count = 0
                elif res == "EXISTS":
                    self.log(f"[-] 跳过本地重复副本: CLS-{idx:03d}.bin")
                    error_count = 0
                elif res == "ERROR":
                    error_count += 1
                    # 连续5个切片遭遇断网或鉴权过期，物理熔断保护
                    if error_count >= 5:
                        self.log("\n[🚫 智能熔断] 连续5次请求失败。请确认手机VPN连接是否正常，或该 RequestURL 的 auth 鉴权已在服务器端过期。")
                        break
                        
            self.log("\n[✔] 捕捞流程执行结束。请点击绿色【合并视频】。")
        except Exception as e:
            self.log(f"\n[流水线中断异常]: {str(e)[:50]}")
        finally:
            self.is_downloading = False
            Clock.schedule_once(lambda dt: setattr(self.main_btn, 'disabled', False))

    # ==========================================
    # 二进制数据体完美无损合流
    # ==========================================
    def merge_slices(self, instance):
        if not self.save_dir or not os.path.exists(self.save_dir):
            self.log("[错误] 本地没有检测到任何缓存文件夹，请先点击下载。")
            return
        files = [f for f in os.listdir(self.save_dir) if f.endswith(".bin")]
        files.sort()
        if not files:
            self.log("[错误] 临时文件夹内空空如也，找不到任何可拼接的数据块。")
            return
            
        parent_dir = os.path.dirname(self.save_dir)
        video_name = os.path.basename(self.save_dir).replace("slices_", "video_")
        output_mp4 = os.path.join(parent_dir, f"{video_name}.mp4")
        
        self.log(f"[*] 正在将这 {len(files)} 个二进制数据流进行线性拼接组装...")
        try:
            with open(output_mp4, "wb") as out_f:
                for f in files:
                    with open(os.path.join(self.save_dir, f), "rb") as in_f:
                        out_f.write(in_f.read())
            self.log(f"\n[✔] 物理合流成功！高保真 MP4 已固化至手机 Download 目录:\n{output_mp4}")
        except Exception as e:
            self.log(f"[合并失败] {str(e)}")

    def open_directory(self, instance):
        if platform == 'android':
            self.log("\n[提示] 成果已归档至手机系统自带【文件管理】->【内部存储】->【Download】文件夹中。")
        else:
            if self.save_dir and os.path.exists(self.save_dir):
                os.startfile(self.save_dir)

if __name__ == "__main__":
    VideoDownloaderAndroid().run()
