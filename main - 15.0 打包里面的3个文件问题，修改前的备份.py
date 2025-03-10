# main.py
import os
import sys
import io
import time
import gzip
import json
import hashlib
import shutil
import requests
import tarfile
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm
import urllib3

# 解决 Windows 终端编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 全局配置
VERSION = "v3.1.0"  # 版本升级
CHUNK_SIZE = 1024 * 512  
MAX_RETRIES = 3          
RETRY_DELAY = 5          
MAX_WORKERS = 1           
RETRY_BACKOFF = 2         

# 初始化日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("docker_pull.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TimeoutHTTPAdapter(HTTPAdapter):
    """自定义超时HTTP适配器"""
    def __init__(self, timeout=30, *args, **kwargs):
        self.timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        kwargs["timeout"] = kwargs.get("timeout") or self.timeout
        return super().send(request, **kwargs)

def create_session():
    """创建带重试机制的会话"""
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"]
    )
    
    adapter = TimeoutHTTPAdapter(
        max_retries=retry_strategy,
        timeout=30
    )
    
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # 设置代理
    session.proxies.update({
        'http': os.environ.get('HTTP_PROXY'),
        'https': os.environ.get('HTTPS_PROXY')
    })
    
    return session

def parse_image_input(image_input):
    """解析镜像名称输入"""
    if '/' not in image_input:
        repo = 'library'
        image_part = image_input
    else:
        repo, image_part = image_input.rsplit('/', 1)
    
    tag = 'latest' if ':' not in image_part else image_part.split(':', 1)[1]
    img = image_part.split(':', 1)[0]
    
    return repo, img, tag

def get_auth_token(session, registry, repo, img, force_refresh=False):
    """获取/刷新 Docker 仓库认证令牌"""
    token_key = f"{registry}_{repo}_{img}_token"
    token_exp_key = f"{token_key}_exp"
    current_time = time.time()
    
    if not force_refresh and hasattr(session, token_key):
        if getattr(session, token_exp_key, 0) > current_time + 30:
            token = getattr(session, token_key)
            logger.debug(f"重用缓存令牌前8位: {token[:8]}******")
            print(f"当前令牌前8位: {token[:8]}******")
            return {'Authorization': f'Bearer {token}'}
        logger.debug("检测到令牌即将过期，强制刷新")

    try:
        auth_url = f"https://{registry}/v2/"
        resp = session.get(auth_url, verify=False)
        
        if resp.status_code == 401:
            auth_header = resp.headers.get('Www-Authenticate', '')
            service = auth_header.split('service="')[1].split('"')[0]
            realm = auth_header.split('realm="')[1].split('"')[0]
            
            token_url = f"{realm}?service={service}&scope=repository:{repo}/{img}:pull"
            resp = session.get(token_url, verify=False)
            resp.raise_for_status()
            
            token_data = resp.json()
            token = token_data["token"]
            
            # 解析令牌有效期（兼容不同仓库实现）
            if 'expires_in' in token_data:
                expires_in = token_data['expires_in']
            else:  # 默认1小时有效期
                expires_in = 3600

            logger.debug(f"获取新令牌前8位: {token[:8]}******")
            print(f"新生成令牌前8位: {token[:8]}******")
            setattr(session, token_key, token)
            setattr(session, token_exp_key, current_time + expires_in)
            
            logger.debug(f"获取新令牌（有效期{expires_in}秒）")
            return {'Authorization': f'Bearer {token}'}
        
        return {}
    
    except Exception as e:
        logger.error(f"认证失败: {str(e)}")
        raise

def get_manifest(session, registry, repo, img, tag, auth_headers):
    """获取镜像清单数据"""
    url = f"https://{registry}/v2/{repo}/{img}/manifests/{tag}"
    resp = session.get(url, headers=auth_headers, verify=False)
    resp.raise_for_status()
    return resp.json()

def select_architecture(manifest_data, target_arch, session, registry, repo, img, auth_headers):
    """选择指定架构的镜像清单"""
    if 'manifests' not in manifest_data:
        return manifest_data
    
    for m in manifest_data['manifests']:
        platform = m.get('platform', {})
        if (platform.get('architecture') == target_arch 
            and platform.get('os') == 'linux'):
            return get_manifest(
                session, 
                registry, 
                repo, 
                img, 
                m['digest'], 
                auth_headers
            )
    
    raise ValueError(f"未找到 {target_arch} 架构的镜像")

