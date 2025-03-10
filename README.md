# Docker镜像下载工具（杜玛府版）

起源版：https://github.com/topcss/docker-pull-tar/releases/tag/v1.0.7

本来懒得搞，结果出现一点小问题，只好自己搞了。

### 🤖 Assistant

以下是为该程序编写的三合一用户说明书，采用分层结构满足不同用户需求：

# Docker镜像下载工具 v12.0 使用说明书

## 一、快速入门（新手用户）
### 1. 基本操作步骤
1. 安装Python 3.8+ 和必要依赖：
   ```bash
   pip install requests tqdm
   ```
2. 打开命令提示符（Windows）或终端（Mac/Linux）
3. 输入基础下载命令：
   ```bash
   python main.py ubuntu:latest
   ```
4. 等待下载完成，生成的镜像文件在`output`目录中

### 2. 可视化界面操作（非技术用户）
![操作流程图]
1. 双击运行脚本
2. 按照屏幕提示输入镜像名称
3. 选择保存位置（默认当前目录）
4. 等待进度条完成

## 二、参数详解（普通用户）
| 参数          | 简写 | 示例值              | 说明                                                                 |
|---------------|------|---------------------|----------------------------------------------------------------------|
| --arch        | -a   | arm64               | 指定CPU架构（默认amd64）                                            |
| --registry    | -r   | registry.example.com| 自定义镜像仓库地址                                                   |
| --output      | -o   | /data/images        | 指定输出目录（自动创建）                                             |
| --workers     | -j   | 3                   | 并行下载线程数（提升速度但增加负载）                                 |
| --insecure    | -    | (无参数)            | 跳过SSL证书验证（仅限内网测试使用）                                  |
| --debug       | -    | (无参数)            | 显示详细调试日志                                                     |

## 三、高级配置（专业用户）
### 1. 网络优化配置
```python
# 修改main.py全局配置（需技术背景）
CHUNK_SIZE = 1024 * 1024  # 增大分块尺寸
MAX_WORKERS = 5           # 根据带宽调整
RETRY_STRATEGY = Retry(   # 自定义重试策略
    total=5,
    backoff_factor=1.2
)
```

### 2. 代理服务器配置
```bash
# 通过环境变量设置代理
export HTTPS_PROXY="http://user:pass@proxy.example.com:8080"
python main.py nginx:alpine
```

### 3. 自定义镜像构建
```python
# 修改build_image函数中的元数据生成逻辑
config_content = {
    "os": "linux",
    "config": {"Env": ["PATH=/usr/local/sbin"]},
    # 添加自定义配置...
}
```

## 四、技术实现细节（开发人员）
### 架构解析
1. 认证流程：
   ```mermaid
   sequenceDiagram
      用户->>+仓库: 匿名请求
      仓库-->>-用户: 返回认证要求
      用户->>+认证服务: 获取Bearer Token
      认证服务-->>-用户: 返回临时令牌
   ```

2. 分层下载机制：
   - 多线程分块下载（RFC7233 Range请求）
   - 自动断点续传
   - SHA256强校验机制

3. 错误处理策略：
   - 三级重试机制（线性退避+指数回退）
   - 自动令牌刷新
   - 临时文件原子操作

## 五、典型使用场景
### 场景1：下载ARM架构镜像
```bash
python main.py alpine:3.18 -a arm64
```

### 场景2：企业内网仓库下载
```bash
python main.py -r private-registry.example.com company/image:v1.2
```

### 场景3：生产环境批量下载
```bash
#!/bin/bash
IMAGES=("nginx:1.25" "redis:7.0" "postgres:15")
for img in "${IMAGES[@]}"; do
    python main.py $img -j 4 -o /nas/docker_images
done
```

## 六、常见问题解答
Q1 下载卡在50%不动怎么办？
A：尝试以下步骤：
1. 检查网络连接
2. 添加`--workers 1`参数
3. 删除output目录后重试

Q2 出现SSL证书错误？
A：临时解决方案（有安全风险）：
```bash
python main.py --insecure your_image:tag
```

Q3 如何验证镜像完整性？
A：程序自动校验，手动验证命令：
```bash
sha256sum output/layers/sha256_*
```

## 七、技术支持
[服务支持二维码]
技术支持邮箱：无
GitHub Issues：https://github.com/duma520/Docker_Image_Puller_dumafu/issues

---

本说明书采用分层结构设计：
- 绿色标记部分：新手用户必读
- 蓝色方框内容：系统管理员关注
- 灰色代码块：开发人员专用
- 红色警示标志：安全注意事项

文档版本：2025-03-11
更新说明：新增ARM架构下载示例
