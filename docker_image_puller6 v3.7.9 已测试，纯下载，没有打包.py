# docker_puller.py v3.7.9
import os
import sys
import re
import time
import random
import hashlib
import threading
import argparse
import logging
import concurrent.futures
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm
import urllib3

# ----------------- 初始化配置 -----------------
# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
VERSION = "v3.7.9"

# ----------------- 配置参数 -----------------
CONNECT_TIMEOUT = 600
READ_TIMEOUT = 7200
MAX_RETRIES = 20
RETRY_BACKOFF_BASE = 5
MAX_THREADS = 20

# ----------------- 性能配置 -----------------
INIT_CHUNK_SIZE = 256 * 1024  # 256KB
LARGE_FILE_THRESHOLD = 500 * 1024 * 1024  # 500MB
LARGE_CHUNK_SIZE = 2 * 1024 * 1024  # 2MB

# ----------------- 日志配置（顶层定义确保全局访问） -----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("docker_puller.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ----------------- 工具函数 -----------------
def parse_image_input(image_input):
    """解析镜像名称"""
    try:
        if ":" in image_input:
            img_tag, tag = image_input.rsplit(":", 1)
        else:
            img_tag, tag = image_input, "latest"

        if "/" in img_tag:
            *repo_parts, img = img_tag.split("/")
            repo = "/".join(repo_parts)
        else:
            repo, img = "library", img_tag

        return repo, img, tag
    except Exception as e:
        logger.error(f"镜像格式解析失败: {image_input}")
        raise ValueError(f"无效的镜像格式: {image_input}") from e