def validate_file(file_path, expected_digest):
    """校验文件SHA256摘要"""
    alg, digest = expected_digest.split(':')
    hasher = hashlib.new(alg)
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    
    if hasher.hexdigest() != digest:
        os.remove(file_path)
        raise ValueError(f"文件校验失败: {os.path.basename(file_path)}")

def download_layer(session, registry, repo, img, layer, output_dir, auth_headers):
    """改进后的下载函数"""
    current_headers = get_auth_token(session, registry, repo, img)
    
    sanitized_name = layer['digest'].replace(':', '_').replace('/', '_')
    tmp_gz = os.path.join(output_dir, f"{sanitized_name}.tar.gz.download")
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            headers = get_auth_token(session, registry, repo, img).copy()
            tmp_gz = os.path.join(output_dir, f"{layer['digest'].replace(':', '_')}.tar.gz.download")
            
            if os.path.exists(tmp_gz):
                headers['Range'] = f'bytes={os.path.getsize(tmp_gz)}-'
            
            with session.get(
                f"https://{registry}/v2/{repo}/{img}/blobs/{layer['digest']}",
                headers=headers,
                stream=True,
                verify=False,
                timeout=30
            ) as resp:
                if resp.status_code == 401:
                    headers = get_auth_token(session, registry, repo, img, force_refresh=True)
                    continue
                
                resp.raise_for_status()
                total_size = int(resp.headers.get('content-length', 0))
                downloaded_size = os.path.getsize(tmp_gz) if os.path.exists(tmp_gz) else 0
                mode = 'ab' if downloaded_size > 0 else 'wb'
                
                with open(tmp_gz, mode) as f, tqdm(
                    total=total_size,
                    initial=downloaded_size,
                    unit='B',
                    unit_scale=True,
                    desc=f"下载 {layer['digest'][:12]}",
                    miniters=1
                ) as pbar:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
                
                validate_file(tmp_gz, layer['digest'])
                shutil.move(tmp_gz, tmp_gz[:-8])  # 移除.download后缀
                break
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                headers = get_auth_token(session, registry, repo, img, force_refresh=True)
                continue
            raise

    layer_digest = layer['digest']
    sanitized_name = layer_digest.replace(':', '_').replace('/', '_')
    gz_path = os.path.join(output_dir, f"{sanitized_name}.tar.gz")
    tar_path = os.path.join(output_dir, f"{sanitized_name}.tar")

    try:
        logger.info(f"正在解压 {layer_digest[:12]}...")
        with gzip.open(gz_path, 'rb') as gz_file:
            with open(tar_path, 'wb') as tar_file:
                shutil.copyfileobj(gz_file, tar_file, length=CHUNK_SIZE)
        os.remove(gz_path)
        return tar_path
    except Exception as e:
        if os.path.exists(tar_path):
            os.remove(tar_path)
        raise

def build_image(output_path, layers_dir, repo, img, tag, package_format="synology"):
    """构建镜像包"""
    if package_format == "synology":
        _build_synology_format(output_path, layers_dir, repo, img, tag)
    else:
        _build_docker_format(output_path, layers_dir, repo, img, tag)

