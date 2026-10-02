# DLL 构建准备

日期：2026-10-02。范围：S3 构建基底。用户已确认 WSL 安装与项目内下载，已在用户终端完成安装并核验，固定子模块、Protobuf 和基线 DLL 构建已完成；项目脚本复跑与静态产物检查通过，已完成经单独确认的临时加载验证并恢复原文件；实际结果见[加载验证](../验证/基线DLL加载验证.md)。接口与测试范围见[原版事件接口验证](../验证/原版事件接口验证.md)，实现次序见[契约草案](../../drafts/接口/L1基础接口契约与现状审计.md#s3-首批实现顺序)。

## 已有工具

WSL 为 Ubuntu 26.04.1，已有 g++、make、git、Python；本次新增 CMake 4.2.3、MinGW GCC 13-posix、zlib 开发包 1.3.1、protoc 3.21.12，dpkg-query 均确认 install ok installed，工具版本命令成功。未引入 clang-cl、ninja、docker 或 wine。Windows 查询通过 PowerShell 与 vswhere 执行，不修改 PATH 或注册表。

| Windows 工具 | 只读确认 |
|---|---|
| CMake | D:\Dev\tools\CMake\bin\cmake.exe，4.3.3 |
| Ninja | D:\Dev\tools\ninja-win\ninja.exe，1.13.2 |
| Visual Studio | Community 2022，17.14.37314.3；已安装 VC.Tools.x86.x64 |
| MSVC / SDK | MSVC 14.44.35207，vcvars32.bat 存在；Windows SDK Lib 10.0.22621.0 存在 |
| LLVM | PATH 与 VS 两个标准 LLVM 路径未发现 clang-cl，不代表整盘不存在 |
| protoc | D:\Anaconda3\Library\bin\protoc.exe，25.3；不能直接假定与上游固定 Protobuf 头文件兼容 |

普通 Windows PATH 没有 cl，不表示未安装 MSVC。上述结果只确认工具与安装目录，未编译或运行验证完整工具链。

## 上游约束与路线选择

研究基线源码为 .agents/tmp/interface-research/repos/ra2yrcpp 的 ee215f5a01f709c52b1fe4dd333d16cbe5d5f146；独立构建源码位于 .agents/tmp/engine-build/sources/ra2yrcpp，八个直接子模块及 Protobuf 的两个递归子模块已按固定 gitlink 检出，git status 为空。版本与许可边界见[复用评估](../引擎/引擎接口复用评估.md)。本次依据固定源码 README、Dockerfile、CMakeLists、toolchain 与 CI，而非最新上游推断。

上游 Docker 与 CI 主要使用 MinGW i686，另提供 clang-cl / MSVC SDK 交叉构建。Docker 基于 Ubuntu 24.04，当前 WSL 为 26.04，复用构建路径不代表工具版本相同。已有 MSVC 可作为备选，但 CMake 的编译参数和源代码兼容性仍需适配；尚不能判定 MSVC 必然失败或无需改动。

建议优先 WSL MinGW；无需为此引入完整 Docker / Wine 或 Python 第三方包。Protobuf 的原生 protoc 与 Windows i686 库须分别处理，目标库用所选编译器重建，不能混用 Anaconda 25.3 或 MSVC 目标库。上游 Docker 使用 Protobuf 3.21.12，本次核验固定子模块 GOOGLE_PROTOBUF_VERSION=3021012，与系统 protoc 3.21.12 匹配；目标静态库已用 MinGW 重建，不需要另建原生 protoc。

APT 只读模拟命令为 apt-get --simulate install --no-install-recommends cmake g++-mingw-w64-i686-posix libz-mingw-w64-dev protobuf-compiler。当前缓存给出新增 19 个包、0 升级、0 删除；这是方案估计，不代表已安装或刷新索引后的结果不变。直接包候选分别为 CMake 4.2.3-2ubuntu2、MinGW 13.2.0-6ubuntu1+26.1、zlib 1.3.1+dfsg-2、protoc 3.21.12-15ubuntu1。安装影响 WSL /usr 与 APT 管理目录，非仅项目内文件；依赖求解出现显著变化时重新说明。

## 已确认改动与文件结构

用户已明确确认：安装上述 WSL 构建包及求解依赖；将固定源码与子模块下载到 .agents/tmp/engine-build/。Agent 的 sudo -n 因需要交互认证失败，由用户在自己的终端完成安装；未收集密码。首次源码准备审批被误中断，复查未创建目录后已重新开始；不存在已确认的重复后台下载任务。该确认只涵盖构建准备，不涵盖游戏 DLL 替换、显示配置、Windows 工具升级或 DSH 变更。

| 计划位置 | 用途 |
|---|---|
| .agents/tmp/engine-build/sources/ra2yrcpp/ | 独立基线源码，直接子模块按 gitlink 固定，递归依赖记录实际提交 |
| .agents/tmp/engine-build/build/ | Protobuf 与 DLL 的构建中间文件 |
| .agents/tmp/engine-build/prefix/ | 项目内目标库与必要原生工具安装前缀 |
| .agents/tmp/engine-build/artifacts/ | 输出 DLL、依赖与哈希清单，不自动复制到游戏目录 |
| .agents/tmp/engine-build/logs/ | 配置、构建及依赖版本日志 |

研究仓库保持调查基线，工程补丁另保存为可追溯的项目文件，具体归档位置在补丁形成时确定；临时构建目录不作为正式代码的唯一保存处。源码版本、子模块清单、编译器版本、完整配置参数和输出 SHA-256 进入记录。

## 构建结果与复跑

入口为 [tools/build_engine.sh](../../../tools/build_engine.sh)。在项目根执行 bash tools/build_engine.sh；默认四个并行任务，ENGINE_BUILD_JOBS 可指定正整数。脚本要求固定基线与子模块干净、protoc 为 3.21.12；不执行 APT 安装、源码克隆、游戏启动或 DLL 替换。首次 CMake 配置仍会下载固定 GoogleTest，需网络授权；源码准备与系统工具安装必须另行完成。

源码准备使用 git clone --no-hardlinks 从研究仓库复制，再 checkout --detach 到固定提交，git submodule update --init --recursive 下载固定子模块。构建脚本分别配置并编译 libprotobuf 和 ra2yrcpp_dll，不编译上游测试、CLI 或 Windows protoc，不向 /usr 安装自编产物；实际命令、版本和静态检查保存在 logs/ 与 artifacts/baseline/manifest.json。

本次遇到两项构建适配：MinGW 运行时位于 /usr/lib/gcc/i686-w64-mingw32/13-posix，通过 CMAKE_INCLUDE_PATH 搜索，不创建系统软链接；上游 --whole-archive 会同时链接 libwinpthread.a 的 version.o，导致重复 VERSIONINFO。脚本复制静态库到 prefix/runtime/，仅删除 version.o 资源成员，并用 CMAKE_SHARED_LINKER_FLAGS 指定该副本；系统库和线程实现成员不改动，主源码与子模块无补丁。修正后的链接不再出现重复资源警告，旧失败日志仍保留。

| 检查 | 结果与证据边界 |
|---|---|
| Protobuf / DLL 编译 | 两个目标编译及链接成功 |
| 脚本复跑 | 通过；复用了现有编译缓存，不证明跨机器字节可复现 |
| 输出 | .agents/tmp/engine-build/artifacts/baseline/libra2yrcpp.dll，8249365 字节 |
| SHA-256 | bfb14fbdd34bbd9bc14f73c0873319dced18865b6547c61e980f526ae6c116ad |
| 架构 / hook | PE32 Intel i386 DLL；.syhks00 存在，七个预期导出存在 |
| 导入 | WS2_32.dll、WSOCK32.DLL、KERNEL32.dll、msvcrt.dll；该产物未导入外置 Protobuf、zlib 或 MinGW 运行 DLL |
| 资源 | 修正后一个版本资源叶项；未进行 Windows GetFileVersionInfo 专测 |
| 存储 | 构建目录实测约 366 MB，另有 WSL APT 安装占用约 520 MB 的元数据估计 |
| 游戏加载与效果 | [限定加载与只读验证通过](../验证/基线DLL加载验证.md)；已恢复原 DLL，本基线不包含 Guard 等新操作 |

当前没有遗留源码下载或编译任务。本次安装、误中断操作和初次配置路径失败均已处理；上游最低 CMake 版本的弃用警告保留，不视为构建失败。编译和 PE 静态检查不证明 hook 地址、对象布局、联机运行或玩家操作正确。

## 加载验证与后续边界

用户已单独确认并执行临时基线替换与只读双实例验证；结果、未验范围、帧差、日志限制与恢复证据见[基线 DLL 加载验证](../验证/基线DLL加载验证.md)。新的 DLL 未永久部署，后续功能版本的替换仍需说明具体变更并确认。

构建清单仅描述构建脚本检查范围，其中 game_loaded=False 表示脚本自身未启动游戏；实际加载结论以验证记录为准，不通过手工改写清单伪造构建步骤。

## 执行顺序与验证边界

1. 获得安装和下载确认，核对实际求解结果并准备独立源码；不使用不受控的全量系统升级。
2. 核验 Protobuf 版本，生成匹配的协议代码，构建 i686 库与基线 DLL；使用项目内 prefix，不安装自编库到 /usr。
3. 将构建适配与功能补丁分开；上游无条件 FetchContent 下载 GoogleTest，构建准备须明确这一网络依赖，即使 BUILD_TESTS=OFF 也不能认为自动跳过。
4. 检查产物架构、依赖和版本，形成构建记录。基线重建不承诺与现有 release DLL 字节一致，编译器和版本记录用于解释差异。
5. 在基底建立后推进受控 GuardCurrent / GuardPosition、能力支持声明和最少对象回读，再验证对应修改；不通过任意 MissionClicked 绕过安全规则。
6. 替换测试游戏 DLL 前单独说明备份、替换位置、回退与场景，并获得确认；真机验证仍允许人工协作。

持续暂停恢复未验、HARV 按用户决定不重测、模型只调用技法的限制继续保留。仅检查环境不增加任何命令可用性或真机效果结论。
