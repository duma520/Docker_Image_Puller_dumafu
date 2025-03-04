# Docker镜像下载工具（杜玛府版）

起源版：[https://github.com/topcss/docker-pull-tar](https://github.com/topcss/docker-pull-tar/releases/tag/v1.0.7)

因为众所周知的原因，原版 1.0.7 版本下载只是单线程，但是RAGFlow 0.17.0 高达9G，下载完大概第4到6个文件的时候就认证就超时了， 本着源码不变的情况下增加多线程就算的原则，对于Python还是小白程度的我，只能求助AI，但众所周知，有时候AI想的，跟我想的不太一样，出现的问题也不一样，大概就跟钢铁侠整那套钢铁一样，通过不断地迭代，最终整了一个自己的版本出来。

---------------------------------------------------------------------------------------

已经安装了Python的：python docker_image_puller6.py infiniflow/ragflow:v0.17.0 -r docker.1ms.run -t 20
默认Docker仓库可以：python docker_image_puller6.py infiniflow/ragflow:v0.17.0
打包成exe文件可以使用 PyInstaller（推荐）
这里我也写一下，怕我自己都忘记了。

---------------------------------------------------------------------------------------

将Python脚本打包为EXE文件可通过多种工具实现，以下是详细步骤和常见方法：

---

### **方法一：使用 PyInstaller（推荐）**
**优点**：跨平台、简单易用、支持生成单个EXE文件。  
**步骤**：

1. **安装 PyInstaller**  
   ```bash
   pip install pyinstaller
   ```

2. **基本打包命令**  
   在脚本目录下执行：
   ```bash
   pyinstaller -F your_script.py
   ```
   - `-F` 生成单个EXE文件（默认生成包含依赖的文件夹）。
   - 生成文件位于 `dist/` 目录。

3. **添加资源文件（如图片、数据）**  
   使用 `--add-data` 指定资源路径（格式：`源路径;目标路径`）：
   ```bash
   pyinstaller -F --add-data "images/*.png;images" your_script.py
   ```

4. **自定义图标**  
   ```bash
   pyinstaller -F --icon=app.ico your_script.py
   ```

5. **减少体积（使用UPX压缩）**  
   - 下载 [UPX](https://upx.github.io/) 并解压。
   ```bash
   pyinstaller -F --upx-dir=C:\path\to\upx your_script.py
   ```

6. **调试打包问题**  
   - 添加 `--debug` 生成调试版本。
   - 在命令行运行EXE查看报错。

---

### **方法二：使用 cx_Freeze**
**优点**：适合分发包包含多个文件。  
**步骤**：

1. **安装 cx_Freeze**  
   ```bash
   pip install cx_Freeze
   ```

2. **创建 `setup.py` 文件**  
   ```python
   from cx_Freeze import setup, Executable

   setup(
       name="YourApp",
       version="1.0",
       description="Description",
       executables=[Executable("your_script.py", icon="app.ico")],
       options={
           "build_exe": {
               "packages": ["os"],
               "include_files": ["images/", "data.txt"],
           }
       }
   )
   ```

3. **生成EXE**  
   ```bash
   python setup.py build
   ```
   - 结果在 `build/` 目录。

---

### **方法三：使用 py2exe（仅Windows）**
**步骤**：

1. **安装 py2exe**  
   ```bash
   pip install py2exe
   ```

2. **创建 `setup.py`**  
   ```python
   from distutils.core import setup
   import py2exe

   setup(console=["your_script.py"])
   ```

3. **生成EXE**  
   ```bash
   python setup.py py2exe
   ```

---

### **常见问题解决**
1. **EXE闪退**  
   - 在命令行运行EXE查看报错。
   - 确保所有依赖资源通过 `--add-data` 正确添加。

2. **路径问题**  
   使用以下代码兼容打包后的路径：
   ```python
   import sys
   import os

   if getattr(sys, 'frozen', False):
       base_path = sys._MEIPASS
   else:
       base_path = os.path.dirname(__file__)
   resource_path = os.path.join(base_path, "images/image.png")
   ```

3. **杀毒软件误报**  
   使用代码签名证书签名EXE，或提示用户添加信任。

---

### **总结**
- **推荐工具**：PyInstaller（适合快速生成单文件）或 cx_Freeze（适合复杂配置）。
- **注意事项**：测试不同系统环境、处理资源路径、压缩体积使用UPX。

按需求选择工具，按步骤操作即可顺利打包！

---------------------------------------------------------------------------------------
infiniflow/ragflow:v0.17.0 表示下载 infiniflow/ragflow ，版本是 0.17.0
docker.1ms.run：不写就是默认官方的 Docker Hub ，写就是第三方的地址
-t 20 ：线程数，1到20,100兆宽度AI建议是 15线程，具体自己体验调整。
其他具体自己看说明书。
论Python我是完全不懂，自己写的程序以前是易语言，现在是易语言新的哪个火山软件。其他就没有了。

再次特别感谢 https://github.com/topcss/docker-pull-tar ，也希望大家一如既往地支持 https://github.com/topcss/docker-pull-tar。
---------------------------------------------------------------------------------------
以下是说明书：Docker镜像下载工具（杜玛府版）v3.7.2
---------------------------------------------------------------------------------------

**Docker镜像下载工具使用说明书**

---

### 一、工具简介
本工具是针对Docker镜像仓库设计的自动化下载工具，支持从公共/私有仓库高效下载镜像层文件。主要特性包括：
- **多线程加速下载**
- **自动处理HTTP 416错误**
- **智能连接池管理**
- **镜像名称自动解析**
- **仓库认证自动处理**
- **实时下载进度显示**
- **文件完整性校验**
- **错误自动重试机制**

---

### 二、环境要求
- **Python 3.8+**
- 依赖库：`requests`, `urllib3`, `tqdm`

```bash
# 安装依赖
pip install requests urllib3 tqdm
```


---

### 三、安装步骤
1. 下载最新代码文件 `docker_image_puller.py`
2. 安装依赖包
3. 赋予执行权限（可选）
```bash
chmod +x docker_image_puller.py
```


---

### 四、使用说明

#### 1. 基础命令格式
```bash
python docker_image_puller.py <镜像名称> [选项]
```


#### 2. 参数详解

| 参数 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `镜像名称` | 是 | 支持标准镜像格式 | `infiniflow/ragflow:v0.17.0`<br>`nginx:latest` |
| `-r/--registry` | 否 | 仓库地址（默认docker官方仓库） | `docker.1ms.run` |
| `-t/--threads` | 否 | 下载线程数（1-20，默认5） | `10` |


#### 3. 使用示例
```bash
# 从默认仓库下载nginx最新版
python docker_image_puller.py nginx:latest

# 从私有仓库下载镜像（10线程）
python docker_image_puller.py infiniflow/ragflow:v0.17.0 -r docker.1ms.run -t 10
```


---

### 五、核心功能说明

#### 1. 下载过程可视化
- **实时显示**：
  - 每个层的12位摘要标识
  - 下载百分比进度
  - 已用/剩余时间估算
- **全局进度**：
  ```bash
  [Global] 3/5 layers | Elapsed: 00:02:17
  ```


#### 2. 文件存储结构
下载文件按以下结构组织：
```
[镜像名称]_layers/
└── [摘要前12位]/
    └── layer.tar
```


#### 3. 错误处理机制

| 错误类型 | 处理策略 | 重试间隔 |
|---------|---------|---------|
| HTTP 416 | 自动删除损坏文件<br>刷新连接池<br>重新认证 | 指数退避 |
| 网络超时 | 自动重试 | 5秒~10分钟 |
| 校验失败 | 终止下载 | - |


---

### 六、高级配置
修改代码顶部参数调整性能：
```python
# 连接配置
CONNECT_TIMEOUT = 600    # 连接超时(秒)
READ_TIMEOUT = 7200      # 读取超时(秒)

# 重试策略
MAX_RETRIES = 20         # 最大重试次数
RETRY_BACKOFF_BASE = 5   # 退避基数

# 性能调优
INIT_CHUNK_SIZE = 262144 # 256KB初始块
LARGE_FILE_THRESHOLD = 524288000  # 500MB大文件阈值
```


---

### 七、日志监控
- **日志文件**：自动生成 `docker_puller.log`
- **关键日志标记**：
  ```log
  [WARNING] 第3次重试 a3ed95caeb02 原因: 504 Gateway Timeout 等待: 18.7s
  [ERROR] 校验失败: 期望 sha256:a3ed95ca 实际 sha256:532ded5d
  ```


---

### 八、常见问题解答

#### Q1: 出现`SSL证书验证失败`错误
```bash
# 临时解决方案（测试环境）
export PYTHONWARNINGS="ignore:Unverified HTTPS request"
```


#### Q2: 下载进度卡在某个百分比
1. 检查网络连接
2. 查看日志文件中的错误提示
3. 尝试减少线程数 `-t 3`

#### Q3: 如何验证下载的完整性？
所有层下载完成后会自动进行SHA256校验，可通过日志查看：
```log
[INFO] sha256:a3ed95ca 下载完成
```


---

### 九、技术支持
遇到未解决问题时请提供：
1. 完整的命令行参数
2. `docker_puller.log` 文件内容
3. 出现问题的镜像名称

**工具版本**：v3.7.2  
**最后更新**：2025-03-04