def _build_synology_format(output_path, layers_dir, repo, img, tag):
    """群晖专用格式"""
    tmp_dir = os.path.join(os.path.dirname(output_path), f"synology_build_temp_{int(time.time())}")
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        layer_list = []
        config_id = hashlib.sha256(json.dumps({"created": "1970-01-01T00:00:00Z"}).encode()).hexdigest()
        
        config_content = {
            "architecture": "amd64",
            "rootfs": {
                "type": "layers",
                "diff_ids": [
                    f"sha256:{hashlib.sha256(open(os.path.join(layers_dir, l), 'rb').read()).hexdigest()}"
                    for l in os.listdir(layers_dir) if l.endswith('.tar')
                ]
            }
        }
        config_path = os.path.join(tmp_dir, f"{config_id}.json")
        with open(config_path, 'w') as f:
            json.dump(config_content, f)

        for idx, layer_file in enumerate(os.listdir(layers_dir)):
            if not layer_file.endswith('.tar'):
                continue

            layer_hash = hashlib.sha256()
            with open(os.path.join(layers_dir, layer_file), 'rb') as f:
                layer_hash.update(f.read())
            
            layer_id = layer_hash.hexdigest()
            layer_dir = os.path.join(tmp_dir, layer_id)
            os.makedirs(layer_dir, exist_ok=True)
            
            shutil.copy(
                os.path.join(layers_dir, layer_file),
                os.path.join(layer_dir, "layer.tar")
            )
            
            layer_data = {
                "id": layer_id[:12],
                "parent": "" if idx == 0 else layer_list[-1]['id'],
                "created": "1970-01-01T00:00:00Z"
            }
            with open(os.path.join(layer_dir, "json"), 'w') as f:
                json.dump(layer_data, f)
            with open(os.path.join(layer_dir, "VERSION"), 'w') as f:
                f.write("1.0")
            
            layer_list.append(layer_data)

        manifest = [{
            "Config": f"{config_id}.json",
            "RepoTags": [f"{repo}/{img}:{tag}"],
            "Layers": [os.path.join(layer['id'], "layer.tar") for layer in layer_list]
        }]
        with open(os.path.join(tmp_dir, "manifest.json"), 'w') as f:
            json.dump(manifest, f)

        repositories = {
            f"{repo}/{img}": {tag: layer_list[-1]['id'] if layer_list else ""}
        }
        with open(os.path.join(tmp_dir, "repositories"), 'w') as f:
            json.dump(repositories, f)

        with tarfile.open(output_path, "w") as tar:
            tar.add(tmp_dir, arcname='/')

        logger.info(f"群晖兼容镜像已生成: {output_path}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

def _build_docker_format(output_path, layers_dir, repo, img, tag):
    """标准Docker格式"""
    with tarfile.open(output_path, "w") as tar:
        # 添加所有层文件
        for layer_file in os.listdir(layers_dir):
            if layer_file.endswith('.tar'):
                tar.add(
                    os.path.join(layers_dir, layer_file),
                    arcname=layer_file
                )
        
        # 生成标准manifest
        manifest = [{
            "Config": f"{img}-{tag}.json",
            "RepoTags": [f"{repo}/{img}:{tag}"],
            "Layers": [f for f in os.listdir(layers_dir) if f.endswith('.tar')]
        }]
        
        # 临时写入manifest
        with open("manifest.json", 'w') as f:
            json.dump(manifest, f)
        tar.add("manifest.json")
        os.remove("manifest.json")

        logger.info(f"标准Docker镜像已生成: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Docker镜像下载工具")
    parser.add_argument("image", help="镜像名称 (例如: ubuntu:latest 或 library/alpine:3.12)")
    parser.add_argument("-a", "--arch", default="amd64", help="目标架构 (默认: amd64)")
    parser.add_argument("-r", "--registry", default="registry-1.docker.io", help="镜像仓库地址")
    parser.add_argument("-o", "--output", default="output", help="输出目录")
    parser.add_argument("-j", "--workers", type=int, default=MAX_WORKERS, 
                       help=f"并发下载数 (默认: {MAX_WORKERS})")
    parser.add_argument("-f", "--format", 
                       choices=["docker", "synology"],
                       default="docker",
                       help="打包格式 (默认: docker)")
    parser.add_argument("--insecure", action="store_true", help="跳过SSL证书验证")
    parser.add_argument("--debug", action="store_true", help="启用调试日志")
    
    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    try:
        work_dir = os.path.join(args.output, "layers")
        os.makedirs(work_dir, exist_ok=True)
        
        session = create_session()
        session.verify = not args.insecure
        
        repo, img, tag = parse_image_input(args.image)
        auth_headers = get_auth_token(session, args.registry, repo, img)
        manifest = get_manifest(session, args.registry, repo, img, tag, auth_headers)
        manifest = select_architecture(
            manifest, 
            args.arch,
            session,
            args.registry,
            repo,
            img,
            auth_headers
        )

        layers = manifest['layers']
        
        logger.info(f"共需要下载 {len(layers)} 个镜像层")
        
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = []
            for layer in layers:
                futures.append(executor.submit(
                    download_layer,
                    session=session,
                    registry=args.registry,
                    repo=repo,
                    img=img,
                    layer=layer,
                    output_dir=work_dir,
                    auth_headers=auth_headers
                ))
            
            layer_files = []
            for idx, future in enumerate(futures, 1):
                try:
                    layer_files.append(future.result())
                    logger.info(f"已完成第 {idx}/{len(layers)} 层")
                except Exception as e:
                    logger.error(f"镜像层下载失败: {str(e)}")
                    raise
        
        image_name = f"{repo.replace('/', '_')}_{img}_{tag}.tar"
        output_path = os.path.join(args.output, image_name)
        build_image(output_path, work_dir, repo, img, tag, args.format)
        
    except KeyboardInterrupt:
        logger.info("用户中止操作")
    except Exception as e:
        logger.error(f"程序运行错误: {str(e)}")
    finally:
        session.close()
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()
