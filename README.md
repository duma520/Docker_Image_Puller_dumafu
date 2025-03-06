# Docker镜像下载工具（杜玛府版）

起源版：[https://github.com/topcss/docker-pull-tar](https://github.com/topcss/docker-pull-tar/releases/tag/v1.0.7)

因为众所周知的原因，原版 1.0.7 版本下载只是单线程，但是RAGFlow 0.17.0 高达9G，下载完大概第4到6个文件的时候就认证就超时了， 本着源码不变的情况下增加多线程就算的原则，对于Python还是小白程度的我，只能求助AI，但众所周知，有时候AI想的，跟我想的不太一样，出现的问题也不一样，大概就跟钢铁侠整那套钢铁一样，通过不断地迭代，最终因为某些限制，只能完全脱离起源版，自己重新写了一个自己的版本出来。这过程真就是痛并快乐着。

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
以下是说明书：Docker镜像下载工具（杜玛府版）v1.0
---------------------------------------------------------------------------------------