def get_auth_head(session, registry, repository):
    """处理认证"""
    try:
        base_url = f"https://{registry}/v2/?_ts={int(time.time())}"
        resp = session.get(base_url, verify=False, timeout=CONNECT_TIMEOUT)

        if resp.status_code == 401:
            auth_header = resp.headers.get("Www-Authenticate", "")
            auth_params = dict(re.findall(r'(\w+)=["]([^"]+)["]', auth_header))

            if "realm" not in auth_params:
                raise ValueError("认证头缺少realm参数")

            token_url = (
                f"{auth_params['realm']}?service={auth_params.get('service', registry)}"
                f"&scope=repository:{repository}:pull&_ts={int(time.time())}"
            )
            token_resp = session.get(token_url, verify=False, timeout=CONNECT_TIMEOUT)
            token_resp.raise_for_status()

            return {
                "Authorization": f"Bearer {token_resp.json()['token']}",
                "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            }
        return {}
    except Exception as e:
        logger.error(f"认证失败: {str(e)}")
        raise

def fetch_manifest(session, registry, repository, tag, auth_head):
    """获取清单（包含config层）"""
    try:
        url = f"https://{registry}/v2/{repository}/manifests/{tag}?_ts={int(time.time())}"
        headers = auth_head.copy()
        headers["Accept"] = "application/vnd.docker.distribution.manifest.v2+json"

        resp = session.get(url, headers=headers, verify=False, timeout=CONNECT_TIMEOUT)
        resp.raise_for_status()

        manifest = resp.json()
        schema_version = manifest.get("schemaVersion", 1)

        layers = []
        if schema_version == 1:
            layers = [layer["blobSum"] for layer in manifest["fsLayers"]]
        elif schema_version == 2:
            config_digest = manifest["config"]["digest"]
            layers = [config_digest] + [layer["digest"] for layer in manifest["layers"]]
        else:
            raise ValueError(f"不支持的清单版本: {schema_version}")

        return {"manifest": manifest, "layers": layers}
    except requests.exceptions.RequestException as e:
        logger.error(f"清单请求失败: {str(e)}")
        raise

# ----------------- 类定义 -----------------
class ConnectionManager:
    """连接管理器"""
    def __init__(self):
        self.session = requests.Session()
        self.last_refresh = time.time()
        self.retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF_BASE,
            status_forcelist=[408, 416, 429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            respect_retry_after_header=True,
            raise_on_status=False
        )
        self.adapter = HTTPAdapter(
            max_retries=self.retry_strategy,
            pool_connections=50,
            pool_maxsize=50,
            pool_block=True
        )
        self.session.mount("https://", self.adapter)

    def refresh_connection(self):
        """刷新连接"""
        self.session.close()
        self.session = requests.Session()
        self.session.mount("https://", self.adapter)
        self.last_refresh = time.time()
        logger.info("连接已刷新")

    def get_session(self):
        """获取会话（每5分钟强制刷新）"""
        if time.time() - self.last_refresh > 300:
            self.refresh_connection()
        return self.session

class ThreadSafeProgress:
    """进度管理"""
    def __init__(self, total_layers):
        self.progress_bars = {}
        self.lock = threading.Lock()
        self.total = total_layers
        self.start_time = time.time()
        self.completed = 0

    def create_bar(self, digest):
        with self.lock:
            bar = tqdm(
                total=100,
                desc=digest[:12],
                leave=False,
                position=len(self.progress_bars),
                bar_format="{l_bar}{bar}| {n_fmt}% [{elapsed}<{remaining}]",
                mininterval=1,
                miniters=1
            )
            self.progress_bars[digest] = bar
            return bar

    def update_global(self):
        """全局进度"""
        with self.lock:
            self.completed += 1
            elapsed = time.strftime(
                "%H:%M:%S",
                time.gmtime(time.time()-self.start_time)
            )
            return f"[Global] {self.completed}/{self.total} layers | Elapsed: {elapsed}"

class DownloadWorker:
    """下载器（增强401处理）"""
    def __init__(self, conn_mgr, registry, repo, auth_head, progress_mgr, threads):
        self.conn_mgr = conn_mgr
        self.registry = registry
        self.repo = repo
        self.auth_head = auth_head.copy()
        self.progress_mgr = progress_mgr
        self.threads = threads
        self.error_stats = defaultdict(int)
        self.last_error_ts = 0

    def _generate_url(self, blob_digest):
        """生成URL"""
        return (
            f"https://{self.registry}/v2/{self.repo}/blobs/{blob_digest}"
            f"?_ts={int(time.time())}&_rand={random.randint(1000,9999)}"
        )

    def _safe_range_check(self, blob_digest, initial_size):
        """范围检查"""
        session = self.conn_mgr.get_session()
        try:
            head_resp = session.head(
                self._generate_url(blob_digest),
                headers=self.auth_head,
                verify=False,
                timeout=CONNECT_TIMEOUT
            )
            server_size = int(head_resp.headers.get('Content-Length', 0))
            return (
                {
                    "Range": f"bytes={initial_size}-{server_size-1}",
                    "If-Range": head_resp.headers.get('ETag', '')
                },
                server_size
            ) if initial_size < server_size else (None, None)
        except Exception as e:
            logger.warning(f"HEAD请求失败: {str(e)}")
            return {}, None

    def _handle_416_error(self, blob_digest, layer_file):
        """处理416错误"""
        self.error_stats['416'] += 1
        logger.warning(f"执行416恢复流程 {blob_digest[:12]}")
        if os.path.exists(layer_file):
            try:
                os.remove(layer_file)
            except Exception as e:
                logger.error(f"文件删除失败: {e}")
        self.conn_mgr.refresh_connection()
        self.auth_head = get_auth_head(
            self.conn_mgr.get_session(),
            self.registry,
            self.repo
        )

    def download_blob(self, blob_digest):
        """下载核心逻辑（增强令牌刷新）"""
        layer_file, attempt = None, 0
        session = self.conn_mgr.get_session()

        while attempt <= MAX_RETRIES:
            try:
                hash_type, hash_value = blob_digest.split(":")
                layer_dir = os.path.join(
                    f"{self.repo.replace('/', '_')}_layers",
                    "blobs",
                    hash_type
                )
                os.makedirs(layer_dir, exist_ok=True)
                layer_file = os.path.join(layer_dir, hash_value)
                initial_size = os.path.getsize(layer_file) if os.path.exists(layer_file) else 0
                headers = self.auth_head.copy()

                if initial_size > 0:
                    range_headers, server_size = self._safe_range_check(blob_digest, initial_size)
                    if not range_headers:
                        return layer_file
                    headers.update(range_headers)

                with session.get(
                    self._generate_url(blob_digest),
                    headers=headers,
                    stream=True,
                    verify=False,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
                ) as resp:
                    resp.raise_for_status()
                    total_size = int(resp.headers.get('content-length', 0)) or None
                    progress_bar = self.progress_mgr.create_bar(blob_digest) if total_size else None
                    downloaded = initial_size

                    with open(layer_file, "ab" if initial_size > 0 else "wb") as f:
                        chunk_size = LARGE_CHUNK_SIZE if total_size and total_size > LARGE_FILE_THRESHOLD else INIT_CHUNK_SIZE
                        for chunk in resp.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if progress_bar:
                                    progress = min(100, int(downloaded / total_size * 100))
                                    progress_bar.n = progress
                                    progress_bar.refresh()

                    self._verify_layer(blob_digest, layer_file)
                    logger.info(f"{blob_digest[:12]} 下载完成")
                    return layer_file

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    logger.warning(f"认证过期，刷新令牌 {blob_digest[:12]}")
                    self.auth_head = get_auth_head(session, self.registry, self.repo)
                    self.conn_mgr.refresh_connection()
                    attempt = 0  # 重置重试计数器
                    continue
                elif e.response.status_code == 416:
                    self._handle_416_error(blob_digest, layer_file)
                    attempt = 0
                    continue
                attempt = self._handle_error(blob_digest, layer_file, str(e), attempt)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                attempt = self._handle_error(blob_digest, layer_file, str(e), attempt)
            except Exception as e:
                attempt = self._handle_error(blob_digest, layer_file, str(e), attempt)

        logger.error(f"{blob_digest[:12]} 超过最大重试次数")
        raise RuntimeError("下载失败")

    def _handle_error(self, digest, file_path, error_msg, attempt):
        """错误处理"""
        self.error_stats[error_msg.split(':')[0]] += 1
        attempt += 1
        jitter = random.uniform(0.5, 1.5)
        delay = (RETRY_BACKOFF_BASE ** attempt) * jitter
        logger.warning(f"第{attempt}次重试 {digest[:12]} 原因: {error_msg} 等待: {delay:.1f}s")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"文件清理失败: {e}")
        time.sleep(delay)
        return attempt

    def _verify_layer(self, digest, file_path):
        """校验文件"""
        hash_algo, expected = digest.split(":")
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha.update(chunk)
        if sha.hexdigest() != expected:
            logger.error(f"校验失败: 期望 {expected[:12]} 实际 {sha.hexdigest()[:12]}")
            raise ValueError("文件校验失败")

