import os
import re
import time
import requests
import subprocess
from urllib.parse import urlencode


class BilibiliDownloader:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        }

        self.quality_map = {
            80: '高清 1080P',
            64: '高清 720P',
            32: '清晰 480P',
            16: '流畅 360P'
        }

    def sanitize_filename(self, filename, max_length=100):
        filename = re.sub(r'[\\/*?:"<>|]', '', filename)
        filename = re.sub(r'\s+', ' ', filename).strip()
        return filename[:max_length]

    def check_ffmpeg(self):
        """检查FFmpeg是否可用"""
        try:
            subprocess.run(['ffmpeg', '-version'],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            print("未检测到FFmpeg，请先安装FFmpeg并配置系统PATH")
            return False

    def download_stream(self, url, filepath, desc=''):
        """通用下载流方法，支持进度显示"""
        try:
            start_time = time.time()
            response = requests.get(url, headers=self.headers, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024
            downloaded_size = 0

            with open(filepath, 'wb') as f:
                for data in response.iter_content(block_size):
                    f.write(data)
                    downloaded_size += len(data)

                    elapsed_time = time.time() - start_time
                    speed = downloaded_size / elapsed_time if elapsed_time > 0 else 0
                    percent = downloaded_size / total_size * 100 if total_size > 0 else 0

                    print(f"\r{desc}下载进度：{percent:.2f}% | 速度：{speed / 1024:.2f} KB/s", end='', flush=True)

            print(f"\n{desc}下载完成")
            return True
        except Exception as e:
            print(f"\n{desc}下载出错：{e}")
            return False

    def get_video_info(self, url):
        """获取视频基本信息"""
        try:
            bvid = re.search(r'BV[a-zA-Z0-9]+', url)
            if not bvid:
                print("无法提取视频BV号")
                return None

            bvid = bvid.group(0)

            info_url = f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'
            info_response = requests.get(info_url, headers=self.headers)
            info_data = info_response.json()

            if info_data['code'] != 0:
                print(f"获取视频信息失败：{info_data.get('message', '未知错误')}")
                return None

            data = info_data['data']
            return {
                'title': data['title'],
                'bvid': bvid,
                'cid': data['cid']
            }
        except Exception as e:
            print(f"获取视频信息出错：{e}")
            return None

    def get_dash_urls(self, bvid, cid, quality=80):
        """获取DASH格式的视频和音频链接"""
        params = {
            'bvid': bvid,
            'cid': cid,
            'qn': quality,
            'fnver': 0,
            'fnval': 16,
            'fourk': 1
        }

        api_url = 'https://api.bilibili.com/x/player/playurl?' + urlencode(params)

        try:
            response = requests.get(api_url, headers=self.headers)
            data = response.json()

            if data['code'] != 0:
                print(f"获取视频地址失败：{data.get('message', '未知错误')}")
                return None

            # 处理DASH格式
            if 'dash' in data['data']:
                dash_data = data['data']['dash']
                video_url = dash_data['video'][0]['base_url']
                audio_url = dash_data['audio'][0]['base_url']
                return {
                    'video_url': video_url,
                    'audio_url': audio_url
                }
            else:
                print("未找到DASH格式视频")
                return None

        except Exception as e:
            print(f"获取视频地址出错：{e}")
            return None

    def merge_video_audio(self, video_path, audio_path, output_path):
        """
        使用FFmpeg快速合并音视频流
        通过 -c copy 直接复制流，避免重新编码
        """
        try:
            print("\n正在快速合并音视频...")

            # 使用subprocess调用FFmpeg
            subprocess.run([
                'ffmpeg',
                '-i', video_path,  # 输入视频流
                '-i', audio_path,  # 输入音频流
                '-c', 'copy',  # 直接复制流，不重新编码
                '-shortest',  # 以最短流为准
                output_path  # 输出路径
            ], check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)

            return True
        except subprocess.CalledProcessError:
            print("音视频合并失败")
            return False
        except Exception as e:
            print(f"合并过程出错：{e}")
            return False

    def download_video_with_audio(self, url, quality=80):
        # 检查FFmpeg
        if not self.check_ffmpeg():
            return None

        # 创建下载目录
        os.makedirs('downloads', exist_ok=True)

        # 获取视频信息
        video_info = self.get_video_info(url)
        if not video_info:
            return None

        # 选择清晰度
        print("\n可选清晰度：")
        for q, desc in self.quality_map.items():
            print(f"{q}: {desc}")

        try:
            selected_quality = int(input("请输入清晰度代码（默认80）：") or 80)
            if selected_quality not in self.quality_map:
                print("无效的清晰度，使用默认 1080P")
                selected_quality = 80
        except ValueError:
            selected_quality = 80

        # 获取视频和音频链接
        dash_urls = self.get_dash_urls(
            video_info['bvid'],
            video_info['cid'],
            selected_quality
        )
        if not dash_urls:
            return None

        # 构造文件名
        sanitized_title = self.sanitize_filename(video_info['title'])
        quality_desc = self.quality_map.get(selected_quality, '未知清晰度')

        # 临时文件路径
        video_temp = os.path.join('downloads', f"{sanitized_title}_video.mp4")
        audio_temp = os.path.join('downloads', f"{sanitized_title}_audio.m4a")
        final_video = os.path.join('downloads', f"{sanitized_title}_{quality_desc}.mp4")

        # 下载视频流
        if not self.download_stream(dash_urls['video_url'], video_temp, '视频流'):
            return None

        # 下载音频流
        if not self.download_stream(dash_urls['audio_url'], audio_temp, '音频流'):
            return None

        # 合并音视频
        if self.merge_video_audio(video_temp, audio_temp, final_video):
            # 删除临时文件
            os.remove(video_temp)
            os.remove(audio_temp)

            print(f"\n视频下载完成：{final_video}")
            return final_video

        return None


def main():
    downloader = BilibiliDownloader()

    while True:
        url = input("\n请输入B站视频链接（输入 'q' 退出）：").strip()

        if url.lower() in ['q', 'quit', 'exit']:
            print("程序已退出。")
            break

        if not url or 'bilibili.com' not in url:
            print("请输入有效的B站视频链接。")
            continue

        downloader.download_video_with_audio(url)


if __name__ == '__main__':
    main()