# ----------------- 主程序 -----------------
def main():
    """入口函数"""
    parser = argparse.ArgumentParser(description=f"Docker镜像下载工具 {VERSION}")
    parser.add_argument("image", help="镜像名称（格式：仓库/镜像:标签 或 镜像:标签）")
    parser.add_argument(
        "-r", "--registry",
        default="registry.hub.docker.com",
        help="Docker仓库地址（默认：registry.hub.docker.com）"
    )
    parser.add_argument(
        "-t", "--threads",
        type=int,
        default=5,
        help=f"下载线程数（默认5，最大{MAX_THREADS}）"
    )
    args = parser.parse_args()

    try:
        args.threads = min(max(args.threads, 1), MAX_THREADS)
        repo, img, tag = parse_image_input(args.image)
        full_repo = f"{repo}/{img}" if repo != "library" else img
        
        # 确保logger全局可用
        global logger
        logger.info(f"开始下载: {full_repo}:{tag} 仓库: {args.registry} 线程: {args.threads}")

        conn_mgr = ConnectionManager()
        session = conn_mgr.get_session()
        auth_head = get_auth_head(session, args.registry, full_repo)
        manifest_data = fetch_manifest(session, args.registry, full_repo, tag, auth_head)

        logger.info(f"检测到 {len(manifest_data['layers'])} 个层需要下载")
        progress_mgr = ThreadSafeProgress(len(manifest_data["layers"]))

        # 显式使用导入的ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            worker = DownloadWorker(
                conn_mgr,
                args.registry,
                full_repo,
                auth_head,
                progress_mgr,
                args.threads
            )
            futures = [executor.submit(worker.download_blob, blob) for blob in manifest_data["layers"]]

            try:
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                        logger.info(progress_mgr.update_global())
                    except Exception as e:
                        logger.error(f"致命错误: {str(e)}")
                        raise
            except KeyboardInterrupt:
                logger.error("用户中断操作")
                executor.shutdown(wait=False)
                sys.exit(1)

        logger.info("所有层下载完成")

    except Exception as e:
        logger.error(f"执行失败: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
